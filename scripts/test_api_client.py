"""Direct API CLI regressions; OAuth and HTTP are tested live separately."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
import unittest
from unittest.mock import patch
import api_client


class ApiClientTest(unittest.TestCase):
    def request_for(self, argv):
        parser = api_client.parser()
        return api_client.build_request(parser.parse_args(argv), parser)

    def test_read_routes_are_fixed_and_pagination_is_encoded(self):
        self.assertEqual(self.request_for(['list', '--status', 'OPEN', '--offset', '2', '--limit', '3']),
                         ('GET', '/tickets?offset=2&limit=3&status=OPEN', None, 200))
        self.assertEqual(self.request_for(['get', '7']), ('GET', '/tickets/7', None, 200))

    def test_write_routes_and_payloads(self):
        self.assertEqual(self.request_for(['create', '--title', 'Synthetic']),
                         ('POST', '/tickets', {'title': 'Synthetic', 'description': '', 'status': 'OPEN'}, 201))
        self.assertEqual(self.request_for(['patch', '7', '--status', 'CLOSED']),
                         ('PATCH', '/tickets/7', {'status': 'CLOSED'}, 200))
        self.assertEqual(self.request_for(['delete', '7']), ('DELETE', '/tickets/7', None, 204))

    def test_rejects_invalid_ids_pagination_and_empty_patch(self):
        for argv in [['get', '../admin'], ['get', '0'], ['list', '--limit', '101'],
                     ['list', '--offset', '-1'], ['patch', '1']]:
            with self.subTest(argv=argv), redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                self.request_for(argv)

    def test_pkce_api_login_and_token_remain_internal(self):
        output = StringIO()
        with patch.object(api_client, 'login', return_value='unit-sensitive-token') as login, \
             patch.object(api_client, 'request', return_value=(200, {}, b'{"tickets": []}')) as request, \
             redirect_stdout(output):
            api_client.main(['--headless-login', 'list'])
        login.assert_called_once_with('api-demo-client', headless=True, resource=api_client.API)
        request.assert_called_once_with('GET', api_client.API + '/tickets?offset=0&limit=20',
                                        token='unit-sensitive-token', body=None)
        self.assertIn('HTTP 200 GET', output.getvalue())
        self.assertNotIn('unit-sensitive-token', output.getvalue())

    def test_failed_api_status_causes_failure_without_headers(self):
        output = StringIO()
        with patch.object(api_client, 'login', return_value='unit-sensitive-token'), \
             patch.object(api_client, 'request', return_value=(403, {'Authorization': 'secret'}, b'')), \
             redirect_stdout(output), self.assertRaises(api_client.DemoError):
            api_client.main(['delete', '1'])
        self.assertIn('HTTP 403', output.getvalue())
        self.assertNotIn('secret', output.getvalue())


if __name__ == '__main__':
    unittest.main()
