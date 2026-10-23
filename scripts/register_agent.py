#!/usr/bin/env python3
"""Reconcile the owned Codex client and demo user offline role without resetting the realm."""
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from client import ROOT, DemoError, request, require
from setup import realm_config

ADMIN = 'http://localhost:8080/admin/realms/mcp-demo'
CLIENT_ID = 'codex-demo-client'
OWNER = 'codex-v1'


def desired(values):
    return next(c for c in realm_config(values)['clients'] if c['clientId'] == CLIENT_ID)


def reconcile():
    values = json.loads((ROOT / '.local/secrets.json').read_text())
    config = desired(values)
    path = ROOT / '.local/realm.json'
    realm = json.loads(path.read_text())
    matches = [c for c in realm['clients'] if c['clientId'] == CLIENT_ID]
    require(not matches or matches[0].get('attributes', {}).get('mcp-demo.managed') == OWNER,
            'Import client is not owned by this demo')
    demo_users = [u for u in realm['users'] if u.get('username') == 'demo']
    require(len(demo_users) == 1 and demo_users[0].get('email') == 'demo@example.invalid',
            'Expected synthetic demo user missing from import')
    status, _, data = request('POST', 'http://localhost:8080/realms/master/protocol/openid-connect/token', form={
        'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'local-admin', 'password': values['admin_password']})
    require(status == 200, 'Local Keycloak admin authentication failed')
    token = json.loads(data)['access_token']

    def admin(method, path, body=None, expected=200):
        status, _, data = request(method, ADMIN + path, token=token, body=body)
        require(status == expected, 'Local Keycloak client configuration failed')
        return json.loads(data) if data else None

    users = admin('GET', '/users?' + urlencode({'username': 'demo', 'exact': 'true'}))
    require(len(users) == 1 and users[0].get('email') == 'demo@example.invalid',
            'Expected synthetic demo user missing from Keycloak')

    existing = admin('GET', '/clients?' + urlencode({'clientId': CLIENT_ID}))
    require(len(existing) <= 1, 'Ambiguous client ID')
    if existing:
        current = existing[0]
        require(current.get('attributes', {}).get('mcp-demo.managed') == OWNER,
                'Existing client is not owned by this demo; refusing to overwrite it')
        client_id = current['id']
        admin('PUT', '/clients/' + client_id, {**current, **config}, 204)
    else:
        admin('POST', '/clients', config, 201)
        client_id = admin('GET', '/clients?' + urlencode({'clientId': CLIENT_ID}))[0]['id']
    base = '/clients/' + client_id
    scopes = {s['name']: s['id'] for s in admin('GET', '/client-scopes')}
    for kind, wanted in [('default', set(config['defaultClientScopes'])),
                         ('optional', set(config['optionalClientScopes']))]:
        current = admin('GET', base + '/' + kind + '-client-scopes')
        for scope in current:
            if scope['name'] not in wanted:
                admin('DELETE', base + '/' + kind + '-client-scopes/' + scope['id'], expected=204)
        for name in wanted - {s['name'] for s in current}:
            admin('PUT', base + '/' + kind + '-client-scopes/' + scopes[name], expected=204)
    expected_mappers = {m['name']: m for m in config['protocolMappers']}
    current = admin('GET', base + '/protocol-mappers/models')
    for mapper in current:
        wanted = expected_mappers.pop(mapper['name'], None)
        if wanted is None:
            admin('DELETE', base + '/protocol-mappers/models/' + mapper['id'], expected=204)
        elif any(mapper.get(k) != v for k, v in wanted.items()):
            admin('PUT', base + '/protocol-mappers/models/' + mapper['id'], {**wanted, 'id': mapper['id']}, 204)
    for mapper in expected_mappers.values():
        admin('POST', base + '/protocol-mappers/models', mapper, 201)

    current = admin('GET', base)
    require(current.get('publicClient') is True and current.get('fullScopeAllowed') is False
            and current.get('redirectUris') == config['redirectUris']
            and current.get('directAccessGrantsEnabled') is False
            and current.get('serviceAccountsEnabled') is False
            and current.get('attributes', {}).get('pkce.code.challenge.method') == 'S256',
            'Client policy verification failed')
    require({s['name'] for s in admin('GET', base + '/default-client-scopes')} == {'mcp.access'}
            and {s['name'] for s in admin('GET', base + '/optional-client-scopes')} == {'offline_access'},
            'Client scope verification failed')

    # Keycloak requires the user role as well as the optional client scope.
    # Add it only to the known synthetic demo account, preserving all other roles.
    user_path = '/users/' + users[0]['id'] + '/role-mappings/realm'
    offline_role = admin('GET', '/roles/offline_access')
    effective = admin('GET', user_path + '/composite')
    if 'offline_access' not in {r['name'] for r in effective}:
        admin('POST', user_path, [offline_role], 204)
    demo_users[0]['realmRoles'] = sorted(set(demo_users[0].get('realmRoles', [])) | {'offline_access'})

    # Maintain the next fresh import, preserving secrets, users and other clients.
    realm['clients'] = [c for c in realm['clients'] if c['clientId'] != CLIENT_ID] + [config]
    descriptor, filename = tempfile.mkstemp(prefix='realm-', suffix='.json.tmp', dir=path.parent)
    temporary = Path(filename)
    try:
        with os.fdopen(descriptor, 'w') as file:
            json.dump(realm, file, indent=2)
            file.write('\n')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    print('Configured owned public client codex-demo-client: exact callback 127.0.0.1:8766, S256, MCP access and optional offline refresh.')


if __name__ == '__main__':
    try:
        reconcile()
    except Exception as error:
        print('Agent setup failed: ' + (str(error) if isinstance(error, DemoError) else type(error).__name__))
        raise SystemExit(1)
