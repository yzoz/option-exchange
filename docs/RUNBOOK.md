# RUNBOOK — как поднять YZoZ Option Exchange с нуля

> ⚠️ **Актуальность.** Часть инструкций ниже описывает состояние ДО задач №1–5 ТЗ
> (`docs/SPEC.md`): пароль как seed, порт API 69, ручной `docker run`. Эти места уже
> устарели — см. `docs/DONE.md` и `docs/DEVELOPER_GUIDE.md` §7. Кратко, как сейчас:
> хранилища — `docker compose up -d`; конфиг — `.env` (из `.env.example`); секрет —
> **пароль** (PBKDF2), а не seed; API слушает `API_PORT` (по умолчанию 6969) и
> стартует `PY_MODE=dev python api/app.py` без root; фронт берёт адрес API из
> `API_URL` (`window.API_SERVER`). Ниже оставлено как исторический контекст и
> диагностика проблем.
>
> Пошаговая инструкция «чтобы получилось с первого раза». Всё ниже **проверено**
> на чистой машине: Node 24, Python 3.10, Docker. Где есть подводные камни — они
> отмечены 🪨, а рядом — как я их обошёл.
>
> Дополнительно см. `docs/DEVELOPER_GUIDE.md` (описание архитектуры и карта проекта).

---

## TL;DR (быстрый путь)

Если план `_cache`, `docker-compose` не пугает и вы готовы на один патч — вот весь путь:

```bash
# 0. Один раз: патч №1 (см. §5) в api/inc/calculation.py  ← ОБЯЗАТЕЛЬНО, иначе API не стартует

# 1. Хранилища
docker run -d --name eq-mongo    -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=ad -e MONGO_INITDB_ROOT_PASSWORD=pass mongo:latest
docker run -d --name eq-memcached -p 11211:11211 memcached:latest -m 64
docker run -d --name eq-influx   -p 8086:8086 \
  -e INFLUXDB_HTTP_AUTH_ENABLED=false influxdb:1.8

# 2. Базы InfluxDB (иначе первый ордер = 500)
for db in orders trades spot; do
  curl -s -XPOST localhost:8086/query --data-urlencode "q=CREATE DATABASE \"$db\""
done

# 3. Рыночный кэш
mkdir -p _cache && echo 50000 > _cache/ETH_BTC_PRICE && echo 0.8 > _cache/ETH_BTC_HV_7

# 4. Python
python3 -m venv .venv && source .venv/bin/activate
pip install "pymongo<4" influxdb python-memcached scipy pandas six requests schedule bottle

# 5. Node
npm install
PORT=3000 node ./bin/www &                     # веб → http://localhost:3000

# 6. API (без root): запускаем на 6969 через раннер из §7
python /tmp/oe-dev/run_api.py &                # API → http://localhost:6969

# 7. Проверка
open http://localhost:3000/exchange/           # в JS поменяйте порт API на 6969 (см. §8)
```

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

🪨 **Python 3.12+ — риск.** Код 2018 года; зависимость `pymongo<4` и `influxdb` могут
собираться/работать капризно на 3.12. Проверено на **3.10** — берите её, если есть выбор.

---

## 1. Порты и адреса (выучить сразу)

| Сервис | Порт | Комментарий |
|---|---|---|
| Express (веб) | **80 / 443** в проде, иначе `PORT` | По умолчанию `bin/www` берёт 80 → нужен root. Мы зададим `PORT=3000`. |
| Python API | **69** в dev, **8080** в проде | Оба привилегированных/неудобных. Запускаем на **6969** через раннер. |
| MongoDB | 27017 | |
| InfluxDB | 8086 | Нужна ветка **1.x** (клиент в коде — `influxdb` python, старый API). |
| Memcached | 11211 | |

🪨 **Главный подводный камень:** `public/javascripts/exchange.js` **хардкодит** адрес API:

```js
if (host == 'localhost') {
    var apiServer = 'http://localhost:69';   // ← фронт будет стучаться сюда
```

Поэтому либо API обязан жить на `localhost:69`, либо придётся поправить эту строку
(см. §8). Это причина №1, почему «сайт открылся, а данные не грузятся».

---

## 2. Хранилища (Docker)

```bash
docker run -d --name eq-mongo -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=ad -e MONGO_INITDB_ROOT_PASSWORD=pass mongo:latest

docker run -d --name eq-memcached -p 11211:11211 memcached:latest -m 64

docker run -d --name eq-influx -p 8086:8086 \
  -e INFLUXDB_HTTP_AUTH_ENABLED=false influxdb:1.8
```

Проверка, что всё живо:

```bash
docker ps --format '{{.Names}} {{.Status}}'
docker exec eq-mongo mongosh --quiet --eval "db.runCommand({ping:1}).ok"   # → 1
curl -s -o /dev/null -w 'influx:%{http_code}\n' localhost:8086/ping          # → 204
printf 'version\r\n' | timeout 3 nc localhost 11211 | head -1                # → VERSION ...
```

🪨 **Не берите `influxdb:2`** — это другой продукт (Flux, токены, нет базы `db` в старом
смысле). Python-клиент `influxdb` 5.x из кода с ним не работает.
🪨 Креды Mongo (`ad` / `pass`) **зашиты в код** — `api/inc/settings.py`. Поэтому
обязательно задаём `MONGO_INITDB_ROOT_USERNAME`/`PASSWORD` именно такими.

---

## 3. Базы InfluxDB

Код пишет историю в БД `orders` и `trades` (плюс `spot` для графиков). По умолчанию их нет:

```bash
for db in orders trades spot; do
  curl -s -XPOST localhost:8086/query --data-urlencode "q=CREATE DATABASE \"$db\""
done
curl -s "localhost:8086/query?q=SHOW+DATABASES" | head -c 400
```

🪨 **Симптом, если забыть:** регистрация и балансы работают, а **любой ордер падает
HTTP 500** с `InfluxDBClientError: 404 database not found: "orders"`. Именно так и было у меня.

---

## 4. Рыночный кэш (`_cache/`)

При старте API вызывает `setPrice()` и `setHV()`, которые читают файлы
`_cache/<TICKER>_PRICE` и `_cache/<TICKER>_HV_7`. В репозитории их нет (`.gitignore`),
а штатный генератор `api/utils/robo.py` тянет данные с **Poloniex — API мертвяк**
(проверено: пустой ответ). Поэтому создаём вручную:

```bash
cd option-exchange
mkdir -p _cache
echo 50000 > _cache/ETH_BTC_PRICE     # цена ETH/BTC ×1e6 (произвольное ненулевое)
echo 0.8   > _cache/ETH_BTC_HV_7      # волатильность 80%
```

🪨 **Симптом, если забыть:** API падает на старте с
`FileNotFoundError: '../_cache/ETH_BTC_PRICE'`.

---

## 5. Патч №1 (обязателен до фикса по ТЗ #8) — `api/inc/calculation.py`

В `exchange/instruments.json` единственная серия экспирации — **`1519862400` = март 2018**,
то есть в прошлом. `setTheo()` считает Блэк–Шоулз с отрицательным временем до
экспирации → `math.log`/`sqrt` дают `ValueError: math domain error`, и **API не поднимается**.

Минимальная правка (guard на `T <= 0 || V <= 0`):

```python
def theo(self, S, K, V, T, dT):
    # Guard: Black-Scholes undefined for non-positive time to expiry
    # (e.g. expired/hardcoded series). Fall back to intrinsic value.
    if T <= 0 or V <= 0:
        if dT == 'C':
            theo = int(round(max(S - K, 0)))
        else:
            theo = int(round(max(K - S, 0)))
        return theo if theo > 0 else 1
    if dT == 'C':
        ...
```

🪨 Это временная заглушка. По ТЗ задача **#8** заменяет её на нормальную обработку
истёкших серий; по задаче **#17** серии регенерируются в актуальные.

---

## 6. Python-окружение и API

```bash
cd option-exchange
python3 -m venv .venv
source .venv/bin/activate
pip install "pymongo<4" influxdb python-memcached scipy pandas six requests schedule bottle
```

🪨 **Почему `"pymongo<4"`:** код вызывает `client.admin.authenticate('','')`
(`api/inc/settings.py`). В pymongo 4 метод удалён. В 3.13 он есть (проверено) — берём 3.x.
🪨 `python-memcached` даёт модуль `memcache` (именно его импортирует код), НЕ `pymemcache`.
🪨 В репо лежит `api/utils/memcache.py` — это вендорная копия библиотеки, **не используйте её**.

---

## 7. Запуск API на невысоком порту (без root)

`api/app.py` при `PY_MODE=dev` сам вызывает `run(host='0.0.0.0', port=69)`. Порт 69
привилегированный → `PermissionError: [Errno 13]`. Обошёл так: запускаю модуль
**в prod-ветке** (она не вызывает `run`, а отдаёт WSGI-приложение) под своим портом.

Создайте файл **вне репозитория**:

```bash
mkdir -p /tmp/oe-dev
cat > /tmp/oe-dev/run_api.py <<'PY'
import os, sys, importlib
os.environ.pop('PY_MODE', None)          # не даём app.py уйти в ветку run(port=69)
sys.path.insert(0, 'REPO/api')           # ← замените REPO на путь к проекту (или запустите из api/)
import bottle
application = importlib.import_module('app').application
bottle.run(app=application, host='0.0.0.0', port=6969, debug=False)
PY

cd option-exchange/api
python /tmp/oe-dev/run_api.py &
```

Проверка:

```bash
curl -s localhost:6969/counters/ETH_BTC      # → [{"price": 50000,"vola": 0.8}]
```

Альтернативы, если хочется канонический порт 69:
- `sudo` (тогда просто `PY_MODE=dev python api/app.py`);
- либо правка `api/app.py`/конфига на невысокий порт — но это уже задача ТЗ **#10**.

---

## 8. Node/Express (веб)

```bash
cd option-exchange
npm install
PORT=3000 node ./bin/www &          # веб на http://localhost:3000
```

🪨 **Почему `PORT=3000`:** `bin/www` в dev-ветке берёт порт **80** → снова `PermissionError`.
🪨 **Про `npm install`:** в `package.json` все версии — `"latest"`, поэтому сейчас
ставится **Express 5.3** и `body-parser 2.x` под код, писавшийся под Express 4.
У меня **завелось как есть** (Express 5 сохраняет совместимость для `app.use(router)`,
`res.render`, `res.redirect`). Это хрупко и будет зафиксировано в ТЗ **#9**.

**Связать фронт с API.** По умолчанию фронт ждёт API на `localhost:69` (§1). Если
вы, как я, подняли API на 6969 — откройте `public/javascripts/exchange.js` и на время
разработки поменяйте:

```js
var apiServer = 'http://localhost:69';   // → 'http://localhost:6969'
```

(В постоянном решении это выносится в конфиг — ТЗ **#10** / аудит п.4.)

---

## 9. Проверка, что всё действительно работает

### В браузере
1. Откройте `http://localhost:3000/` — лендинг.
2. `http://localhost:3000/exchange/` — торговый стол со страйками 200000…10000.
   В правом верхнем углу должны появиться **HV** и **Price** (значит фронт достучался до API).
3. `http://localhost:3000/info/eth/btc/` — страница аналитики (картинки графиков пока
   отсутствуют — это нормально, см. ТЗ #32).

### Сквозной сценарий через API (без браузера)

```bash
python3 - <<'PY'
import json, hmac, hashlib, urllib.request
API  = 'http://localhost:6969'
KEY  = 'TESTY-AAAAA-BBBBB-CCCCC-1'
SEED = 'test seed phrase one'

def post(path, payload):
    req = urllib.request.Request(API+path, data=json.dumps(payload).encode(),
                                 headers={'Content-Type':'application/json'})
    return urllib.request.urlopen(req).read().decode()

def mac(msg):
    return hmac.new(SEED.encode(), msg.encode(), hashlib.sha3_512).hexdigest()

print(post('/signup', {'key': KEY, 'seed': SEED, 'email': 'a@b.c'})[:80])
print(post('/user', {'user': KEY, 'hmac': mac('balances'), 'question': 'balances'})[:60], '...')

asset, typ, q, price = 'ETH_BTC_1519862400_100000_C', 'buy', 5, 30000
q_msg = 'send' + typ + str(q) + asset + str(price)
print(post('/order', {'user': KEY, 'hmac': mac(q_msg),
                      'question': {'action':'send','type':typ,'quant':q,'asset':asset,'price':price}}))
PY
```

Ожидаемо: `User ... created!`, затем дерево баланса, затем `SendLimit: ...`.

---

## 10. Таблица типовых ошибок

| Симптом | Причина | Что делать |
|---|---|---|
| `EACCES` / порт 80 занят/запрещён | `bin/www` по умолчанию на 80 | `PORT=3000 node ./bin/www` |
| `PermissionError: [Errno 13]` на API | порт 69 < 1024 | раннер из §7 на 6969 или `sudo` |
| API: `FileNotFoundError .../_cache/...` | нет рыночного кэша | §4 |
| API: `ValueError: math domain error` | серия истекла (2018) | патч §5 |
| Ордер → **HTTP 500**, `database not found: "orders"` | не созданы БД Influx | §3 |
| Сайт открылся, но данные пустые | фронт стучится на `localhost:69`, а API на 6969 | §1/§8 |
| `pymongo` `authenticate` отсутствует | поставился pymongo 4 | `pip install "pymongo<4"` |
| `ModuleNotFoundError: memcache` | поставили не ту библиотеку | `pip install python-memcached` |
| `mongo` не подключается | контейнер не готов / не те креды | `docker ps`, ждать ~5 c, креды `ad/pass` |
| `docker: permission denied` | нет прав на docker | добавить пользователя в группу `docker` |
| Графики 404 на `/info/*` | `public/img/*` не сгенерированы | нормально (ТЗ #32) |
| `jquery-ui.css` 404 | файл в `.gitignore` | нормально (ТЗ #33) |

---

## 11. Сценарий «одной командой» (для копипаста)

```bash
set -e
REPO="$HOME/dev/option-exchange"; cd "$REPO"

docker start eq-mongo eq-memcached eq-influx 2>/dev/null || {
  docker run -d --name eq-mongo -p 27017:27017 -e MONGO_INITDB_ROOT_USERNAME=ad \
    -e MONGO_INITDB_ROOT_PASSWORD=pass mongo:latest
  docker run -d --name eq-memcached -p 11211:11211 memcached:latest -m 64
  docker run -d --name eq-influx -p 8086:8086 -e INFLUXDB_HTTP_AUTH_ENABLED=false influxdb:1.8
}
sleep 5
for db in orders trades spot; do
  curl -s -XPOST localhost:8086/query --data-urlencode "q=CREATE DATABASE \"$db\"" >/dev/null
done
mkdir -p _cache
[ -f _cache/ETH_BTC_PRICE ] || echo 50000 > _cache/ETH_BTC_PRICE
[ -f _cache/ETH_BTC_HV_7 ]  || echo 0.8   > _cache/ETH_BTC_HV_7

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip -q install "pymongo<4" influxdb python-memcached scipy pandas six requests schedule bottle
[ -d node_modules ] || npm install

PORT=3000 node ./bin/www >/tmp/oe-web.log 2>&1 &
( cd api && python /tmp/oe-dev/run_api.py >/tmp/oe-api.log 2>&1 & )
sleep 6
echo "веб: http://localhost:3000/exchange/   api: http://localhost:6969/"
```

Остановка:

```bash
pkill -f "bin/www"; pkill -f run_api.py
docker stop eq-mongo eq-memcached eq-influx
```

Сброс данных (если нужно с нуля):

```bash
docker exec eq-mongo mongosh exchange --quiet --eval \
  "db.users.drop(); db.orders.drop(); db.contracts.drop()"
curl -s -XPOST localhost:8086/query --data-urlencode 'q=DROP DATABASE "orders"'
curl -s -XPOST localhost:8086/query --data-urlencode 'q=DROP DATABASE "trades"'
curl -s -XPOST localhost:8086/query --data-urlencode 'q=CREATE DATABASE "orders"'
curl -s -XPOST localhost:8086/query --data-urlencode 'q=CREATE DATABASE "trades"'
```

---

## 12. Что упростит запуск в будущем (из ТЗ)

- **#1–2:** `.env` + `docker-compose.yml` (все хранилища одной командой, креды в конфиг).
- **#9:** зафиксированные версии (`package-lock.json`, `requirements.txt`) — уходит риск с Express 5.
- **#10:** API на настраиваемом невысоком порту; фронт берёт адрес API из конфига, а не из `hostname`.
- **#7, #17:** живой источник данных (Bybit) + актуальные серии → больше не нужны ручные `_cache` и патч `theo()`.
