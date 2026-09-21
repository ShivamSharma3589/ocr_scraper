#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] waiting for mysql at ${DB_HOST}:${DB_PORT} ..."
for attempt in $(seq 1 60); do
    if mysqladmin ping -h "${DB_HOST}" -P "${DB_PORT}" \
         -u"${DB_USER}" -p"${DB_PASSWORD}" --silent 2>/dev/null; then
        echo "[entrypoint] mysql is up"
        break
    fi
    if [ "${attempt}" -eq 60 ]; then
        echo "[entrypoint] ERROR: mysql did not become reachable in 120s"
        exit 1
    fi
    sleep 2
done

if [ ! -d /app/adintel ]; then
    echo "[entrypoint] ERROR: /app/adintel is missing - is the volume mounted?"
    exit 1
fi

echo "[entrypoint] applying schema ..."
python -m adintel init-db

if [ "${1:-idle}" = "idle" ]; then
    echo "[entrypoint] ready. run commands with:"
    echo "  docker compose exec adintel python -m adintel status"
    exec sleep infinity
fi

exec python -m adintel "$@"
