#!/usr/bin/env python3
"""One-time VPS provisioning. Never replace secrets or an existing realm."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
from setup import realm_config


def setup(root, hostname, public_ip, caddy_image, postgres_image):
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', hostname) or '.' not in hostname:
        raise ValueError('A DNS hostname is required')
    ipaddress.IPv4Address(public_ip)
    for image in [caddy_image, postgres_image]:
        if not re.fullmatch(r'[a-z0-9./:-]+@sha256:[a-f0-9]{64}', image):
            raise ValueError('Container images must be pinned by digest')
    os.umask(0o077)
    directory = root / '.hosted'
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    config = {'hostname': hostname, 'public_ip': public_ip,
              'caddy_image': caddy_image, 'postgres_image': postgres_image}
    path = directory / 'deployment.json'
    if path.exists():
        if json.loads(path.read_text()) != config:
            raise ValueError('Existing deployment differs; refusing to change issuer or credentials')
        if not all((directory / name).is_file() for name in ['secrets.json', 'realm.json', 'docker.env']):
            raise ValueError('Incomplete deployment; restore the original configuration')
        print('Existing hosted realm and secrets preserved.')
        return
    if any((directory / name).exists() for name in ['secrets.json', 'realm.json', 'docker.env']):
        raise ValueError('Partial deployment exists; restore configuration before continuing')
    values = {key: secrets.token_urlsafe(32) for key in [
        'db_password', 'admin_password', 'mcp_client_secret', 'demo_password', 'reader_password', 'unprivileged_password']}
    realm = realm_config(values, resource='https://' + hostname + '/mcp')
    realm.update(sslRequired='external', bruteForceProtected=True, permanentLockout=False,
                 failureFactor=10, waitIncrementSeconds=60, maxFailureWaitSeconds=900)
    files = {
        'secrets.json': json.dumps(values, indent=2),
        'realm.json': json.dumps(realm, indent=2),
        'docker.env': '\n'.join([
            'PUBLIC_HOST=' + hostname, 'PUBLIC_IP=' + public_ip,
            'CADDY_IMAGE=' + caddy_image, 'POSTGRES_IMAGE=' + postgres_image,
            'DB_PASSWORD=' + values['db_password'], 'ADMIN_PASSWORD=' + values['admin_password'],
            'MCP_CLIENT_SECRET=' + values['mcp_client_secret']]),
        'deployment.json': json.dumps(config, indent=2)}
    for name, contents in files.items():
        target = directory / name
        target.write_text(contents + '\n')
        # Keycloak runs as uid 1000, gid 0 and must read the mounted import.
        # The parent stays 0700; only container gid 0 receives file read access.
        target.chmod(0o640 if name == 'realm.json' else 0o600)
    print('Generated isolated hosted realm and secrets (0700/0600).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hostname', required=True)
    parser.add_argument('--public-ip', required=True)
    parser.add_argument('--caddy-image', required=True)
    parser.add_argument('--postgres-image', required=True)
    args = parser.parse_args()
    setup(Path(__file__).resolve().parents[1], args.hostname, args.public_ip, args.caddy_image, args.postgres_image)
