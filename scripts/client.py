#!/usr/bin/env python3
"""Small real OAuth+PKCE / Streamable HTTP MCP client; tokens stay in process RAM."""
import argparse
import base64
from contextlib import contextmanager
import hashlib
from html.parser import HTMLParser
import http.cookiejar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
ISSUER = 'http://localhost:8080/realms/mcp-demo'
API = 'http://localhost:8081'
MCP = 'http://localhost:8082/mcp'
CALLBACK = 'http://127.0.0.1:8765/callback'


class DemoError(Exception):
    pass


def require(condition, label):
    if not condition:
        raise DemoError(label)


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        require((parsed.scheme, parsed.netloc) in [('http', 'localhost:8080'), ('http', '127.0.0.1:8765')],
                'OAuth redirect outside local allowlist')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Redirects are forbidden for API/token requests: Authorization must not be forwarded.
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def request(method, url, token=None, body=None, form=None, headers=None, basic=None, opener=None):
    values = dict(headers or {})
    if token:
        values['Authorization'] = 'Bearer ' + token
    if basic:
        values['Authorization'] = 'Basic ' + base64.b64encode((':'.join(basic)).encode()).decode()
    data = None
    if form is not None:
        data = urlencode(form).encode()
        values['Content-Type'] = 'application/x-www-form-urlencoded'
    elif body is not None:
        data = json.dumps(body).encode()
        values['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=values, method=method)
    transport = opener or urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))
    try:
        with transport.open(req, timeout=15) as response:
            return response.status, response.headers, response.read()
    except HTTPError as error:
        return error.code, error.headers, error.read()


def document(url):
    status, _, data = request('GET', url)
    require(status == 200, 'Discovery request failed')
    return json.loads(data)


def discover():
    status, headers, _ = request('POST', MCP, body={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
    require(status == 401, 'MCP must challenge unauthenticated requests')
    challenge = headers.get('WWW-Authenticate', '')
    match = re.search(r'resource_metadata="([^"]+)"', challenge)
    expected = 'http://localhost:8082/.well-known/oauth-protected-resource/mcp'
    require(match is not None and match.group(1) == expected, 'Invalid resource metadata challenge')
    resource = document(expected)
    require(resource.get('resource') == MCP and resource.get('authorization_servers') == [ISSUER], 'Resource metadata mismatch')
    return resource


class LocalCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    def return_ok_secure(self, cookie, req):
        # Keycloak marks localhost cookies Secure. Browsers treat localhost as trustworthy;
        # reproduce that behavior only for this exact loopback authority in the form driver.
        if urlparse(req.full_url).scheme == 'http' and urlparse(req.full_url).netloc == 'localhost:8080':
            return True
        return super().return_ok_secure(cookie, req)


class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}
        self.inside = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form' and attrs.get('id') == 'kc-form-login':
            self.inside = True
            self.action = attrs.get('action')
        if tag == 'input' and self.inside and attrs.get('type') == 'hidden' and attrs.get('name'):
            self.fields[attrs['name']] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.inside = False


def login(client='mcp-demo-client', user='demo', headless=False, resource=MCP):
    metadata = document(ISSUER + '/.well-known/openid-configuration')
    require(metadata.get('issuer') == ISSUER, 'Issuer discovery mismatch')
    require('S256' in metadata.get('code_challenge_methods_supported', []), 'PKCE S256 unavailable')
    for key in ['authorization_endpoint', 'token_endpoint']:
        require(metadata[key].startswith(ISSUER + '/protocol/openid-connect/'), 'Unexpected OAuth endpoint')
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    state = secrets.token_urlsafe(32)
    scopes = 'tickets.read tickets.write' if resource == API else 'mcp.access'
    query = {'client_id': client, 'response_type': 'code', 'redirect_uri': CALLBACK,
             'scope': scopes, 'state': state, 'code_challenge': challenge,
             'code_challenge_method': 'S256', 'resource': resource, 'prompt': 'login'}
    result = {}
    done = threading.Event()

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != '/callback':
                self.send_error(404)
                return
            params = parse_qs(parsed.query)
            # Bind the callback to this flow and the discovered issuer before exchanging any code.
            valid = params.get('state') == [state] and params.get('iss') == [ISSUER] and len(params.get('code', [])) == 1
            self.send_response(200 if valid else 400)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(('Login abgeschlossen. Dieses Fenster kann geschlossen werden.' if valid else 'Login abgelehnt.').encode())
            if valid:
                result['code'] = params['code'][0]
                done.set()

        def log_message(self, *args):
            pass  # Callback URLs contain authorization codes.

    server = ThreadingHTTPServer(('127.0.0.1', 8765), Callback)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = metadata['authorization_endpoint'] + '?' + urlencode(query)
        if headless:
            # Actual authorization endpoint + Keycloak login form + redirect, no password grant.
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar(policy=LocalCookiePolicy())),
                                                SafeRedirect(), urllib.request.ProxyHandler({}))
            status, _, html = request('GET', url, opener=opener)
            require(status == 200, 'Authorization endpoint failed')
            parser = LoginForm()
            parser.feed(html.decode())
            require(parser.action and parser.action.startswith(ISSUER + '/login-actions/'), 'Unexpected login form')
            local = json.loads((ROOT / '.local/secrets.json').read_text())
            fields = {**parser.fields, 'username': user, 'password': local[user + '_password']}
            status, _, _ = request('POST', parser.action, form=fields, opener=opener)
            require(status == 200, 'Keycloak login failed')
            require(done.wait(5), 'OAuth callback not received')
        else:
            print('Keycloak-Login im Browser geöffnet (Benutzer: ' + user + ').')
            require(webbrowser.open(url), 'Could not open browser')
            require(done.wait(180), 'OAuth login timed out')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    status, _, data = request('POST', metadata['token_endpoint'], form={
        'grant_type': 'authorization_code', 'client_id': client, 'redirect_uri': CALLBACK,
        'code': result['code'], 'code_verifier': verifier, 'resource': resource})
    require(status == 200, 'Authorization-code / PKCE exchange failed')
    tokens = json.loads(data)
    require(tokens.get('token_type', '').lower() == 'bearer' and 'access_token' in tokens, 'Invalid token response')
    return tokens['access_token']


def claims(token):
    """Diagnostics only. Resource servers perform cryptographic token validation."""
    payload = token.split('.')[1]
    return json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))


class McpClient:
    def __init__(self, token):
        self.token = token
        self.next_id = 1
        self.version = '2025-06-18'

    def call(self, method, params=None, notification=False):
        message = {'jsonrpc': '2.0', 'method': method}
        if not notification:
            message['id'] = self.next_id
            self.next_id += 1
        if params is not None:
            message['params'] = params
        status, _, data = request('POST', MCP, token=self.token, body=message,
            headers={'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': self.version})
        if notification:
            require(status == 202, 'MCP notification failed')
            return None
        require(status == 200, 'MCP HTTP request failed')
        answer = json.loads(data)
        require(answer.get('jsonrpc') == '2.0' and answer.get('id') == message['id'], 'MCP response mismatch')
        require('error' not in answer, 'MCP JSON-RPC error')
        return answer['result']

    def initialize(self):
        info = self.call('initialize', {'protocolVersion': self.version, 'capabilities': {},
                                       'clientInfo': {'name': 'local-pkce-demo', 'version': '0.1.0'}})
        require(info.get('protocolVersion') == self.version, 'Unexpected MCP version')
        self.call('notifications/initialized', notification=True)
        return info

    def tool(self, name, arguments):
        return self.call('tools/call', {'name': name, 'arguments': arguments})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless-login', action='store_true', help='Automate the real Keycloak login form (local fixtures only)')
    parser.add_argument('--reset', action='store_true')
    args = parser.parse_args()
    if args.reset:
        token = login('api-demo-client', headless=args.headless_login, resource=API)
        status, _, _ = request('POST', API + '/demo/reset', token=token)
        require(status == 204, 'Reset failed')
        print('Synthetische Tickets zurückgesetzt.')
        return
    discover()
    token = login(headless=args.headless_login)
    client = McpClient(token)
    client.initialize()
    print(json.dumps(client.call('tools/list'), ensure_ascii=False, indent=2))
    result = client.tool('list_tickets', {'limit': 20})
    require(not result.get('isError'), 'Ticket read failed')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Client fehlgeschlagen: ' + (str(error) if isinstance(error, DemoError) else type(error).__name__))
        raise SystemExit(1)
