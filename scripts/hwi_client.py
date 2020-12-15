import subprocess
import argparse
import json

parser = argparse.ArgumentParser(description='HWI BTCSigner CLI tool.')
subparsers = parser.add_subparsers(dest='command')
subparsers.required = True

parser_details = subparsers.add_parser('list')

parser_create = subparsers.add_parser('getaddress')
parser_create.add_argument('-f', '--fingerprit', help='Device fingerprint', required=True)
parser_create.add_argument('-n', '--network', help='Network (default="testnet")', default='testnet')
parser_create.add_argument('-p', '--path', help='Derivation path (default="m/44\'/1\'/0\'/0/0")', default="m/44'/1'/0'/0/0")

parser_create = subparsers.add_parser('getxpub')
parser_create.add_argument('-f', '--fingerprit', help='Device fingerprint', required=True)
parser_create.add_argument('-n', '--network', help='Network (default="testnet")', default='testnet')
parser_create.add_argument('-m', '--masterpath', help='First part of the derivation path (default="m/44\'/0\'/0\'")', default="m/44'/0'/0'")
parser_create.add_argument('-a', '--addresspath', help='Last part of the derivation path (default="/0/0")', default='/0/0')

parser_create = subparsers.add_parser('signpsbt')
parser_create.add_argument('-f', '--fingerprit', help='Device fingerprint', required=True)
parser_create.add_argument('--psbt', help='Password for the new user', required=True)

args = parser.parse_args()

if args.command == 'list':
    status = subprocess.check_output(f'hwi enumerate', shell=True).decode()
    print(status)
elif args.command == 'getaddress':
    network = f'--{args.network}'
    status = subprocess.check_output(f'hwi {network} -f {args.fingerprit} displayaddress --path \"{args.path}\" --wpkh', shell=True).decode()
    print(status)
elif args.command == 'getxpub':
    network = f'--{args.network}'
    status = json.loads(subprocess.check_output(f'hwi {network} -f {args.fingerprit} getxpub \"{args.masterpath}\"', shell=True).decode())
    if 'xpub' in status:
        print(f'[{args.fingerprit}/{args.masterpath[2:]}]{status["xpub"]}{args.addresspath}')
    else:
        print('error')
elif args.command == 'signpsbt':
    network = f'--{args.network}'
    status = subprocess.check_output(f'hwi {network} -f {args.fingerprit} signtx \"{args.psbt}\"', shell=True).decode()
    print(status)
