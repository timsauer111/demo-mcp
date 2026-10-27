"""Only a proven pre-thread MCP OAuth failure may initiate one fresh login."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
import subprocess
import unittest
from unittest.mock import patch
import agent_client
from client import DemoError


STARTUP = ('Error: thread/start: thread/start failed: Fatal error: Failed to initialize session: '
           'required MCP servers failed to initialize: ticket_demo: '
           'OAuth refresh token was rejected: invalid_grant: Token is not active: OAuth authorization required')
SUCCESS = '\n'.join(json.dumps(e) for e in [
    {'type': 'thread.started'}, {'type': 'turn.started'},
    {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Beide Tools erfolgreich.'}},
    {'type': 'turn.completed'}])


def result(code=0, output='', error=''):
    return subprocess.CompletedProcess([], code, output, error)


class StartupClassificationTest(unittest.TestCase):
    def test_actual_cli_0160_stderr_only_invalid_grant(self):
        self.assertTrue(agent_client.startup_needs_login(result(1, error=STARTUP), []))

    def test_structured_startup_and_missing_login_are_recognized(self):
        for message in [STARTUP, STARTUP.replace('OAuth authorization required', 'Auth required')]:
            with self.subTest(message=message):
                self.assertTrue(agent_client.startup_needs_login(result(1), [{'type': 'error', 'message': message}]))

    def test_never_retries_after_thread_or_turn_or_items_or_unknown_output(self):
        for events in [[{'type': kind}] for kind in ['thread.started', 'turn.started', 'item.started', 'turn.failed']]:
            with self.subTest(events=events):
                self.assertFalse(agent_client.startup_needs_login(result(1, error=STARTUP), events))
        self.assertFalse(agent_client.startup_needs_login(result(1, error=STARTUP), None))
        self.assertIsNone(agent_client.events_from('unrecognized output'))

    def test_network_model_other_server_and_success_are_not_login_failures(self):
        for error in [STARTUP.replace('OAuth authorization required', 'connection refused'),
                      STARTUP.replace('ticket_demo:', 'another_server:'), 'Model quota exceeded', 'invalid_grant']:
            with self.subTest(error=error):
                self.assertFalse(agent_client.startup_needs_login(result(1, error=error), []))
        self.assertFalse(agent_client.startup_needs_login(result(0, error=STARTUP), []))


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.output = StringIO()
        self.errors = StringIO()
        self.addCleanup(patch.stopall)
        patch('sys.stdout', self.output).start()
        patch('sys.stderr', self.errors).start()
        patch.object(agent_client, 'command', side_effect=lambda action: [action]).start()
        self.interactive = patch.object(agent_client.sys.stdin, 'isatty', return_value=True).start()
        self.run = patch.object(agent_client.subprocess, 'run').start()

    def actions(self):
        return [c.args[0][0] for c in self.run.call_args_list]

    def test_invalid_grant_logout_browser_pkce_and_one_retry_succeed(self):
        self.run.side_effect = [result(1, error=STARTUP), result(), result(), result(output=SUCCESS)]
        agent_client.run_agent()
        self.assertEqual(self.actions(), ['run', 'logout', 'login', 'run'])
        self.assertIn('Beide Tools erfolgreich.', self.output.getvalue())
        self.assertNotIn('thread/start failed', self.errors.getvalue())
        self.assertTrue(all(c.kwargs['stdin'] == subprocess.DEVNULL for c in self.run.call_args_list))

    def test_second_auth_failure_stops_without_third_run_or_second_login(self):
        self.run.side_effect = [result(1, error=STARTUP), result(), result(), result(1, error=STARTUP)]
        with self.assertRaisesRegex(DemoError, 'kein weiterer Versuch'):
            agent_client.run_agent()
        self.assertEqual(self.actions(), ['run', 'logout', 'login', 'run'])

    def test_noninteractive_auth_failure_keeps_credentials_and_gives_login_command(self):
        self.interactive.return_value = False
        self.run.return_value = result(1, error=STARTUP)
        with self.assertRaisesRegex(DemoError, './demo agent login'):
            agent_client.run_agent()
        self.assertEqual(self.actions(), ['run'])

    def test_network_error_preserves_diagnostics_and_credentials(self):
        self.run.return_value = result(1, error='Keycloak connection refused')
        with self.assertRaises(DemoError):
            agent_client.run_agent()
        self.assertEqual(self.actions(), ['run'])
        self.assertIn('connection refused', self.errors.getvalue())

    def test_partial_agent_action_is_never_repeated(self):
        output = json.dumps({'type': 'item.started', 'item': {'type': 'mcp_tool_call'}})
        self.run.return_value = result(1, output=output, error=STARTUP)
        with self.assertRaises(DemoError):
            agent_client.run_agent()
        self.assertEqual(self.actions(), ['run'])

    def test_failed_or_timed_out_browser_login_does_not_restart_agent(self):
        for failure in [result(1), subprocess.TimeoutExpired(['login'], 180)]:
            with self.subTest(failure=type(failure).__name__):
                self.run.reset_mock()
                self.run.side_effect = [result(1, error=STARTUP), result(), failure]
                with self.assertRaisesRegex(DemoError, './demo agent login'):
                    agent_client.run_agent()
                self.assertEqual(self.actions(), ['run', 'logout', 'login'])

    def test_failed_logout_does_not_start_browser(self):
        self.run.side_effect = [result(1, error=STARTUP), result(1)]
        with self.assertRaisesRegex(DemoError, './demo agent logout'):
            agent_client.run_agent()
        self.assertEqual(self.actions(), ['run', 'logout'])

    def test_browser_interrupt_is_not_retried(self):
        self.run.side_effect = [result(1, error=STARTUP), result(), KeyboardInterrupt()]
        with self.assertRaises(KeyboardInterrupt):
            agent_client.run_agent()
        self.assertEqual(self.actions(), ['run', 'logout', 'login'])


if __name__ == '__main__':
    unittest.main()
