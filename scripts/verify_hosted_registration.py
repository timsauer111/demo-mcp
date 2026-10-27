#!/usr/bin/env python3
"""Live DCR, real PKCE login and read-only exchange proof for newly registered app clients."""
import base64
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import http.cookiejar
import json
import os
import re
import secrets
import subprocess
from urllib.parse import parse_qs, urlencode, urlparse
import urllib.request
from client import API, ISSUER, MCP, SECRETS_FILE, DemoError, LoginForm, McpClient, NoRedirect, claims, request, require

CALLBACK = 'https://chatgpt.com/connector_platform_oauth_redirect'
RESULTS = []
SENSITIVE = []


def check(condition, label):
    require(condition, label)
    RESULTS.append({'check': label, 'result': 'PASS'})
    print('PASS ' + label, flush=True)


class ConsentForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}
        self.inside = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.action = attrs.get('action')
            self.inside = True
        if tag == 'input' and self.inside and attrs.get('name') and attrs.get('type') == 'hidden':
            self.fields[attrs['name']] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.inside = False


def login(registration, values, callback=CALLBACK, scope='openid mcp.access offline_access', resource=MCP):
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    query = {'client_id': registration['client_id'], 'redirect_uri': callback,
             'response_type': 'code', 'scope': scope, 'state': state,
             'resource': resource, 'code_challenge': challenge, 'code_challenge_method': 'S256'}
    for changes in [{'code_challenge_method': 'plain'}, {'code_challenge_method': None, 'code_challenge': None}]:
        negative = {k: v for k, v in {**query, **changes}.items() if v is not None}
        status, headers, data = request('GET', ISSUER + '/protocol/openid-connect/auth?' + urlencode(negative))
        error = parse_qs(urlparse(headers.get('Location', '')).query).get('error')
        check(status in (302, 400) and (error or b'Invalid' in data or b'Missing' in data),
              'New app client rejects absent or plain PKCE: ' + str(changes['code_challenge_method']))
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                        urllib.request.ProxyHandler({}))
    status, _, html = request('GET', ISSUER + '/protocol/openid-connect/auth?' + urlencode(query), opener=opener)
    require(status == 200, 'App authorization endpoint failed')
    form = LoginForm()
    form.feed(html.decode())
    require(form.action and form.action.startswith(ISSUER + '/login-actions/'), 'Unexpected app login action')
    status, headers, html = request('POST', form.action, opener=opener,
                                   form={**form.fields, 'username': 'demo', 'password': values['demo_password']})
    for _ in range(4):
        location = headers.get('Location', '')
        if status == 302 and location.startswith(callback + '?'):
            break
        if status == 302 and location.startswith(ISSUER + '/'):
            status, headers, html = request('GET', location, opener=opener)
            continue
        consent = ConsentForm()
        consent.feed(html.decode())
        action = consent.action
        if action and action.startswith('/'):
            parsed = urlparse(ISSUER)
            action = parsed.scheme + '://' + parsed.netloc + action
        require(status == 200 and action and action.startswith(ISSUER + '/login-actions/'),
                'Unexpected app consent action')
        status, headers, html = request('POST', action, opener=opener, form={**consent.fields, 'accept': 'Yes'})
    parsed_callback = urlparse(headers.get('Location', ''))
    params = parse_qs(parsed_callback.query)
    require(status == 302 and parsed_callback.scheme + '://' + parsed_callback.netloc + parsed_callback.path == callback
            and params.get('state') == [state] and params.get('iss') == [ISSUER] and len(params.get('code', [])) == 1,
            'App OAuth callback or issuer binding failed')
    # Do not visit the external callback: redeem our own test code directly.
    basic = (registration['client_id'], registration['client_secret']) if registration.get('client_secret') else None
    status, _, data = request('POST', ISSUER + '/protocol/openid-connect/token', basic=basic, form={
        'grant_type': 'authorization_code', 'client_id': registration['client_id'], 'redirect_uri': callback,
        'code': params['code'][0], 'code_verifier': verifier, 'resource': resource})
    require(status == 200, 'Fresh app client PKCE code exchange failed')
    tokens = json.loads(data)
    SENSITIVE.extend(tokens[k] for k in ['access_token', 'refresh_token', 'id_token'] if k in tokens)
    check('refresh_token' in tokens, 'Fresh app client completes PKCE and receives refresh credentials')
    return tokens['access_token']


def run():
    report = SECRETS_FILE.parent / 'registration-verification.json'
    report.unlink(missing_ok=True)
    values = json.loads(SECRETS_FILE.read_text())
    endpoint = ISSUER + '/clients-registrations/openid-connect'
    metadata = {'client_name': 'mcp-app-verification-' + secrets.token_hex(6), 'redirect_uris': [CALLBACK],
                'response_types': ['code'], 'grant_types': ['authorization_code', 'refresh_token'],
                'scope': 'openid mcp.access offline_access'}
    for changed in [{'redirect_uris': ['http://remote-client.example/callback']},
                    {'redirect_uris': ['http://chatgpt.com/callback']},
                    {'redirect_uris': ['https://chatgpt.com/*']}, {'scope': 'tickets.write'}]:
        status, _, _ = request('POST', endpoint, body={**metadata, **changed})
        check(status in (400, 403), 'DCR rejects forbidden registration: ' + str(next(iter(changed))))
    profiles = [(CALLBACK, 'client_secret_basic'),
                ('https://claude.ai/api/mcp/auth_callback', 'none'),
                ('https://gemini.google.com/callback', 'none'),
                ('https://another-client.example/callback', 'none'),
                ('http://localhost:54321/callback', 'none'),
                ('http://127.0.0.1:54322/oauth/callback', 'none'),
                ('http://[::1]:54323/callback', 'none')]
    for callback, method in profiles:
        metadata = {**metadata, 'redirect_uris': [callback]}
        status, _, data = request('POST', endpoint, body={**metadata, 'token_endpoint_auth_method': method})
        require(status == 201, 'Fresh app DCR failed: ' + method)
        registration = json.loads(data)
        SENSITIVE.extend(registration[k] for k in ['client_secret', 'registration_access_token'] if k in registration)
        require(registration['registration_client_uri'].startswith(endpoint + '/'), 'Unexpected registration URI')
        check(True, 'App DCR creates a fresh client: ' + callback + ' (' + method + ')')
        try:
            status, _, _ = request('PUT', registration['registration_client_uri'],
                token=registration['registration_access_token'],
                body={**metadata, 'redirect_uris': ['http://remote-client.example/callback']})
            check(status == 400, 'Registration update cannot introduce remote HTTP callbacks')
            token = login(registration, values, callback)
            check(MCP in claims(token).get('aud', []) and claims(token).get('resource_access', {}).get('mcp-server', {}).get('roles') == ['mcp.access'],
                  'New app token is bound to the MCP resource and role')
            check(request('GET', API + '/tickets', token=token)[0] == 401,
                  'New app token A is rejected directly at the backend')
            basic = ((registration['client_id'], registration['client_secret'])
                     if registration.get('client_secret') else None)
            status, _, _ = request('POST', ISSUER + '/protocol/openid-connect/token', basic=basic, form={
                'grant_type': 'password', 'client_id': registration['client_id'],
                'username': 'demo', 'password': values['demo_password']})
            check(status == 400, 'New app client cannot use a password grant')
            mcp = McpClient(token)
            mcp.initialize()
            check({t['name'] for t in mcp.call('tools/list')['tools']} == {'list_tickets', 'get_ticket'},
                  'New app client sees exactly the two read tools')
            check(not mcp.tool('list_tickets', {'limit': 3}).get('isError')
                  and not mcp.tool('get_ticket', {'id': 1}).get('isError'), 'Fresh app client executes both real MCP tools')
            status, _, data = request('POST', ISSUER + '/protocol/openid-connect/token',
                basic=('mcp-server', values['mcp_client_secret']), form={
                    'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange', 'subject_token': token,
                    'subject_token_type': 'urn:ietf:params:oauth:token-type:access_token',
                    'requested_token_type': 'urn:ietf:params:oauth:token-type:access_token', 'audience': 'tickets-api'})
            require(status == 200, 'New app token exchange failed')
            backend = json.loads(data)['access_token']
            SENSITIVE.append(backend)
            status, _, before = request('GET', API + '/tickets?limit=100', token=backend)
            require(status == 200, 'New app exchanged token cannot read')
            for verb, path, body in [('POST', '/tickets', {'title': 'forbidden', 'description': '', 'status': 'OPEN'}),
                                     ('PATCH', '/tickets/1', {'status': 'CLOSED'}), ('DELETE', '/tickets/1', None),
                                     ('POST', '/demo/reset', None)]:
                status, _, _ = request(verb, API + path, token=backend, body=body)
                check(status == 403, 'Exact new-app exchange token: ' + verb + ' ' + path + ' -> 403')
                status, _, after = request('GET', API + '/tickets?limit=100', token=backend)
                check(status == 200 and json.loads(after) == json.loads(before), 'New-app data unchanged after ' + verb)
            status, _, _ = request('PUT', registration['registration_client_uri'],
                token=registration['registration_access_token'], body={**metadata, 'scope': 'tickets.write',
                                                                      'token_endpoint_auth_method': method})
            check(status == 403, 'Registered app cannot add a write scope later')
        finally:
            status, _, _ = request('DELETE', registration['registration_client_uri'], token=registration['registration_access_token'])
            check(status == 204, 'Test app registration removed without changing other clients')
    for callback in ['https://oauth.pstmn.io/v1/callback', 'https://oauth.pstmn.io/v1/browser-callback']:
        api_token = login({'client_id': 'api-demo-client'}, values, callback,
                          scope='tickets.read tickets.write', resource=API)
        check(request('GET', API + '/tickets', token=api_token)[0] == 200,
              'Public REST API login supports registered Postman callback: ' + callback)
        status, headers, data = request('POST', API + '/tickets', token=api_token, body={
            'title': 'Public API OAuth verification', 'description': 'synthetic', 'status': 'OPEN'})
        check(status == 201 and headers.get('Location', '').startswith('/api/tickets/'),
              'Public API token creates a ticket with the public Location path')
        ticket_id = json.loads(data)['id']
        try:
            check(request('PATCH', API + '/tickets/' + str(ticket_id), token=api_token,
                          body={'status': 'CLOSED'})[0] == 200, 'Public API token updates its synthetic ticket')
        finally:
            check(request('DELETE', API + '/tickets/' + str(ticket_id), token=api_token)[0] == 204,
                  'Public API token deletes its synthetic ticket')
    host = os.environ.get('DEMO_LOG_SSH_HOST')
    require(host and re.fullmatch(r'[a-zA-Z0-9_][a-zA-Z0-9_.@-]*', host), 'Operator SSH log verification required')
    logs = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', host,
        'cd /opt/mcp-demo && docker compose -f compose.hosted.yaml --env-file .hosted/docker.env logs --no-color'], text=True)
    check(not any(secret in logs for secret in [*SENSITIVE, *values.values()]), 'No new-app credentials or issued tokens in container logs')
    report.write_text(json.dumps({'executed_at': datetime.now(timezone.utc).isoformat(),
        'mode': 'public-dcr-and-real-pkce-form-login', 'mcp': MCP, 'checks': RESULTS,
        'passed': len(RESULTS), 'total': len(RESULTS)}, indent=2) + '\n')
    print(str(len(RESULTS)) + ' live app-registration checks passed.')


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        print('FAIL ' + (str(error) if isinstance(error, DemoError) else type(error).__name__))
        raise SystemExit(1)
