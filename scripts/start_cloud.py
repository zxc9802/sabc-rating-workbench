"""Run the private backend and web frontend together; stop both on failure."""
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request


def main():
    if os.getenv('SABC_AUTH_MODE') == 'sso':
        if len(os.getenv('SABC_SSO_CLIENT_SECRET','')) < 32 or not os.getenv('SABC_SSO_MAIN_ORIGIN','').startswith('https://'):
            raise SystemExit('SSO secret and HTTPS main origin are required')
    elif len(os.getenv('SABC_ACCESS_PASSWORD',''))<20:
        raise SystemExit('SABC_ACCESS_PASSWORD must contain at least 20 characters')
    if not os.getenv('SABC_UI_ORIGIN','').startswith('https://'):
        raise SystemExit('SABC_UI_ORIGIN must be the public HTTPS origin')
    Path(os.environ['SABC_DB']).parent.mkdir(parents=True,exist_ok=True)
    processes=[]
    def stop(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:
        processes.append(subprocess.Popen(['python','-m','uvicorn','sabc.app:app','--host','127.0.0.1','--port','18765','--no-access-log']))
        for _ in range(60):
            if processes[0].poll() is not None: raise SystemExit('Backend failed to start')
            try:
                with urllib.request.urlopen('http://127.0.0.1:18765/api/health',timeout=1) as response:
                    if response.status==200: break
            except OSError: time.sleep(1)
        else: raise SystemExit('Backend readiness timed out')
        processes.append(subprocess.Popen(['node','server.js'],env={**os.environ,'HOSTNAME':'0.0.0.0'}))
        while all(p.poll() is None for p in processes): time.sleep(1)
        raise SystemExit('A service exited; restarting the complete application is required')
    finally:
        for process in processes:
            if process.poll() is None: process.terminate()
        for process in processes:
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait()


if __name__=='__main__': main()
