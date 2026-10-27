#!/usr/bin/env python3
"""Live acceptance matrix against Keycloak, API and MCP. Never serialize tokens."""
import json
import os
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timezone
from client import API, MCP, ISSUER, ROOT, SECRETS_FILE, DemoError, McpClient, claims, discover, login, request, require

RESULTS = []
TOKENS = []


def check(condition, label):
    require(condition, label)
    RESULTS.append({'check': label, 'result': 'PASS'})
    print('PASS ' + label, flush=True)


def api(method, path, token=None, body=None):
    status, _, data = request(method, API + path, token=token, body=body)
    return status, json.loads(data) if data else None


def ticket_data(token):
    status, data = api('GET', '/tickets?limit=100', token)
    require(status == 200, 'Read snapshot failed')
    return data


def issue(client='mcp-demo-client', user='demo', resource=MCP):
    token = login(client, user, headless=True, resource=resource)
    TOKENS.append(token)
    return token


def exchange(subject, scope=None, audience='tickets-api'):
    config = json.loads(SECRETS_FILE.read_text())
    form = {'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange',
            'subject_token': subject, 'subject_token_type': 'urn:ietf:params:oauth:token-type:access_token',
            'requested_token_type': 'urn:ietf:params:oauth:token-type:access_token', 'audience': audience}
    if scope is not None:
        form['scope'] = scope
    status, _, data = request('POST', ISSUER + '/protocol/openid-connect/token', form=form,
                             basic=('mcp-server', config['mcp_client_secret']))
    if status == 200:
        token = json.loads(data)['access_token']
        TOKENS.append(token)
        return status, token
    return status, None


def cannot_write(token, label):
    before = ticket_data(token)
    for method, path, body in [
        ('POST', '/tickets', {'title': 'forbidden', 'description': 'synthetic', 'status': 'OPEN'}),
        ('PATCH', '/tickets/1', {'title': 'forbidden'}), ('DELETE', '/tickets/1', None),
        ('POST', '/demo/reset', None)]:
        status, _ = api(method, path, token, body)
        check(status == 403, label + ': ' + method + ' ' + path + ' -> 403')
        check(ticket_data(token) == before, label + ': unchanged after ' + method + ' ' + path)


def run():
    report_path = SECRETS_FILE.parent / 'verification.json'
    report_path.unlink(missing_ok=True)
    discover()
    check(True, 'MCP 401 challenge -> protected-resource metadata -> Keycloak discovery')
    direct = issue('api-demo-client', resource=API)
    subject = issue()
    check(claims(direct)['sub'] == claims(subject)['sub'], 'Direct API and MCP login represent the same demo user')
    check(api('POST', '/demo/reset', direct)[0] == 204, 'Authorized deterministic reset')
    try:
        before = ticket_data(direct)
        check(before['total'] == 3, 'Direct API token reads fixed seed data')
        status, created = api('POST', '/tickets', direct,
                             {'title': 'MCP live proof', 'description': 'synthetic live marker', 'status': 'OPEN'})
        check(status == 201, 'Direct API token creates a ticket -> 201')
        marker = created['id']
        status, patched = api('PATCH', '/tickets/' + str(marker), direct, {'status': 'IN_PROGRESS'})
        check(status == 200 and patched['status'] == 'IN_PROGRESS', 'Direct API token updates a ticket -> 200')
        check(api('GET', '/tickets/' + str(marker), direct)[1] == patched, 'Direct write is persisted in the API store')

        status, backend = exchange(subject)
        check(status == 200 and backend is not None, 'Real Keycloak Standard V2 Token Exchange succeeds')
        b_claims = claims(backend)
        check(b_claims['sub'] == claims(subject)['sub'], 'Exchanged token preserves user subject')
        check(b_claims.get('resource_access', {}).get('tickets-api', {}).get('roles') == ['tickets.read'],
              'Exchanged token has exactly the API read role (supplementary claims check)')
        check(api('GET', '/tickets/' + str(marker), backend)[1] == patched, 'The exact exchanged token reads real API data')
        cannot_write(backend, 'Exact exchanged token B')

        client = McpClient(subject)
        client.initialize()
        check(True, 'MCP initialize and initialized notification succeed over HTTP')
        schemas = client.call('tools/list')
        check({t['name'] for t in schemas['tools']} == {'list_tickets', 'get_ticket'}, 'MCP publishes exactly the two curated tools')
        listed = client.tool('list_tickets', {'status': 'IN_PROGRESS', 'offset': 0, 'limit': 100})
        check(not listed.get('isError') and patched in listed['structuredContent']['tickets'],
              'MCP list_tickets returns the ticket just written through the actual API')
        fetched = client.tool('get_ticket', {'id': marker})
        check(not fetched.get('isError') and fetched['structuredContent'] == patched,
              'MCP get_ticket matches the actual API record exactly')
        outputs = [schemas, listed, fetched]
        for name, args in [('list_tickets', {'url': 'http://example.invalid'}),
                           ('list_tickets', {'limit': 101}), ('get_ticket', {'id': 1.5}),
                           ('get_ticket', {'id': '../admin'}), ('get_ticket', {'id': 999999})]:
            result = client.tool(name, args)
            outputs.append(result)
            check(result.get('isError') is True, 'MCP rejects invalid or missing input: ' + name + ' ' + ','.join(args))

        check(api('GET', '/tickets', subject)[0] == 401, 'Token A at API rejected for wrong audience -> 401')
        check(request('POST', MCP, token=direct, body={})[0] == 401, 'Direct API token at MCP rejected for wrong audience -> 401')
        check(request('POST', MCP, token=backend, body={})[0] == 401, 'Exchanged API token B at MCP rejected for wrong audience -> 401')
        for label, token in [('missing', None), ('malformed', 'not-a-jwt'),
                             ('bad signature', subject[:-12] + ('a' * 12))]:
            check(api('GET', '/tickets', token)[0] == 401, label + ' token at API -> 401')
            check(request('POST', MCP, token=token, body={})[0] == 401, label + ' token at MCP -> 401')

        for scope in ['tickets.write', 'tickets.read tickets.write', 'offline_access tickets.write', 'roles tickets.write']:
            status, elevated = exchange(subject, scope=scope)
            check(status in [200, 400, 403], 'Exchange handles unauthorized scope request: ' + scope)
            if elevated:
                cannot_write(elevated, 'Attempted scope elevation ' + scope)
            else:
                check(True, 'Keycloak denies scope elevation: ' + scope)

        reader = issue(user='reader')
        read_status, read_backend = exchange(reader)
        check(read_status == 200 and claims(read_backend)['sub'] == claims(reader)['sub']
              and claims(reader)['sub'] != claims(subject)['sub'], 'Second user context remains distinct across exchange')
        reader_client = McpClient(reader)
        reader_client.initialize()
        check(not reader_client.tool('get_ticket', {'id': 1}).get('isError'), 'Second user can use MCP without cross-user token reuse')
        no_rights = issue(user='unprivileged')
        check(request('POST', MCP, token=no_rights, body={})[0] == 403, 'Valid MCP audience without MCP role -> 403')
        no_api_rights = issue('api-demo-client', user='unprivileged', resource=API)
        check(api('GET', '/tickets', no_api_rights)[0] == 403, 'Valid API audience without API role -> 403')
        check(api('POST', '/tickets', no_api_rights, {'title': 'x', 'description': '', 'status': 'OPEN'})[0] == 403,
              'Valid API audience without write role -> 403')
        expired = issue('expiry-demo-client')
        require(claims(expired)['exp'] - claims(expired)['iat'] <= 2, 'Short lifetime fixture not active')
        time.sleep(max(0, claims(expired)['exp'] - time.time()) + .3)
        check(request('POST', MCP, token=expired, body={})[0] == 401, 'Real expired Keycloak token at MCP -> 401')
        expired_api = issue('expiry-api-demo-client', resource=API)
        require(api('GET', '/tickets', expired_api)[0] == 200, 'API expiry fixture must first read successfully')
        time.sleep(max(0, claims(expired_api)['exp'] - time.time()) + .3)
        check(api('GET', '/tickets', expired_api)[0] == 401, 'Real expired Keycloak token with correct API audience -> 401')

        check(request('POST', MCP, token=subject, body={}, headers={'Origin': 'https://attacker.invalid'})[0] == 403,
              'MCP rejects untrusted browser Origin')
        check(request('POST', MCP, token=subject, body={}, headers={'Host': 'attacker.invalid'})[0] in (400, 421),
              'MCP rejects untrusted Host')
        check(api('DELETE', '/tickets/' + str(marker), direct)[0] == 204, 'Direct API token deletes -> 204')
        check(api('GET', '/tickets/' + str(marker), direct)[0] == 404, 'Direct deletion actually removes the ticket')
        rendered = json.dumps(outputs)
        local = json.loads(SECRETS_FILE.read_text())
        check(not any(value in rendered for value in [*TOKENS, *local.values()]), 'No issued tokens or local secrets in MCP schemas or results')
        log_host = os.environ.get('DEMO_LOG_SSH_HOST')
        if log_host:
            require(re.fullmatch(r'[a-zA-Z0-9_][a-zA-Z0-9_.@-]*', log_host), 'Invalid log SSH host')
            logs = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', log_host,
                'cd /opt/mcp-demo && docker compose -f compose.hosted.yaml --env-file .hosted/docker.env logs --no-color'], text=True)
        else:
            logs = ''.join(p.read_text(errors='replace') for p in SECRETS_FILE.parent.glob('*.log'))
        check(not any(value in logs for value in [*TOKENS, *local.values()]), 'No issued tokens or local secrets in application logs')
    finally:
        require(api('POST', '/demo/reset', direct)[0] == 204, 'Final reset failed')
    check(ticket_data(direct)['total'] == 3, 'Acceptance run leaves the three fixed seed tickets')
    report = {'executed_at': datetime.now(timezone.utc).isoformat(), 'mode': 'live-http-form-login-pkce', 'mcp': MCP,
              'checks': RESULTS, 'total': len(RESULTS), 'passed': len(RESULTS)}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(str(len(RESULTS)) + ' live checks passed. Sanitized report: ' + str(report_path))


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        print('FAIL ' + (str(error) if isinstance(error, DemoError) else type(error).__name__), flush=True)
        raise SystemExit(1)
