"""Supervisor regressions: no service changes on preflight failure; preserve live PIDs."""
from contextlib import ExitStack
import tempfile
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch, Mock
import demo


class SupervisorTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.local = self.root / '.local'
        self.local.mkdir()
        self.stack.enter_context(patch.object(demo, 'ROOT', self.root))
        self.stack.enter_context(patch.object(demo, 'LOCAL', self.local))
        self.stack.enter_context(patch.object(demo.time, 'sleep'))

    def tearDown(self):
        self.stack.close()

    def jar(self, module):
        jar = self.root / module / 'target' / (module + '-0.1.0-SNAPSHOT.jar')
        jar.parent.mkdir(parents=True)
        jar.touch()

    def test_second_missing_jar_is_detected_before_compose_or_start(self):
        self.jar('ticket-api')
        with patch.object(demo.sys, 'argv', ['demo', 'up']), patch.object(demo, 'compose') as compose, \
             patch.object(demo.subprocess, 'run'), patch.object(demo.socket, 'socket') as socket, \
             patch.object(demo.subprocess, 'Popen') as popen:
            socket.return_value.__enter__.return_value.connect_ex.return_value = 1
            with self.assertRaisesRegex(SystemExit, 'Build first'):
                demo.main()
            compose.assert_not_called()
            popen.assert_not_called()

    def test_occupied_second_port_is_detected_before_start(self):
        self.jar('ticket-api')
        self.jar('mcp-server')
        with patch.object(demo.sys, 'argv', ['demo', 'up']), patch.object(demo, 'compose') as compose, \
             patch.object(demo.subprocess, 'run'), patch.object(demo.socket, 'socket') as socket, \
             patch.object(demo.subprocess, 'Popen') as popen:
            socket.return_value.__enter__.return_value.connect_ex.side_effect = [1, 0]
            with self.assertRaisesRegex(SystemExit, '8082'):
                demo.main()
            compose.assert_not_called()
            popen.assert_not_called()

    def test_startup_failure_rolls_back_app_processes(self):
        for module in ['ticket-api', 'mcp-server']:
            self.jar(module)
        with patch.object(demo.sys, 'argv', ['demo', 'up']), patch.object(demo, 'compose'), \
             patch.object(demo.subprocess, 'run'), patch.object(demo.socket, 'socket') as socket, \
             patch.object(demo.subprocess, 'Popen') as popen, patch.object(demo, 'java_env', return_value={}), \
             patch.object(demo, 'wait_url', side_effect=[None, SystemExit('start failed')]), \
             patch.object(demo, 'stop_apps') as stop:
            socket.return_value.__enter__.return_value.connect_ex.return_value = 1
            popen.return_value.pid = 1234
            with self.assertRaises(SystemExit):
                demo.main()
            stop.assert_called_once()

    def test_stop_preserves_pid_file_when_process_does_not_exit(self):
        pidfile = self.local / 'mcp-server.pid'
        pidfile.write_text('1234')
        result = subprocess.CompletedProcess([], 0, stdout=str(self.root / 'mcp-server/target') + '/app.jar')
        with patch.object(demo.subprocess, 'run', return_value=result), patch.object(demo.os, 'kill'):
            with self.assertRaisesRegex(SystemExit, 'PID file preserved'):
                demo.stop_apps()
            self.assertTrue(pidfile.exists())

    def test_stop_does_not_signal_a_reused_pid(self):
        pidfile = self.local / 'mcp-server.pid'
        pidfile.write_text('1234')
        with patch.object(demo.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='other-program')), \
             patch.object(demo.os, 'kill') as kill:
            demo.stop_apps()
            kill.assert_not_called()
            self.assertFalse(pidfile.exists())


if __name__ == '__main__':
    unittest.main()
