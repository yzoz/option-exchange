# RUNBOOK — как поднять YZoZ Option Exchange с нуля

> **Статус документа.** Обновлён после Этапа 3 ТЗ (задачи 26–35): линтеры
> (`make lint`/`format`, ESLint+Prettier, ruff), `.editorconfig`, лицензия MIT,
> обновлены jQuery/jQuery UI, клиентская валидация и AJAX-ошибки, защита от
> деления на ноль, оптимизация пересчёта THEO.
> Ранее — после Этапа 2 ТЗ (задачи 20–25): запуск через
> `make up/down/logs/e2e` (+ `Procfile`, + compose-профиль `app` — весь стек в
> контейнерах), healthcheck `/health` у API и веб-слоя, graceful-поведение при
> недоступных хранилищах (503 вместо падения импорта), вынос логики из роутов в
> модули-сервисы (#23), удалён мёртвый код, обновлён `README`.
> Ранее (Этап 1, задачи 1–12): конфиг в `.env`, хранилища через `docker compose`,
> пароль (PBKDF2) вместо seed, API на `API_PORT`, фронт берёт адрес API из
> `API_URL`, Bybit вместо Poloniex, `_cache` необязателен, зависимости Node
> зафиксированы (Express 4.x), rate-limit, секреты вычищены из git-истории.
> Исторические детали прежнего запуска (ручной
> `docker run`, патч `theo()`, раннер `/tmp`, правка JS на порт 69) больше не
> нужны — они остались в git-истории. См. также `docs/DONE.md` (что сделано) и
> `docs/DEVELOPER_GUIDE.md` §7 (архитектура и карта портов).
>
> Пошаговая инструкция «чтобы получилось с первого раза». Проверено на Node 24,
> Python 3.10, Docker. Подводные камни отмечены 🪨.

---

## TL;DR (быстрый путь)

```bash
cd option-exchange
cp .env.example .env
make up                                   # хранилища + API + theo + веб (задача #21)
make e2e                                  # сквозной сценарий
open http://localhost:3000/exchange/      # HV/Price должны заполниться (Bybit)
```

`make up` поднимает Mongo/Memcached/InfluxDB (Docker), Python API, планировщик
`api/theo.py` и Node-веб локальными процессами; `make down` их останавливает,
`make logs` показывает логи, `make help` — все цели. Весь стек в контейнерах:
`make docker-up` (compose-профиль `app`). Проверка кода — `make check`
(синтаксис) и `make lint` (ruff + ESLint); форматирование — `make format`.

Эквивалент вручную:

```bash
docker compose up -d                      # 1. хранилища (Influx-базы создаются сами)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PY_MODE=dev python api/app.py &           # 2. API  → http://localhost:6969
PY_MODE=dev python api/theo.py &          #    планировщик PRICE/THEO/HV
npm install && node ./bin/www &           # 3. веб  → http://localhost:3000
```

Ни `_cache`, ни ручной `CREATE DATABASE`, ни патч `calculation.py` больше не нужны.
Дальше — те же шаги подробно, с объяснением «почему» и таблицей типовых ошибок.

---

## 0. Что понадобится

| Компонент | Проверенная версия | Проверка |
|---|---|---|
| Node.js | v24 (подойдёт ≥16) | `node -v` |
| npm | 11 | `npm -v` |
| Python | 3.10 (подойдёт 3.8–3.11) | `python3 --version` |
| Docker + daemon | 29 | `docker ps` |

Проверьте одним махом:

```bash
node -v && npm -v && python3 --version && docker ps >/dev/null && echo "OK"
```

🪨 **Python 3.12+ — риск.** Код 2018 года; зависимости `pymongo<4` и `influxdb`
могут собираться/работать капризно на 3.12. Проверено на **3.10** — берите её,
если есть выбор.

---

## 1. Порты и адреса (выучить сразу)

| Сервис | Порт (dev) | Порт (prod) | Где задаётся |
|---|---|---|---|
| Express (веб) | **3000** (`WEB_PORT`) | 80 / 443 | `.env` → `bin/www` |
| Python API | **6969** (`API_PORT`) | 6969 | `.env` → `api/app.py` |
| MongoDB | 27017 | 27017 | `.env` → `api/inc/settings.py` |
| InfluxDB | 8086 | 8086 | `.env` → `api/inc/settings.py` |
| Memcached | 11211 | 11211 | `.env` → `api/inc/settings.py` |

В dev-режиме оба сервера слушают **непривилегированные** порты — `sudo` не нужен.

🪨 **Главный подводный камень:** браузер должен знать адрес API. Он НЕ берётся из
`hostname` — Express инжектит `window.API_SERVER` из `API_URL` (`.env`) в страницу
(`views/layout.pug`), а `public/javascripts/exchange.js` читает
`window.API_SERVER`. Если `API_URL` не совпадает с реальным портом API — сайт
откроется, но данные будут пустыми. При смене `API_PORT` правьте и `API_URL`
(и, если меняете порт веба, — `CORS_ORIGIN`).

---

## 2. Хранилища (Docker Compose)

```bash
cp .env.example .env
docker compose up -d
```

Поднимаются три сервиса (`docker-compose.yml`):

- `mongo:6.0` — контейнер `eq-mongo`, креды из `MONGO_USER`/`MONGO_PASSWORD`;
- `memcached:1.6` (`-m 64`) — `eq-memcached`;
- `influxdb:1.8` — `eq-influx`, базы `orders`/`trades`/`spot` создаются
  автоматически init-скриптом `docker/influx-init.iql`
  (`/docker-entrypoint-initdb.d/`).

Проверка, что всё живо:

```bash
docker ps --format '{{.Names}} {{.Status}}'
docker exec eq-mongo mongosh --quiet --eval "db.runCommand({ping:1}).ok"   # → 1
curl -s -o /dev/null -w 'influx:%{http_code}\n' localhost:8086/ping          # → 204
printf 'version\r\n' | timeout 3 nc localhost 11211 | head -1                # → VERSION ...
```

🪨 **InfluxDB только 1.8.** Python-клиент `influxdb` 5.x из кода несовместим с
InfluxDB 2.x (Flux/токены).
🪨 Креды Mongo должны совпадать с `.env` (`MONGO_USER`/`MONGO_PASSWORD`) — БД
инициализируется ими при первом старте.
🪨 Если порты 27017/8086/11211 заняты старыми `docker run`-контейнерами, сначала
`docker rm -f eq-mongo eq-memcached eq-influx`.

---

## 3. Базы InfluxDB

С `docker compose` их создавать **не нужно** — init-скрипт
`docker/influx-init.iql` (монтируется в `/docker-entrypoint-initdb.d/`) создаёт
`orders`, `trades`, `spot` при **первом** старте контейнера. Проверить:

```bash
curl -s "localhost:8086/query?q=SHOW+DATABASES" | head -c 400
```

🪨 **`INFLUXDB_DATABASES` не работает** в образе `influxdb:1.8` (это не его
переменная) — до правки базы не создавались автоматически, хотя доки это
утверждали. Теперь используется штатный init-скрипт. Если том `influx-data` уже
существовал (init не запускается), пересоздайте:
`docker compose down && docker volume rm option-exchange_influx-data && docker compose up -d`.
🪨 **Если поднимали Influx вручную (без compose)** и забыли создать базы, симптом
такой: регистрация и балансы работают, а **любой ордер падает HTTP 500** с
`InfluxDBClientError: 404 database not found: "orders"`. Создайте вручную:

```bash
for db in orders trades spot; do
  curl -s -XPOST localhost:8086/query --data-urlencode "q=CREATE DATABASE \"$db\""
done
```

---

## 4. Рыночный кэш (`_cache/`) — необязателен

При старте API вызывает `setPrice()`/`setHV()`/`setTheo()`. Источника два:

1. файлы `_cache/<TICKER>_PRICE` и `_cache/<TICKER>_HV_7` (если есть — приоритет);
2. **Bybit public API** — если файлов нет (это и есть штатный режим после
   задачи #7).

`_cache` теперь **не требуется**: без него API поднимается и берёт цену/HV с Bybit.
Создавать файлы вручную (как раньше в этом разделе) больше не нужно.

🪨 **Проверка «рынок жив»:** `curl -s localhost:6969/counters/ETH_BTC` при
работающем интернете вернёт `[{"price": <с Bybit>,"vola": <HV>}]`. Если ответ
`null` — нет ни файлов, ни доступа к Bybit (проверьте сеть/файрвол).

---

## 5. `theo()` — править больше не нужно

Ранее требовался обязательный патч `api/inc/calculation.py` (guard на `T <= 0`),
иначе API не стартовал на истёкшей серии `1519862400`. Задача #8 закрыта: `theo()`
сама проверяет `S/K/V/T > 0` и возвращает внутреннюю стоимость для истёкших серий.
Никаких ручных правок перед запуском не требуется.

> Серии в `exchange/instruments.json` обновлены задачей ТЗ **#17** — теперь это
> **будущие** серии (ноябрь/декабрь 2026, январь 2027), поэтому `theo()` считает
> по модели Блэка–Шоулза, а не в intrinsic-режиме.

---

## 6. Python-окружение и API

```bash
cd option-exchange
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PY_MODE=dev python api/app.py     # слушает API_HOST:API_PORT (0.0.0.0:6969)
```

Проверка:

```bash
curl -s localhost:6969/counters/ETH_BTC      # → [{"price": ..., "vola": ...}]
```

🪨 **Зависимости зафиксированы** в `requirements.txt` (в т.ч. `python-dotenv`).
Отдельно ставить `"pymongo<4"`/`python-memcached` вручную больше не нужно — они
там есть.
🪨 `python-memcached` даёт модуль `memcache` (не `pymemcache`); вендорная копия
`api/utils/memcache.py` удалена (задача #22).
🪨 Запускайте из **корня репозитория** (как выше), чтобы `.env`, `exchange/` и
`_cache/` находились по абсолютным путям из `settings.py`.
🪨 `api/utils/trader.py` — ручной нагрузчик, хардкодит прод-URL; в запуск не входит.

---

## 7. Запуск API и веб-слоя

**API (Bottle).** Dev-режим поднимает встроенный сервер на `API_HOST:API_PORT`
(по умолчанию `0.0.0.0:6969`) — привилегированных портов нет:

```bash
PY_MODE=dev python api/app.py
```

Любое другое значение `PY_MODE` отдаёт WSGI-приложение (прод/Gunicorn).

**Планировщик рыночных расчётов (`api/theo.py`, задача #18).** Отдельный
долгоживущий процесс: раз в минуту обновляет `PRICE`/`THEO`, раз в 15 минут —
`HV`, а при старте пересобирает `PRICE/HV/LAST/BEST/THEO` из Bybit и Mongo
(задача #19). API и планировщик не зависят друг от друга, но **требуют общего
Memcached**:

```bash
setsid nohup env PY_MODE=dev python api/theo.py >/tmp/opencode/oe-theo.log 2>&1 </dev/null &
# разовый пересчёт (без цикла) — отладка:
PY_MODE=dev python api/theo.py --once
```

> 🪨 **Запуск в фоне (агенты).** Голый `&` в инструментальной оболочке убивает
> сервер вместе с командой (`Killed by SIGTERM`). Отвязывайте процесс:
> `setsid nohup env PY_MODE=dev python api/app.py >/tmp/oe-api.log 2>&1 </dev/null &`.
> Подробно — `docs/DEVELOPER_GUIDE.md` §7.1.

**Веб (Node/Express).** Порт берётся из `WEB_PORT` (dev-дефолт 3000):

```bash
npm install
node ./bin/www
```

🪨 **Про `npm install`.** Версии в `package.json` зафиксированы (Express **4.x**,
`body-parser` 1.x, `pug` 2.x и т.д. — задача ТЗ **#9** закрыта), `package-lock.json`
закоммичен и фиксирует Express **4.22.3**. Код писался под Express 4 — теперь
совпадает.

**Связь фронта с API** задаётся в `.env` (`API_URL`) — правка JS, как раньше, не
нужна.

---

## 8. Проверка, что всё действительно работает

### Автоматический e2e-тест (рекомендуется)

```bash
# при поднятом API
.venv/bin/python tests/e2e.py            # адрес API из API_URL
```

Проверяет регистрацию, балансы, частичный/полный матчинг, атомарность при
параллельных ордерах и негативные ответы (401/400). Завершается кодом `1` при
провале. См. `docs/DEVELOPER_GUIDE.md` §0.3.1 — тест нужно дополнять при правках.

### Healthcheck API

```bash
curl -s localhost:6969/health     # API + хранилища
curl -s localhost:3000/health     # веб-слой + API (задача #24)
```

Всегда отвечает `200` (процесс жив). В теле — `status` (`ok`/`degraded`),
состояние каждого хранилища (`mongo`/`influx`/`memcached`) и число инструментов.
При недоступном хранилище API поднимается в **degraded**-режиме: данные-запросы
(`/signup`, `/user`, `/order`, `/saldo`, `/orders`, `/river/*`) отвечают **HTTP
503** с понятным JSON, а не падают. Проверка кэшируется на `STORAGE_PROBE_TTL`
сек; таймауты — `MONGO_SELECT_TIMEOUT`, `INFLUX_TIMEOUT`.

### Линтеры и форматтеры (задача #27)

```bash
make check        # быстрый синтаксис: py_compile + node --check + compose config
make lint         # ruff (Python) + ESLint (JS)
make lint-py      # только ruff
make lint-js      # только ESLint (нужен npm install)
make format       # prettier --write + ruff --fix
```

- **Python** — `ruff` (конфиг `ruff.toml`: реальные ошибки `E4/E7/E9/F/W`,
  осознанно без модернизации). Установка: `pip install ruff` (или `uvx ruff`).
- **JS** — ESLint (`.eslintrc.json`) + Prettier (`.prettierrc.json`); входят в
  `devDependencies`, ставятся обычным `npm install`.
- **Стиль редактора** — `.editorconfig`.

### В браузере

1. `http://localhost:3000/` — лендинг.
2. `http://localhost:3000/exchange/` — торговый стол. В правом верхнем углу
   должны появиться **HV** и **Price** (значит фронт достучался до API).
3. `http://localhost:3000/info/eth/btc/` — аналитика (картинки графиков — пока
   заглушки/404: генерация PNG ещё не реализована, раздел «На будущее» в SPEC).

### Сквозной сценарий через API (без браузера)

```bash
python3 tests/e2e.py
```

Ручной вариант (если нужно точечно):

```python
import json, hmac, hashlib, urllib.request
API, PW = 'http://localhost:6969', 'secret-pass'
KEY, SEED = 'TESTY-AAAAA-BBBBB-CCCCC-1', 'test seed phrase one'

def post(path, payload):
    req = urllib.request.Request(API+path, data=json.dumps(payload).encode(),
                                 headers={'Content-Type':'application/json'})
    return urllib.request.urlopen(req).read().decode()

def mac(msg):
    return hmac.new(PW.encode(), msg.encode(), hashlib.sha3_512).hexdigest()

print(post('/signup', {'key': KEY, 'seed': SEED, 'password': PW})[:80])
print(post('/user', {'user': KEY, 'password': PW, 'hmac': mac('balances'),
                     'question': 'balances'})[:60], '...')
```

> ⚠ HMAC считается по **паролю**, а не по seed (схема после задачи #5).

---

## 9. Проверка, что всё действительно работает (диагностика)

| Симптом | Причина | Что делать |
|---|---|---|
| API не стартует, `Address already in use` | порт 6969 занят | сменить `API_PORT` (и `API_URL`) |
| Сайт открылся, но данные пустые | `API_URL` не совпадает с портом API | синхронизировать `API_URL`/`API_PORT` |
| `/counters/...` → `null` | нет `_cache` и нет доступа к Bybit | проверить сеть; при желании создать `_cache` (см. §4) |
| Ордер → **HTTP 500**, `database not found: "orders"` | не созданы БД Influx (ручной запуск) | §3 |
| `pymongo` `authenticate` отсутствует | поставлен pymongo 4 | `pip install "pymongo<4"` (или `pip install -r requirements.txt`) |
| `ModuleNotFoundError: memcache` | не та библиотека | `pip install python-memcached` |
| `mongo` не подключается | контейнер не готов / не те креды | `docker ps`, ждать ~5 c, сверить `.env` |
| `docker: permission denied` | нет прав на docker | добавить пользователя в группу `docker` |
| Графики 404 на `/info/*` | `public/img/*` не сгенерированы (`robo.py` не запускали) | нормально; см. §11 / «На будущее» в SPEC |
| Стол открылся, но **BEST/THEO/LAST пустые**, при живом `PRICE`/`HV` | API перезапущен на «холодном» Memcached (кэш не переживает рестарт) | перезапустить API (пересборка при старте, #19) или запустить `api/theo.py` |
| `/exchange/` редиректит на неизвестную серию / 404 на столе | серия из `instruments.json` устарела | обновить серии (#17) и перезапустить веб-слой |
| Стол открылся, но **PRICE = null** | нет `_cache` и нет доступа к Bybit | проверить сеть (§4) |
| `/user`, `/order`, `/signup` → **HTTP 429** | сработал rate-limit | подождать `RATE_WINDOW` или поднять `RATE_MAX` / `RATE_LIMIT=0` |
| Ордер → **500** сразу после чистой установки Memcached | устаревший код: `currencys` читался на импорте | исправлено (ленивый `_currencys()`); обновите код |
| API стартует, но данные-роуты → **503**, `/health` → `degraded` | недоступно хранилище (Mongo/Influx/Memcached) | `docker compose up -d`, проверить `GET /health`; см. §2 |
| API **не стартует** при выключенных хранилищах | устаревший код (падал импорт) | исправлено (задача #25): стартует в degraded; обновите код |

---

## 10. Сценарий «одной командой» (для копипаста)

То же делает `make up` (см. TL;DR) — скрипт ниже полезен, если `make` недоступен
или нужен явный контроль над каждым шагом.

```bash
set -e
REPO="$HOME/dev/option-exchange"; cd "$REPO"

[ -f .env ] || cp .env.example .env
docker compose up -d
sleep 5

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip -q install -r requirements.txt
[ -d node_modules ] || npm install

setsid nohup env PY_MODE=dev python api/app.py >/tmp/oe-api.log 2>&1 </dev/null &
setsid nohup env PY_MODE=dev python api/theo.py >/tmp/oe-theo.log 2>&1 </dev/null &
setsid nohup node ./bin/www >/tmp/oe-web.log 2>&1 </dev/null &
sleep 8

.venv/bin/python tests/e2e.py
echo "веб: http://localhost:3000/exchange/   api: http://localhost:6969/"
```

> 🪨 `setsid ... &` (а не голый `&`) — чтобы серверы пережили завершение
> оболочки. В агентской среде простой `&` убивается вместе с командой
> (`Killed by SIGTERM`). Подробно — `docs/DEVELOPER_GUIDE.md` §7.1.

Остановка:

```bash
pkill -f "api/app.py"; pkill -f "api/theo.py"; pkill -f "bin/www"; docker compose stop
```

Сброс данных (если нужно с нуля):

```bash
docker exec eq-mongo mongosh exchange --quiet --eval \
  "db.users.drop(); db.orders.drop(); db.contracts.drop()"
for db in orders trades; do
  curl -s -XPOST localhost:8086/query --data-urlencode "q=DROP DATABASE \"$db\""
  curl -s -XPOST localhost:8086/query --data-urlencode "q=CREATE DATABASE \"$db\""
done
```

---

## 11. Генерация графиков (`robo.py`)

`api/utils/robo.py` — отдельный скрипт (не входит в рантайм API). Он тянет
свечи с Bybit, пишет историю в InfluxDB `spot` и строит PNG в `public/img/`.
Импортирует `inc.*`, поэтому запускать **из каталога `api/`**:

```bash
cd api && python utils/robo.py
```

🪨 Требует `matplotlib` (нет в `requirements.txt` — тяжёлая зависимость, нужна
только для графиков): `pip install matplotlib`. `numpy` придёт с `scipy`/`pandas`.
Полноценная генерация графиков для `/info/*` — в блоке «На будущее» (SPEC), вне
текущей работы.

---

## 12. Что уже не нужно (историческое)

Эти шаги из ранних версий RUNBOOK больше **не выполняются**:

- ручной `docker run` для Mongo/Memcached/Influx → `docker compose up -d`;
- ручное создание БД Influx → init-скрипт (`docker/influx-init.iql`); переменная
  `INFLUXDB_DATABASES` в image 1.8 не работала (см. §3);
- создание `_cache/ETH_BTC_PRICE` и `_cache/ETH_BTC_HV_7` вручную → Bybit;
- патч `api/inc/calculation.py` (guard `theo()`) → задача #8 закрыта;
- запуск API через раннер `/tmp/oe-dev/run_api.py` на 6969 → `API_PORT`;
- правка `public/javascripts/exchange.js` (`localhost:69`) → `API_URL`
  (dev-fallback теперь `localhost:6969`);
- seed как секрет/HMAC-ключ → пароль (PBKDF2) + HMAC по паролю;
- `"latest"` в `package.json` → фиксированные версии Express 4.x (#9);
- креды `ad`/`pass` в коде/истории → `.env` + ротация + чистка истории (#12).

Этап 3 (**#26–#35**) закрыт — см. `docs/DONE.md`. Открытые пункты — блок
«На будущее» в `docs/SPEC.md` (админ-генерация серий, Memcached→Redis, автотесты
дополнительно, CI, бэкапы, генерация графиков).
