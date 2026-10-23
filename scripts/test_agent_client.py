"""Meaningful client-isolation and owned Keycloak reconciliation regressions."""
import copy
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse
import agent_client
from client import DemoError
import register_agent
from setup import realm_config


class AgentCommandTest(unittest.TestCase):
    def test_list_targets_only_this_connection(self):
        with patch.object(agent_client.shutil, 'which', return_value='/test/codex'):
            command = agent_client.command('list')
        self.assertEqual(command[-3:], ['mcp', 'get', 'ticket_demo'])
        self.assertIn('mcp_oauth_credentials_store="keyring"', command)
        self.assertNotIn('--oauth-client-secret', command)

    def test_agent_run_ignores_global_config_and_disables_shell(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(agent_client, 'ROOT', Path(temp)), \
             patch.object(agent_client.shutil, 'which', return_value='/test/codex'), \
             patch.object(agent_client, 'overrides', return_value=['-c', 'mcp_servers={}']):
            (Path(temp) / '.local').mkdir()
            command = agent_client.command('run')
        self.assertIn('--ignore-user-config', command)
        self.assertIn('--ephemeral', command)
        self.assertIn('features.shell_tool=false', command)
        self.assertIn('project_doc_max_bytes=0', command)
        self.assertIn('read-only', command)
        self.assertIn('get_ticket', command[-1])
        self.assertIn('list_tickets', command[-1])


class ReconcileTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / '.local').mkdir(mode=0o700)
        self.values = {k: 'unit-fixture' for k in ['mcp_client_secret', 'admin_password',
                      'demo_password', 'reader_password', 'unprivileged_password']}
        self.realm = realm_config(self.values)
        self.desired = register_agent.desired(self.values)
        (self.root / '.local/secrets.json').write_text(json.dumps(self.values))
        # Start from an older import without the external client.
        self.realm['clients'] = [c for c in self.realm['clients'] if c['clientId'] != register_agent.CLIENT_ID]
        (self.root / '.local/realm.json').write_text(json.dumps(self.realm))
        self.client = None
        self.default = []
        self.optional = []
        self.mappers = []
        self.mutations = []
        self.realm_roles = [{'name': 'offline_access', 'id': 'role-offline'}]

    def tearDown(self):
        self.temp.cleanup()

    def reply(self, value=None, status=200):
        return status, {}, json.dumps(value).encode() if value is not None else b''

    def request(self, method, url, **kwargs):
        if url.endswith('/realms/master/protocol/openid-connect/token'):
            return self.reply({'access_token': 'unit-admin-fixture'})
        path = urlparse(url).path.removeprefix('/admin/realms/mcp-demo')
        body = kwargs.get('body')
        if method != 'GET':
            self.mutations.append((method, path))
        if path == '/users' and method == 'GET':
            return self.reply([{'id': 'demo-user', 'email': 'demo@example.invalid'}])
        if path == '/roles/offline_access':
            return self.reply({'name': 'offline_access', 'id': 'role-offline'})
        if path == '/users/demo-user/role-mappings/realm/composite':
            return self.reply(self.realm_roles)
        if path == '/users/demo-user/role-mappings/realm' and method == 'POST':
            self.realm_roles.extend(copy.deepcopy(body))
            return self.reply(status=204)
        if path == '/clients' and method == 'GET':
            return self.reply([self.client] if self.client else [])
        if path == '/clients' and method == 'POST':
            self.client = {**copy.deepcopy(body), 'id': 'owned-id'}
            self.default = [{'name': 'mcp.access', 'id': 'scope-mcp'}]
            self.mappers = [{**copy.deepcopy(m), 'id': 'mapper-' + str(i)} for i, m in enumerate(body['protocolMappers'])]
            return self.reply(status=201)
        if path == '/client-scopes':
            return self.reply([{'name': 'mcp.access', 'id': 'scope-mcp'}, {'name': 'offline_access', 'id': 'scope-offline'}])
        if path == '/clients/owned-id':
            if method == 'PUT':
                self.client.update(copy.deepcopy(body))
                return self.reply(status=204)
            return self.reply(self.client)
        for kind in ['default', 'optional']:
            prefix = '/clients/owned-id/' + kind + '-client-scopes'
            scopes = getattr(self, kind)
            if path == prefix:
                return self.reply(scopes)
            if path.startswith(prefix + '/'):
                scope_id = path.rsplit('/', 1)[1]
                if method == 'DELETE':
                    scopes[:] = [s for s in scopes if s['id'] != scope_id]
                else:
                    scopes.append({'name': {'scope-mcp': 'mcp.access', 'scope-offline': 'offline_access'}[scope_id], 'id': scope_id})
                return self.reply(status=204)
        prefix = '/clients/owned-id/protocol-mappers/models'
        if path == prefix and method == 'GET':
            return self.reply(self.mappers)
        if path == prefix and method == 'POST':
            self.mappers.append({**copy.deepcopy(body), 'id': 'new-' + body['name']})
            return self.reply(status=201)
        if path.startswith(prefix + '/'):
            mapper_id = path.rsplit('/', 1)[1]
            self.mappers[:] = [m for m in self.mappers if m['id'] != mapper_id]
            if method == 'PUT':
                self.mappers.append(copy.deepcopy(body))
            return self.reply(status=204)
        raise AssertionError('Unexpected admin operation')

    def reconcile(self):
        with patch.object(register_agent, 'ROOT', self.root), patch.object(register_agent, 'request', side_effect=self.request), \
             redirect_stdout(StringIO()):
            register_agent.reconcile()

    def test_repeated_setup_preserves_other_clients_users_and_secrets(self):
        secret_before = (self.root / '.local/secrets.json').read_bytes()
        self.reconcile()
        import_before = (self.root / '.local/realm.json').read_bytes()
        state_before = copy.deepcopy((self.client, self.default, self.optional, self.mappers))
        self.reconcile()
        self.assertEqual(state_before, (self.client, self.default, self.optional, self.mappers))
        self.assertEqual(import_before, (self.root / '.local/realm.json').read_bytes())
        self.assertEqual(secret_before, (self.root / '.local/secrets.json').read_bytes())
        current = json.loads(import_before)
        self.assertEqual(current['users'], self.realm['users'])
        self.assertEqual([c for c in current['clients'] if c['clientId'] != register_agent.CLIENT_ID], self.realm['clients'])
        self.assertEqual((self.root / '.local/realm.json').stat().st_mode & 0o777, 0o600)

    def test_rejects_foreign_client_before_any_mutation(self):
        self.client = {**self.desired, 'id': 'owned-id', 'attributes': {}}
        with self.assertRaises(DemoError):
            self.reconcile()
        self.assertEqual(self.mutations, [])

    def test_rejects_foreign_import_client_before_admin_access(self):
        self.realm['clients'].append({'clientId': register_agent.CLIENT_ID, 'attributes': {}})
        path = self.root / '.local/realm.json'
        path.write_text(json.dumps(self.realm))
        with patch.object(register_agent, 'ROOT', self.root), patch.object(register_agent, 'request') as network:
            with self.assertRaises(DemoError):
                register_agent.reconcile()
            network.assert_not_called()
        self.assertEqual(json.loads(path.read_text()), self.realm)

    def test_rejects_unexpected_import_user_before_admin_access(self):
        self.realm['users'][0]['email'] = 'someone@example.invalid'
        (self.root / '.local/realm.json').write_text(json.dumps(self.realm))
        with patch.object(register_agent, 'ROOT', self.root), patch.object(register_agent, 'request') as network:
            with self.assertRaises(DemoError):
                register_agent.reconcile()
            network.assert_not_called()

    def test_rejects_unexpected_live_user_before_mutations(self):
        original = self.request
        def network(method, url, **kwargs):
            if urlparse(url).path.endswith('/users'):
                return self.reply([{'id': 'foreign-user', 'email': 'someone@example.invalid'}])
            return original(method, url, **kwargs)
        with patch.object(register_agent, 'ROOT', self.root), patch.object(register_agent, 'request', side_effect=network):
            with self.assertRaises(DemoError):
                register_agent.reconcile()
        self.assertEqual(self.mutations, [])

    def test_grants_offline_role_only_to_synthetic_demo_account(self):
        self.realm_roles = [{'name': 'preserved-role'}]
        self.reconcile()
        self.assertEqual({r['name'] for r in self.realm_roles}, {'preserved-role', 'offline_access'})
        grants = [(method, path) for method, path in self.mutations if path.startswith('/users/')]
        self.assertEqual(grants, [('POST', '/users/demo-user/role-mappings/realm')])
        before = list(self.realm_roles)
        self.reconcile()
        self.assertEqual(before, self.realm_roles)

    def test_removes_extra_scope_and_hardcoded_mapper_only_from_owned_client(self):
        self.reconcile()
        self.default = [{'name': 'tickets.write', 'id': 'write'}]
        self.optional = [{'name': 'tickets.write', 'id': 'write'}]
        self.mappers.append({'name': 'hardcoded-write', 'id': 'extra', 'protocolMapper': 'oidc-hardcoded-role-mapper'})
        self.mutations.clear()
        self.reconcile()
        self.assertEqual(self.default, [{'name': 'mcp.access', 'id': 'scope-mcp'}])
        self.assertEqual(self.optional, [{'name': 'offline_access', 'id': 'scope-offline'}])
        self.assertEqual({m['name'] for m in self.mappers}, {m['name'] for m in self.desired['protocolMappers']})
        self.assertTrue(all(path.startswith('/clients/owned-id') for _, path in self.mutations))


if __name__ == '__main__':
    unittest.main()
