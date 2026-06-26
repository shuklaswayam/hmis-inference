#!/bin/bash
# Double-fork to fully detach from parent shell
(
  cd "$(dirname "$0")"
  source backend/venv/bin/activate
  export DATABASE_URL="postgresql://hmis:hmis_password@localhost:5432/hmis"
  exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
) &
disown -h
echo "Backend started in background"
