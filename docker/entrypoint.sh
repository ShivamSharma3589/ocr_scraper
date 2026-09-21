#!/usr/bin/env bash
set -e

echo "waiting for mysql at ${DB_HOST}:${DB_PORT}..."
until mysqladmin ping -h "${DB_HOST}" -P "${DB_PORT}" -u"${DB_USER}" -p"${DB_PASSWORD}" --silent 2>/dev/null; do
    sleep 2
done
echo "mysql is up"

echo "applying schema..."
python -m adintel init-db

if [ "$1" = "idle" ]; then
    echo ""
    echo "ready. run commands with:"
    echo "  docker compose exec adintel python -m adintel scrape --retailer lookfantastic --platform meta --limit 10"
    echo "  docker compose exec adintel python -m adintel status"
    echo ""
    exec sleep infinity
fi

exec python -m adintel "$@"
