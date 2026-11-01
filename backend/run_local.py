"""Run one API and one worker for local development."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import dotenv_values

root = Path(__file__).resolve().parent
os.chdir(root)
env = {
    **os.environ,
    **{key: value for key, value in dotenv_values(root / ".env").items() if value is not None},
}
subprocess.run([sys.executable, "-m", "app.init_db"], env=env, check=True)
processes = [
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8020"],
        env=env,
    ),
    subprocess.Popen([sys.executable, "-m", "app.worker"], env=env),
]


def stop(signum, frame):
    raise SystemExit(0)


signal.signal(signal.SIGTERM, stop)
try:
    while all(process.poll() is None for process in processes):
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        process.wait()
