#!/bin/sh
# Container entrypoint. SERVICE picks the role; the image is the same for both.
set -e
case "${SERVICE:-agent}" in
  api)
    exec uvicorn voisai.api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
    ;;
  agent)
    exec python -m voisai.agent.worker start
    ;;
  *)
    echo "unknown SERVICE=$SERVICE (expected api or agent)" >&2
    exit 1
    ;;
esac
