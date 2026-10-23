#!/usr/bin/env python3
"""Generate local-only secrets and realm import. Existing installations are preserved."""
import json
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'


def realm_config(values):
    def mapper(name, kind, config):
        return {'name': name, 'protocol': 'openid-connect', 'protocolMapper': kind,
                'consentRequired': False, 'config': config}

    def audience(client, uri=None):
        config = {'included.client.audience': client, 'access.token.claim': 'true', 'id.token.claim': 'false'}
        if uri:
            config['included.custom.audience'] = uri
        return mapper('fixed-audience', 'oidc-audience-mapper', config)

    def roles(client):
        return mapper('client-roles', 'oidc-usermodel-client-role-mapper', {
            'usermodel.clientRoleMapping.clientId': client,
            'claim.name': 'resource_access.' + client + '.roles',
            'jsonType.label': 'String', 'multivalued': 'true',
            'access.token.claim': 'true', 'id.token.claim': 'false', 'userinfo.token.claim': 'false'})

    def subject():
        return mapper('subject', 'oidc-sub-mapper', {'access.token.claim': 'true'})

    def resource_mappers(api=False):
        result = [subject(), audience('tickets-api' if api else 'mcp-server')]
        if not api:
            result.append(mapper('resource-audience', 'oidc-audience-mapper', {
                'included.custom.audience': 'http://localhost:8082/mcp',
                'access.token.claim': 'true', 'id.token.claim': 'false'}))
        return result

    def scope(name, client):
        return {'name': name, 'protocol': 'openid-connect', 'attributes': {'include.in.token.scope': 'true'},
                'protocolMappers': [roles(client)]}

    def public(client, scopes, extra=None):
        return {'clientId': client, 'enabled': True, 'protocol': 'openid-connect', 'publicClient': True,
                'standardFlowEnabled': True, 'directAccessGrantsEnabled': False,
                'serviceAccountsEnabled': False, 'fullScopeAllowed': False,
                'redirectUris': ['http://127.0.0.1:8765/callback'], 'webOrigins': [],
                'defaultClientScopes': scopes, 'optionalClientScopes': [],
                'protocolMappers': resource_mappers(api='tickets.read' in scopes),
                'attributes': {'pkce.code.challenge.method': 'S256', **(extra or {})}}

    def user(name, password, mapping):
        return {'username': name, 'enabled': True, 'emailVerified': True,
                'firstName': 'Synthetic', 'lastName': name,
                'email': name + '@example.invalid', 'requiredActions': [],
                'credentials': [{'type': 'password', 'value': password, 'temporary': False}],
                'clientRoles': mapping}

    # Scopes are a finite allowlist. In particular, mcp-server has no optional write scope.
    return {
        'realm': 'mcp-demo', 'enabled': True, 'sslRequired': 'none',
        'registrationAllowed': False, 'resetPasswordAllowed': False,
        'accessTokenLifespan': 120, 'ssoSessionIdleTimeout': 1800,
        'defaultDefaultClientScopes': [], 'defaultOptionalClientScopes': [],
        'roles': {'client': {
            'tickets-api': [{'name': 'tickets.read', 'composite': False}, {'name': 'tickets.write', 'composite': False}],
            'mcp-server': [{'name': 'mcp.access', 'composite': False}]}},
        'clients': [
            {'clientId': 'tickets-api', 'enabled': True, 'protocol': 'openid-connect',
             'publicClient': False, 'bearerOnly': True, 'standardFlowEnabled': False,
             'directAccessGrantsEnabled': False, 'fullScopeAllowed': False,
             'defaultClientScopes': [], 'optionalClientScopes': []},
            {'clientId': 'mcp-server', 'enabled': True, 'protocol': 'openid-connect',
             'publicClient': False, 'clientAuthenticatorType': 'client-secret', 'secret': values['mcp_client_secret'],
             'standardFlowEnabled': False, 'directAccessGrantsEnabled': False,
             'serviceAccountsEnabled': False, 'fullScopeAllowed': False,
             'defaultClientScopes': ['tickets.read'], 'optionalClientScopes': [],
             'protocolMappers': resource_mappers(api=True),
             'attributes': {'standard.token.exchange.enabled': 'true',
                            'standard.token.exchange.enableRefreshRequestedTokenType': 'false'}},
            public('mcp-demo-client', ['mcp.access']),
            public('api-demo-client', ['tickets.read', 'tickets.write']),
            # A two-second lifetime is confined to this negative-test client.
            public('expiry-demo-client', ['mcp.access'], {'access.token.lifespan': '2'}),
            public('expiry-api-demo-client', ['tickets.read', 'tickets.write'], {'access.token.lifespan': '2'})],
        'clientScopes': [scope('mcp.access', 'mcp-server'),
                         scope('tickets.read', 'tickets-api'), scope('tickets.write', 'tickets-api')],
        'clientScopeMappings': {
            'mcp-server': [{'clientScope': 'mcp.access', 'roles': ['mcp.access']}],
            'tickets-api': [{'clientScope': 'tickets.read', 'roles': ['tickets.read']},
                            {'clientScope': 'tickets.write', 'roles': ['tickets.write']}]},
        'users': [user('demo', values['demo_password'],
                       {'tickets-api': ['tickets.read', 'tickets.write'], 'mcp-server': ['mcp.access']}),
                  user('reader', values['reader_password'],
                       {'tickets-api': ['tickets.read'], 'mcp-server': ['mcp.access']}),
                  user('unprivileged', values['unprivileged_password'], {})]}


def setup():
    os.umask(0o077)
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    LOCAL.chmod(0o700)
    path = LOCAL / 'secrets.json'
    if path.exists():
        if not (LOCAL / 'realm.json').exists() or not (LOCAL / 'docker.env').exists():
            raise SystemExit('Incomplete .local configuration; restore it before starting.')
        print('Existing local secrets and realm preserved.')
        return
    values = {key: secrets.token_urlsafe(32) for key in [
        'db_password', 'admin_password', 'mcp_client_secret', 'demo_password', 'reader_password', 'unprivileged_password']}
    path.write_text(json.dumps(values, indent=2) + '\n')
    (LOCAL / 'realm.json').write_text(json.dumps(realm_config(values), indent=2) + '\n')
    (LOCAL / 'docker.env').write_text('DB_PASSWORD=' + values['db_password'] + '\nADMIN_PASSWORD=' + values['admin_password'] + '\n')
    for name in ['secrets.json', 'realm.json', 'docker.env']:
        (LOCAL / name).chmod(0o600)
    print('Generated local secrets and realm in .local/ (directory 0700, files 0600).')


if __name__ == '__main__':
    setup()
