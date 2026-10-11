# Альтернатива `make up` для process-manager'ов (foreman/honcho/overmind).
# Хранилища (Mongo/Memcached/InfluxDB) — отдельно: `docker compose up -d`.
# Адреса API для фронта берутся из .env (API_URL), порты — тоже.
api: PY_MODE=dev python api/app.py
theo: PY_MODE=dev python api/theo.py
web: node ./bin/www
