#!/usr/bin/env python3
"""Local process supervisor. Secrets are never passed on the command line."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
os.umask(0o077)


def java_env():
    env = os.environ.copy()
    if not env.get('JAVA_HOME') and sys.platform == 'darwin':
        env['JAVA_HOME'] = subprocess.check_output(['/usr/libexec/java_home', '-v', '21'], text=True).strip()
    if env.get('JAVA_HOME'):
        env['PATH'] = env['JAVA_HOME'] + '/bin:' + env['PATH']
    return env


def compose(*args):
    return subprocess.run(['docker', 'compose', '--env-file', str(LOCAL / 'docker.env'), *args], cwd=ROOT, check=True)


def wait_url(url, seconds=180):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise SystemExit('Local service did not become ready: ' + url + '; inspect .local/*.log')


def stop_apps():
    for module in ['mcp-server', 'ticket-api']:
        pidfile = LOCAL / (module + '.pid')
        if not pidfile.exists():
            continue
        pid = int(pidfile.read_text())
        # Do not kill a reused PID belonging to another program.
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True)
        if str(ROOT / module / 'target') in result.stdout:
            os.kill(pid, signal.SIGTERM)
            for _ in range(100):
                result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True)
                if str(ROOT / module / 'target') not in result.stdout:
                    break
                time.sleep(.1)
            else:
                raise SystemExit(f'{module} still running; PID file preserved for retry.')
        pidfile.unlink(missing_ok=True)


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else 'help'
    if command == 'setup':
        subprocess.run([sys.executable, 'scripts/setup.py'], cwd=ROOT, check=True)
    elif command == 'build':
        subprocess.run([str(ROOT / 'mvnw'), '-B', '-ntp', 'verify'], cwd=ROOT, env=java_env(), check=True)
    elif command == 'up':
        subprocess.run([sys.executable, 'scripts/setup.py'], cwd=ROOT, check=True)
        services = [('ticket-api', 8081), ('mcp-server', 8082)]
        # Preflight every local application before starting any service.
        for module, port in services:
            jar = ROOT / module / 'target' / (module + '-0.1.0-SNAPSHOT.jar')
            if not jar.exists():
                raise SystemExit('Build first: ./demo build')
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1', port)) == 0:
                    raise SystemExit(f'Port {port} already occupied. Run ./demo status and ./demo stop first.')
        compose('up', '-d')
        wait_url('http://localhost:8080/realms/mcp-demo/.well-known/openid-configuration')
        try:
            for module, port in services:
                jar = ROOT / module / 'target' / (module + '-0.1.0-SNAPSHOT.jar')
                env = java_env()
                if module == 'mcp-server':
                    env['MCP_CLIENT_SECRET'] = json.loads((LOCAL / 'secrets.json').read_text())['mcp_client_secret']
                java = str(Path(env['JAVA_HOME']) / 'bin/java') if env.get('JAVA_HOME') else 'java'
                with (LOCAL / (module + '.log')).open('ab') as log:
                    proc = subprocess.Popen([java, '-jar', str(jar)], cwd=ROOT, env=env,
                                            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
                (LOCAL / (module + '.pid')).write_text(str(proc.pid))
                wait_url(f'http://localhost:{port}/health', 60)
        except BaseException:
            stop_apps()
            raise
        print('Ready: Keycloak http://localhost:8080 | API http://localhost:8081 | MCP http://localhost:8082/mcp')
    elif command in ['stop', 'down']:
        stop_apps()
        if command == 'down':
            compose('down')  # Keep the PostgreSQL volume and secrets.
    elif command == 'status':
        compose('ps')
        for port in [8081, 8082]:
            try:
                with urllib.request.urlopen(f'http://localhost:{port}/health', timeout=2) as r:
                    print(f'localhost:{port}: {r.status}')
            except Exception:
                print(f'localhost:{port}: unavailable')
    elif command == 'test':
        subprocess.run([sys.executable, 'scripts/e2e.py', *sys.argv[2:]], cwd=ROOT, check=True)
    elif command == 'agent':
        subprocess.run([sys.executable, 'scripts/agent_client.py', *sys.argv[2:]], cwd=ROOT, check=True)
    elif command == 'hosted':
        subprocess.run([sys.executable, 'scripts/hosted.py', *sys.argv[2:]], cwd=ROOT, check=True)
    elif command == 'api':
        subprocess.run([sys.executable, 'scripts/api_client.py', *sys.argv[2:]], cwd=ROOT, check=True)
    elif command in ['client', 'reset']:
        args = sys.argv[2:] if command == 'client' else ['--reset', *sys.argv[2:]]
        subprocess.run([sys.executable, 'scripts/client.py', *args], cwd=ROOT, check=True)
    else:
        print('Usage: ./demo setup|build|up|status|hosted|api|client|agent|test|reset|stop|down')


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, KeyboardInterrupt):
        raise SystemExit(1)
