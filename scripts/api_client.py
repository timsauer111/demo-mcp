#!/usr/bin/env python3
"""Direct API client with a real user PKCE login; no token export or generic proxy."""
import argparse
import json
from urllib.parse import urlencode
from client import API, DemoError, login, request, require

STATUSES = ['OPEN', 'IN_PROGRESS', 'CLOSED']


def integer_at_least(minimum):
    def parse(value):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError('An integer is required') from None
        if number < minimum:
            raise argparse.ArgumentTypeError('Minimum: ' + str(minimum))
        return number
    return parse


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--headless-login', action='store_true', help='Automate the local Keycloak form; still Authorization Code + PKCE')
    commands = cli.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='GET /tickets')
    listing.add_argument('--status', choices=STATUSES)
    listing.add_argument('--offset', type=integer_at_least(0), default=0)
    listing.add_argument('--limit', type=integer_at_least(1), default=20)
    get = commands.add_parser('get', help='GET /tickets/{id}')
    get.add_argument('id', type=integer_at_least(1))
    create = commands.add_parser('create', help='POST /tickets')
    create.add_argument('--title', required=True)
    create.add_argument('--description', default='')
    create.add_argument('--status', choices=STATUSES, default='OPEN')
    patch = commands.add_parser('patch', help='PATCH /tickets/{id}')
    patch.add_argument('id', type=integer_at_least(1))
    patch.add_argument('--title')
    patch.add_argument('--description')
    patch.add_argument('--status', choices=STATUSES)
    delete = commands.add_parser('delete', help='DELETE /tickets/{id}')
    delete.add_argument('id', type=integer_at_least(1))
    return cli


def build_request(args, cli):
    if args.command == 'list':
        if args.limit > 100:
            cli.error('--limit must be between 1 and 100')
        query = {'offset': args.offset, 'limit': args.limit}
        if args.status:
            query['status'] = args.status
        return 'GET', '/tickets?' + urlencode(query), None, 200
    if args.command == 'get':
        return 'GET', '/tickets/' + str(args.id), None, 200
    if args.command == 'create':
        return 'POST', '/tickets', {k: getattr(args, k) for k in ['title', 'description', 'status']}, 201
    if args.command == 'patch':
        body = {k: getattr(args, k) for k in ['title', 'description', 'status'] if getattr(args, k) is not None}
        if not body:
            cli.error('patch requires --title, --description or --status')
        return 'PATCH', '/tickets/' + str(args.id), body, 200
    return 'DELETE', '/tickets/' + str(args.id), None, 204


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    method, path, body, expected = build_request(args, cli)
    token = login('api-demo-client', headless=args.headless_login, resource=API)
    status, _, data = request(method, API + path, token=token, body=body)
    print('HTTP ' + str(status) + ' ' + method + ' ' + path)
    if data:
        print(json.dumps(json.loads(data), ensure_ascii=False, indent=2))
    require(status == expected, 'API request was rejected; see HTTP status above')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('API-Client fehlgeschlagen: ' + (str(error) if isinstance(error, DemoError) else type(error).__name__))
        raise SystemExit(1)
