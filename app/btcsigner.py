from flask import Flask, request, send_from_directory
from flask_stache import render_template
from flask_qrcode import QRcode
from flask_socketio import SocketIO
from bitcoin_rpc_class import RPCHost
import os
import configparser
import mysql.connector
import json
import requests
import string
import random
from flask import jsonify

import numpy as np
import pandas as pd
from plotnine import *

app = Flask(__name__, static_url_path='/static')
qrcode = QRcode(app)

socketio = SocketIO(app)

config = configparser.RawConfigParser()
config.read('btcsigner.conf')

rpcHost = config.get('BITCOIN', 'host')
rpcPort = config.get('BITCOIN', 'port')
rpcUser = config.get('BITCOIN', 'username')
rpcPassword = config.get('BITCOIN', 'password')
rpcPassphrase = config.get('BITCOIN', 'passphrase')
rpcWallet = config.get('BITCOIN', 'wallet')
if rpcWallet is None:
    serverURL = 'http://{}:{}@{}:{}'.format(rpcUser, rpcPassword, rpcHost, rpcPort)
else:
    serverURL = 'http://{}:{}@{}:{}/wallet/{}'.format(rpcUser, rpcPassword, rpcHost, rpcPort, rpcWallet)

myHost = config.get('MYSQL', 'host')
myUser = config.get('MYSQL', 'username')
myPasswd = config.get('MYSQL', 'password')
myDatabase = config.get('MYSQL', 'database')

host = RPCHost(serverURL)
if (len(rpcPassphrase) > 0):
    result = host.call('walletpassphrase', rpcPassphrase, 60)


@app.route('/.well-known/<path:filename>')
def wellKnownRoute(filename):
    return send_from_directory('{}/well-known/'.format(app.root_path), filename, conditional=True)

@app.route('/')
def home():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    status = ''
    data = {
        'status': status,
    }
    return render_template('home', **data)

@app.route('/about')
def about():
    data = {
    }
    return render_template('about', **data)

@app.route('/create')
def create():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    status = ''
    form = True
    my_pubkey = ''
    your_pubkey = ''
    multisig_address = ''

    your_pubkey = request.args.get('pubkey')
    your_descriptor = request.args.get('descriptor')
    descriptor = None
    name = request.args.get('name')
    if your_pubkey is not None:
        form = False
        my_address = host.call('getnewaddress')
        my_pubkey = host.call('getaddressinfo', my_address)['pubkey']
        # TODO: check errors
        multisig_address = host.call('addmultisigaddress', 2, [my_pubkey, your_pubkey])['address']
        status = host.call('importaddress', multisig_address, '', False)

        mydb = mysql.connector.connect(host=myHost, user=myUser, passwd=myPasswd, database=myDatabase)
        mycursor = mydb.cursor()
        sql = "INSERT IGNORE INTO addresses (Address, MyPubkey, YourPubkey, Name, IP) VALUES (%s, %s, %s, %s, %s)"
        val = (multisig_address, my_pubkey, your_pubkey, name, ip)
        mycursor.execute(sql, val)
        mydb.commit()
        mydb.close()

    if your_descriptor is not None:
        form = False
        my_address = host.call('getnewaddress')
        my_pubkey = host.call('getaddressinfo', my_address)['pubkey']
        # TODO: check errors
        descriptor = host.call('getdescriptorinfo', f"wsh(sortedmulti(2,{my_pubkey},{your_descriptor}))")['descriptor']
        multisig_address = host.call('deriveaddresses', descriptor)[0]
        status = host.call('importaddress', multisig_address, '', False)

        mydb = mysql.connector.connect(host=myHost, user=myUser, passwd=myPasswd, database=myDatabase)
        mycursor = mydb.cursor()
        sql = "INSERT IGNORE INTO addresses (Address, MyPubkey, YourPubkey, Name, IP) VALUES (%s, %s, %s, %s, %s)"
        val = (multisig_address, my_pubkey, descriptor, name, ip)
        mycursor.execute(sql, val)
        mydb.commit()
        mydb.close()

    data = {
        'form': form,
        'status': status,
        'my_pubkey': my_pubkey,
        'your_pubkey': your_pubkey,
        'your_descriptor': descriptor,
        'descriptor': descriptor != None,
        'multisig_address': multisig_address,
    }
    return render_template('create', **data)

@app.route('/list')
def list():
    mydb = mysql.connector.connect(host=myHost, user=myUser, passwd=myPasswd, database=myDatabase)
    mycursor = mydb.cursor()
    sql = "SELECT Name, Address, MyPubkey, YourPubkey, Timestamp FROM addresses ORDER BY Timestamp DESC"
    mycursor.execute(sql)
    res = mycursor.fetchall()
    mydb.close()

    results = []
    for row in res:
        obj = {}
        obj['name'] = row[0]
        obj['multisig_address'] = row[1]
        obj['my_pubkey'] = row[2]
        obj['your_pubkey'] = row[3]
        obj['timestamp'] = row[4]
        results.append(obj)

    data = {
        'results': results,
    }
    return render_template('list', **data)

@app.route('/address')
def address():

    name = ''
    multisig_address = ''
    my_pubkey = ''
    your_pubkey = ''
    timestamp = ''

    address = request.args.get('address')
    if address is not None:
        mydb = mysql.connector.connect(host=myHost, user=myUser, passwd=myPasswd, database=myDatabase)
        mycursor = mydb.cursor()
        sql = "SELECT Name, Address, MyPubkey, YourPubkey, Timestamp FROM addresses WHERE Address LIKE '{}'".format(address)
        mycursor.execute(sql)
        res = mycursor.fetchone()
        mydb.close()

        name = res[0]
        multisig_address = res[1]
        my_pubkey = res[2]
        your_pubkey = res[3]
        timestamp = res[4]

        res = requests.get('https://blockstream.info/testnet/api/address/{}'.format(address))

    data = {
        'stats': res.json(),
        'name': name,
        'multisig_address': multisig_address,
        'my_pubkey': my_pubkey,
        'your_pubkey': your_pubkey,
        'timestamp': timestamp,
    }
    return render_template('address', **data)

@app.route('/new_psbt')
def new_psbt():
    ID = 0
    status = ''
    form_1 = True
    form_2 = False
    form_3 = False
    psbt_1 = ''
    psbt_1_base64 = ''
    decoded_psbt = ''
    testmempoolaccept = ''
    txid = ''

    address = request.args.get('address')
    receiving_address = request.args.get('receiving_address')
    psbt_1 = request.args.get('psbt_1')
    signed_psbt = request.args.get('signed_psbt')
    id = request.args.get('id')

    mydb = mysql.connector.connect(host=myHost, user=myUser, passwd=myPasswd, database=myDatabase)
    mycursor = mydb.cursor()
    sql = "SELECT Name, Address FROM addresses"
    mycursor.execute(sql)
    res = mycursor.fetchall()
    mydb.close()
    addresses = []
    for x in res:
        addresses.append({'address':x[1], 'name':x[0]})

    if receiving_address is not None:
        form_1 = False
        form_2 = True
        form_3 = False

        # collect input
        unspenttxs = host.call('listunspent', 1, 99999999, [address])
        input = []
        amount = 0
        sequence = 0
        for tx in unspenttxs:
            input.append({'txid':tx['txid'], 'vout':tx['vout'], 'sequence':sequence})
            sequence = sequence + 1
            amount = amount + tx['amount']

        # create psbt moving funds to receiving_address + op_return
        output = {receiving_address:amount, 'data':'4254435369676e65722e636f6d'}
        psbt_1 = host.call('walletcreatefundedpsbt', input, output, 0, {'subtractFeeFromOutputs':[0], 'includeWatching':True})

        if 'psbt' in psbt_1:
            psbt_1_base64 = psbt_1['psbt']

        mydb = mysql.connector.connect(host=myHost, user=myUser, passwd=myPasswd, database=myDatabase)
        mycursor = mydb.cursor()
        sql = "INSERT IGNORE INTO psbts (Address, ReceivingAddress, PSBT_1) VALUES (%s, %s, %s)"
        val = (address, receiving_address, json.dumps(psbt_1))
        mycursor.execute(sql, val)
        ID = mycursor.lastrowid
        mydb.commit()
        mydb.close()

    elif signed_psbt is not None:
        form_1 = False
        form_2 = False
        form_3 = True

        # decode
        decoded_psbt = host.call('decodepsbt', signed_psbt)

        # sign
        fully_signed_psbt = host.call('walletprocesspsbt', signed_psbt)

        # finalize
        finalized_psbt = host.call('finalizepsbt', fully_signed_psbt['psbt'])

        testmempoolaccept = host.call('testmempoolaccept', [finalized_psbt['hex']])

        # broadcast
        txid = host.call('sendrawtransaction', finalized_psbt['hex'])

        mydb = mysql.connector.connect(host=myHost, user=myUser, passwd=myPasswd, database=myDatabase)
        mycursor = mydb.cursor()
        sql = "UPDATE psbts SET PSBT_2=%s, PSBT_2=%s, Transaction=%s, Txid=%s WHERE ID LIKE %s"
        val = (json.dumps(signed_psbt), json.dumps(finalized_psbt), finalized_psbt['hex'], txid, id)
        mycursor.execute(sql, val)
        mydb.commit()
        mydb.close()

    data = {
        'id': ID,
        'addresses': addresses,
        'status': status,
        'form_1': form_1,
        'form_2': form_2,
        'form_3': form_3,
        'psbt_1': psbt_1,
        'psbt_1_base64': psbt_1_base64,
        'signed_psbt': signed_psbt,
        'decoded_psbt': decoded_psbt,
        'testmempoolaccept': testmempoolaccept,
        'txid': txid,
    }
    return render_template('new_psbt', **data)

@app.route('/sign_psbt')
def sign_psbt():
    ID = 0
    status = ''
    form_1 = True

    decoded_psbt = ''
    testmempoolaccept = ''
    txid = ''

    signed_psbt = request.args.get('signed_psbt')

    if signed_psbt is not None:
        form_1 = False

        # decode
        decoded_psbt = host.call('decodepsbt', signed_psbt)

        # sign
        fully_signed_psbt = host.call('walletprocesspsbt', signed_psbt)

        # finalize
        finalized_psbt = host.call('finalizepsbt', fully_signed_psbt['psbt'])

        testmempoolaccept = host.call('testmempoolaccept', [finalized_psbt['hex']])

        # broadcast
        txid = host.call('sendrawtransaction', finalized_psbt['hex'])

    data = {
        'signed_psbt': signed_psbt,
        'form_1': form_1,
        'decoded_psbt': decoded_psbt,
        'testmempoolaccept': testmempoolaccept,
        'txid': txid,
    }
    return render_template('sign_psbt', **data)

if __name__ == '__main__':
    app.import_name = '.'
    socketio.run(app, host='0.0.0.0', port=5007)
