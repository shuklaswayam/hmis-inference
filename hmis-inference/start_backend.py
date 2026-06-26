import os, signal, subprocess, sys

# ---------------------------------------------------------------------------
# Daemonize via double-fork
# ---------------------------------------------------------------------------
if os.fork() > 0:
    sys.exit(0)
os.setsid()
if os.fork() > 0:
    sys.exit(0)

# Redirect stdio
sys.stdin = open(os.devnull)
sys.stdout = open("/tmp/backend.log", "a")
sys.stderr = sys.stdout

# Ignore signals
signal.signal(signal.SIGHUP, signal.SIG_IGN)
signal.signal(signal.SIGTERM, signal.SIG_IGN)

# ---------------------------------------------------------------------------
# Environment + working dir
# ---------------------------------------------------------------------------
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATABASE_URL"] = "postgresql://hmis:hmis_password@localhost:5432/hmis"

# ---------------------------------------------------------------------------
# Launch uvicorn through the project venv's python.
#
# Importing uvicorn here failed before because this script was running under
# system Python (which lacks asyncpg/uvicorn). Using subprocess.run with the
# venv interpreter avoids that — and survives environments where system
# Python changes.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(PROJECT_ROOT, "backend", "venv", "bin", "python")
if not os.path.isfile(VENV_PYTHON) or not os.access(VENV_PYTHON, os.X_OK):
    # Fallback: warn loudly, fall back to whatever interpreter invoked us
    sys.stderr.write(
        f"[start_backend.py] WARNING: {VENV_PYTHON} not found; "
        f"falling back to {sys.executable}. Backend may fail to import deps.\n"
    )
    VENV_PYTHON = sys.executable

subprocess.run(
    [
        VENV_PYTHON,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--log-level",
        "info",
    ],
    cwd=PROJECT_ROOT,
    env=os.environ,
)
