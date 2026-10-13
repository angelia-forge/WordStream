#!/bin/sh
set -eu

if [ "$(id -u)" = "0" ]; then
    mkdir -p /data
    chown -R wordstream:wordstream /data
    exec gosu wordstream "$0" "$@"
fi

alembic upgrade head
exec "$@"
