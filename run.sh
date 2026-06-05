#!/usr/bin/env bash
# Launch the Cheer ASCII Studio local web app.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000 "$@"
