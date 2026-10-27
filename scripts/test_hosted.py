"""Hosting regressions: preserve the realm, PKCE and the exchange permission ceiling."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse
import client
import hosted
import hosted_setup
import hosted_registration


class HostedSetupTest(unittest.TestCase):
    def test_repeated_setup_preserves_credentials_and_read_only_exchange(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            args = (root, 'mcp.example.test', '192.0.2.1', hosted.CADDY, hosted.POSTGRES)
            hosted_setup.setup(*args)
            before = {p.name: p.read_bytes() for p in (root / '.hosted').iterdir()}
            hosted_setup.setup(*args)
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / '.hosted').iterdir()})
            realm = json.loads(before['realm.json'])
            exchange = next(c for c in realm['clients'] if c['clientId'] == 'mcp-server')
            self.assertFalse(exchange['fullScopeAllowed'])
            self.assertEqual(exchange['defaultClientScopes'], ['tickets.read'])
            self.assertEqual(exchange['optionalClientScopes'], [])
            codex = next(c for c in realm['clients'] if c['clientId'] == 'codex-demo-client')
            self.assertEqual(codex['redirectUris'], ['http://127.0.0.1:8766/callback'])
            self.assertEqual(codex['attributes']['pkce.code.challenge.method'], 'S256')
            self.assertFalse(codex['directAccessGrantsEnabled'])
            self.assertTrue(realm['bruteForceProtected'])
            audience = next(m for m in codex['protocolMappers'] if m['name'] == 'resource-audience')
            self.assertEqual(audience['config']['included.custom.audience'], 'https://mcp.example.test/mcp')
            self.assertEqual((root / '.hosted/secrets.json').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                hosted_setup.setup(root, 'other.example.test', '192.0.2.1', hosted.CADDY, hosted.POSTGRES)
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / '.hosted').iterdir()})

    def test_oauth_redirects_allow_only_configured_issuer_and_exact_callback(self):
        handler = client.SafeRedirect()
        with patch.object(client, 'ISSUER', 'https://mcp.example.test/auth/realms/mcp-demo'):
            for url in ['http://mcp.example.test/auth', 'https://attacker.test/', 'http://127.0.0.1:8765/evil']:
                with self.assertRaises(client.DemoError):
                    handler.redirect_request(None, None, 302, '', {}, url)


class InstallTest(unittest.TestCase):
    def test_install_preserves_existing_config_and_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            config_path = root / 'config.toml'
            original = 'model = "test"\n[mcp_servers.other]\nurl = "https://other.example/mcp"\n'
            config_path.write_text(original)
            with patch.dict(hosted.os.environ, {'CODEX_HOME': directory}), patch.object(hosted, 'LOCAL', root):
                hosted.install()
                self.assertTrue(config_path.read_text().startswith(original))
                installed = hosted.tomllib.loads(config_path.read_text())
                self.assertEqual(set(installed['mcp_servers']), {'other', hosted.NAME})
                self.assertNotIn('enabled_tools', installed['mcp_servers'][hosted.NAME])
                with self.assertRaises(client.DemoError):
                    hosted.install()


class AppRegistrationTest(unittest.TestCase):
    def test_mapper_comparison_accepts_only_keycloak_defaults(self):
        wanted = {'name': 'subject', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-sub-mapper',
                  'config': {'access.token.claim': 'true'}}
        actual = {**wanted, 'id': 'server-id', 'config': {**wanted['config'], 'introspection.token.claim': 'true'}}
        self.assertTrue(hosted_registration.mapper_matches(actual, wanted))
        actual['config']['included.custom.audience'] = 'tickets-api'
        self.assertFalse(hosted_registration.mapper_matches(actual, wanted))

    def test_registration_is_provider_neutral_but_keeps_mcp_only_scopes(self):
        policies = hosted_registration.registration_policies()
        self.assertNotIn('trusted-hosts', policies)
        scopes = policies['allowed-client-templates']
        self.assertEqual(scopes['allow-default-scopes'], ['false'])
        self.assertEqual(set(scopes['allowed-client-scopes']), {'openid', 'mcp.access', 'offline_access'})
        self.assertEqual(policies['allowed-protocol-mappers']['allowed-protocol-mapper-types'], [])

    def test_oauth_profile_enforces_pkce_without_password_or_implicit_grants(self):
        profile = hosted_registration.oauth_profile()
        executors = {e['executor']: e['configuration'] for e in profile['executors']}
        self.assertTrue(executors['pkce-enforcer']['auto-configure'])
        self.assertTrue(executors['reject-ropc-grant']['auto-configure'])
        self.assertTrue(executors['reject-implicit-grant']['auto-configure'])
        self.assertTrue(executors['secure-redirect-uris-enforcer']['allow-http-scheme'])
        self.assertTrue(executors['secure-redirect-uris-enforcer']['allow-ipv4-loopback-address'])
        self.assertFalse(executors['secure-redirect-uris-enforcer']['allow-wildcard-context-path'])
        self.assertIn(profile['name'], hosted_registration.oauth_policy()['profiles'])
        condition = hosted_registration.oauth_policy()['conditions'][0]
        self.assertEqual(condition['condition'], 'client-updater-context')
        self.assertEqual(set(condition['configuration']['update-client-source']),
                         {'ByAnonymous', 'ByRegistrationAccessToken'})
