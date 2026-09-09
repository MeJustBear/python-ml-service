#!/bin/sh
# Перед запуском сервиса накатывает миграции, если задана БД.
set -e

if [ -n "$MLWRAP_DATABASE_URL" ] && [ "${MLWRAP_RUN_MIGRATIONS:-true}" = "true" ]; then
    attempt=1
    until mlwrap migrate; do
        if [ "$attempt" -ge "${MLWRAP_MIGRATE_RETRIES:-10}" ]; then
            echo "entrypoint: миграции не применились после $attempt попыток" >&2
            exit 1
        fi
        echo "entrypoint: БД ещё не готова, повтор $attempt..." >&2
        attempt=$((attempt + 1))
        sleep 2
    done
fi

exec "$@"
