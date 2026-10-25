"""Exercise the actual shell entrypoint with a shadowing, incompatible Python."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project with spaces'
        (self.root / 'scripts').mkdir(parents=True)
        shutil.copyfile(Path(__file__).resolve().parents[1] / 'demo', self.root / 'demo')
        (self.root / 'scripts/demo.py').write_text(
            'import json, subprocess, sys\n'
            'child = subprocess.check_output([sys.executable, "-c", '
            '"import sys, tomllib; print(sys.executable)"], text=True).strip()\n'
            'print(json.dumps({"parent": sys.executable, "child": child, "args": sys.argv[1:]}))\n')
        self.old = self.root / 'old python'
        self.new = self.root / 'new python'
        self.old.mkdir()
        self.new.mkdir()
        (self.old / 'python3').write_text('#!/bin/sh\nexit 1\n')
        (self.old / 'python3').chmod(0o755)
        (self.new / 'python3').symlink_to(sys.executable)
        self.env = {**os.environ, 'PATH': str(self.old) + ':' + str(self.new) + ':/usr/bin:/bin'}
        self.env.pop('DEMO_PYTHON', None)

    def launch(self, *args):
        return subprocess.run(['/bin/sh', str(self.root / 'demo'), *args], env=self.env,
                              capture_output=True, text=True, timeout=15)

    def assert_interpreter_and_children(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(Path(data['parent']).resolve(), Path(sys.executable).resolve())
        self.assertEqual(data['parent'], data['child'])
        return data

    def test_skips_old_first_python_and_preserves_interpreter_in_children(self):
        result = self.launch('agent', 'run', 'argument with spaces')
        data = self.assert_interpreter_and_children(result)
        self.assertEqual(data['args'], ['agent', 'run', 'argument with spaces'])

    def test_explicit_compatible_interpreter_works_with_old_path(self):
        self.env['PATH'] = str(self.old) + ':/usr/bin:/bin'
        self.env['DEMO_PYTHON'] = str(self.new / 'python3')
        self.assert_interpreter_and_children(self.launch('agent', 'run'))

    def test_unsuitable_explicit_interpreter_exits_before_project_imports(self):
        self.env['DEMO_PYTHON'] = str(self.old / 'python3')
        result = self.launch('agent', 'run')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Python 3.11', result.stderr)
        self.assertIn('DEMO_PYTHON', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
