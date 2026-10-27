#!/usr/bin/env python3
"""Reconcile provider-neutral MCP DCR and the separate public API client, on the VPS only."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlencode
from client import DemoError, request, require
from setup import realm_config

ROOT = Path(__file__).resolve().parents[1]
ADMIN = 'http://127.0.0.1:18080/auth/admin/realms/mcp-demo'
POLICY_TYPE = 'org.keycloak.services.clientregistration.policy.ClientRegistrationPolicy'
PROFILE = 'mcp-demo-app-oauth'


def registration_policies():
    return {
        'allowed-client-templates': {'allow-default-scopes': ['false'],
                                    'allowed-client-scopes': ['openid', 'mcp.access', 'offline_access']},
        'allowed-protocol-mappers': {'allowed-protocol-mapper-types': []},
        'max-clients': {'max-clients': ['32']}}


def oauth_profile():
    return {'name': PROFILE, 'description': 'Managed MCP demo OAuth: code flow with S256 and exact secure redirects',
            'executors': [
                {'executor': 'pkce-enforcer', 'configuration': {'auto-configure': True}},
                {'executor': 'reject-ropc-grant', 'configuration': {'auto-configure': True}},
                {'executor': 'reject-implicit-grant', 'configuration': {'auto-configure': True}},
                {'executor': 'secure-redirect-uris-enforcer', 'configuration': {
                    # The public registration gateway restricts HTTP to literal loopback hosts.
                    'allow-ipv4-loopback-address': True, 'allow-ipv6-loopback-address': True,
                    'allow-http-scheme': True, 'allow-wildcard-context-path': False,
                    'allow-private-use-uri-scheme': False, 'allow-open-redirect': False}}]}


def oauth_policy():
    return {'name': PROFILE, 'description': 'Managed MCP demo authorization-code security policy', 'enabled': True,
            'conditions': [{'condition': 'client-updater-context', 'configuration': {
                'update-client-source': ['ByAnonymous', 'ByRegistrationAccessToken']}}],
            'profiles': [PROFILE]}


def mapper_matches(existing, wanted):
    # Keycloak materializes these defaults when exporting a newly created mapper.
    defaults = {'introspection.token.claim': 'true', 'userinfo.token.claim': 'false'}
    actual = existing.get('config', {})
    return (all(existing.get(k) == wanted[k] for k in ['name', 'protocol', 'protocolMapper'])
            and all(actual.get(k) == v for k, v in wanted['config'].items())
            and all(k in wanted['config'] or defaults.get(k) == v for k, v in actual.items()))


def atomic_json(path, value, mode=0o600):
    fd, filename = tempfile.mkstemp(dir=path.parent, prefix='registration-')
    temporary = Path(filename)
    try:
        with os.fdopen(fd, 'w') as file:
            json.dump(value, file, indent=2)
            file.write('\n')
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def reconcile():
    os.umask(0o077)
    directory = ROOT / '.hosted'
    values = json.loads((directory / 'secrets.json').read_text())
    deployment = json.loads((directory / 'deployment.json').read_text())
    resource = 'https://' + deployment['hostname'] + '/mcp'
    status, _, data = request('POST', 'http://127.0.0.1:18080/auth/realms/master/protocol/openid-connect/token', form={
        'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'hosted-admin', 'password': values['admin_password']})
    require(status == 200, 'Private Keycloak administration failed')
    token = json.loads(data)['access_token']

    def admin(method, path, body=None, expected=200):
        status, _, data = request(method, ADMIN + path, token=token, body=body)
        require(status == expected, 'Keycloak registration migration failed: ' + method + ' ' + path)
        return json.loads(data) if data else None

    clients = admin('GET', '/clients')
    exchange = next(c for c in clients if c['clientId'] == 'mcp-server')
    require(exchange.get('fullScopeAllowed') is False and exchange.get('defaultClientScopes') == ['tickets.read']
            and not exchange.get('optionalClientScopes'), 'Expected read-only exchange ceiling is missing')
    defaults = admin('GET', '/default-default-client-scopes')
    optional = admin('GET', '/default-optional-client-scopes')
    require({s['name'] for s in defaults} <= {'mcp.access'} and {s['name'] for s in optional} <= {'offline_access'},
            'Unexpected realm default scopes; refusing anonymous client registration')
    components = admin('GET', '/components?' + urlencode({'type': POLICY_TYPE}))
    anonymous = {p['providerId']: p for p in components if p.get('subType') == 'anonymous'}
    require(len(anonymous) == len([p for p in components if p.get('subType') == 'anonymous'])
            and set(registration_policies()) <= set(anonymous)
            and {'scope', 'consent-required'} <= set(anonymous), 'Expected anonymous registration safeguards missing')
    scopes = admin('GET', '/client-scopes')
    scope = next(s for s in scopes if s['name'] == 'mcp.access')
    scope_id = scope['id']
    mappers = admin('GET', '/client-scopes/' + scope_id + '/protocol-mappers/models')
    profiles = admin('GET', '/client-policies/profiles')
    policies = admin('GET', '/client-policies/policies')
    backup = directory / 'registration-before.json'
    if not backup.exists():
        atomic_json(backup, {'components': components, 'mappers': mappers, 'profiles': profiles,
                            'policies': policies, 'default_scopes': defaults, 'optional_scopes': optional})

    # Put the safeguards in place before allowing any new registration source.
    profiles['profiles'] = [p for p in profiles.get('profiles', []) if p['name'] != PROFILE] + [oauth_profile()]
    admin('PUT', '/client-policies/profiles', {'profiles': profiles['profiles']}, 204)
    policies['policies'] = [p for p in policies.get('policies', []) if p['name'] != PROFILE] + [oauth_policy()]
    admin('PUT', '/client-policies/policies', {'policies': policies['policies']}, 204)
    config = realm_config(values, resource)
    desired = next(c for c in config['clients'] if c['clientId'] == 'mcp-demo-client')['protocolMappers']
    for mapper in desired:
        existing = next((m for m in mappers if m['name'] == mapper['name']), None)
        if existing:
            require(mapper_matches(existing, mapper), 'Unexpected resource mapper conflict')
        else:
            admin('POST', '/client-scopes/' + scope_id + '/protocol-mappers/models', mapper, 201)
    if scope_id not in {s['id'] for s in defaults}:
        admin('PUT', '/default-default-client-scopes/' + scope_id, expected=204)
    for provider, settings in registration_policies().items():
        component = anonymous[provider]
        admin('PUT', '/components/' + component['id'], {**component, 'config': settings}, 204)
    # Callback validation belongs to the public registration gateway, not a vendor host list.
    if 'trusted-hosts' in anonymous:
        admin('DELETE', '/components/' + anonymous['trusted-hosts']['id'], expected=204)

    current = admin('GET', '/clients/' + exchange['id'])
    require(all(current.get(k) == exchange.get(k) for k in ['fullScopeAllowed', 'defaultClientScopes',
            'optionalClientScopes', 'attributes', 'publicClient']), 'Exchange client changed unexpectedly')
    api_client = next(c for c in clients if c['clientId'] == 'api-demo-client')
    require(api_client.get('publicClient') is True and api_client.get('fullScopeAllowed') is False
            and set(api_client.get('defaultClientScopes', [])) == {'tickets.read', 'tickets.write'},
            'Unexpected direct API client configuration')
    api_redirects = ['http://127.0.0.1:8765/callback', 'https://oauth.pstmn.io/v1/callback',
                     'https://oauth.pstmn.io/v1/browser-callback']
    admin('PUT', '/clients/' + api_client['id'], {**api_client, 'redirectUris': api_redirects}, 204)
    # Preserve the next realm import as well; policies are reconciled after every deployment.
    path = directory / 'realm.json'
    realm = json.loads(path.read_text())
    realm['defaultDefaultClientScopes'] = ['mcp.access']
    realm['defaultOptionalClientScopes'] = ['offline_access']
    realm['clientProfiles'] = {'profiles': profiles['profiles']}
    realm['clientPolicies'] = {'policies': policies['policies']}
    next(c for c in realm['clients'] if c['clientId'] == 'api-demo-client')['redirectUris'] = api_redirects
    realm_scope = next(s for s in realm['clientScopes'] if s['name'] == 'mcp.access')
    for mapper in desired:
        if not any(m['name'] == mapper['name'] for m in realm_scope['protocolMappers']):
            realm_scope['protocolMappers'].append(mapper)
    atomic_json(path, realm, 0o640)
    atomic_json(directory / 'registration-migration.json', {
        'executed_at': datetime.now(timezone.utc).isoformat(), 'resource': resource,
        'callback_policy': 'HTTPS or literal HTTP loopback; exact URIs without wildcards', 'max_realm_clients': 32,
        'default_scope': 'mcp.access', 'exchange_ceiling': 'tickets.read'})
    print('Configured provider-neutral HTTPS/loopback DCR, S256 PKCE and public API login; MCP exchange remains read-only.')


if __name__ == '__main__':
    try:
        reconcile()
    except Exception as error:
        print(str(error) if isinstance(error, DemoError) else 'Registration setup failed: ' + type(error).__name__)
        raise SystemExit(1)
