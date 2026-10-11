# DONE — журнал выполненных работ

> Краткая история изменений по крупным блокам. Предназначена для нового агента
> (или разработчика), который продолжает работу над проектом: здесь описано, что
> уже сделано, **почему** именно так, и на что не наступать снова.
>
> Текущий статус плана и приоритеты — в `docs/SPEC.md`. Описание архитектуры —
> в `docs/DEVELOPER_GUIDE.md`. Запуск — в `docs/RUNBOOK.md`.

---

## Индекс

| Дата | Блок | Задачи ТЗ | Статус |
|---|---|---|---|
| 2026-10-11 | Этап 1, задачи 1–5 (P0) + сопутствующий запуск | #1, #2, #3, #4, #5; частично #8, #10, #11 | ✅ e2e проверено |
| 2026-10-11 | Этап 1, задачи 6–8 (P0) — атомарность, Bybit, `theo()` | #6, #7, #8 | ✅ e2e проверено |

---

## 2026-10-11 — Этап 1, задачи 1–5

Выполнены пять задач P0 из `docs/SPEC.md` и минимальный набор сопутствующих правок,
без которых «живой» запуск с новой схемой был бы невозможен. Ниже — по задачам.

### Что менять в первую очередь (кратко)

- Конфиг теперь в `.env` (корень репозитория); хардкод кредов убран.
- Хранилища поднимаются `docker compose up -d` (Mongo 6, Memcached, InfluxDB 1.8).
- `api/inc/address.py` — CLI-скрипт, рантайм его не импортирует.
- `/admin/clear/...` требует `ADMIN_TOKEN`.
- Аутентификация переведена на **пароль** (PBKDF2), `seed` — мнемоника, не секрет.

---

### Задача 1 — Конфиг через `.env` 🔴

**Файлы:** `api/inc/settings.py`, `app.js`, `bin/www`, `public/javascripts/exchange.js`,
`views/layout.pug`, `.env.example` (создан), `.env` (создан, в `.gitignore`),
`.gitignore`, `package.json`, `requirements.txt`.

Что сделано:

- **Python** (`api/inc/settings.py`): все креды и хосты читаются из окружения через
  `python-dotenv`. `.env` грузится по абсолютному пути от корня репозитория
  (`api/inc/` → `../../.env`), поэтому не зависит от текущего каталога запуска.
  - Переменные: `MONGO_HOST/PORT/USER/PASSWORD/DB`, `INFLUX_HOST/PORT/USER/PASSWORD`,
    `MEMCACHED_HOST/PORT`.
  - Убран ручной `cli.admin.authenticate(...)` (его нет в pymongo 4). Теперь Mongo
    подключается по URI: `mongodb://user:pass@host:port/?authSource=admin`.
  - Добавлены константы путей: `ROOT`, `INSTRUMENTS`, `CACHE_DIR` — чтобы
    `instruments.json` и `_cache/` находились независимо от cwd.
- **Node** (`app.js`, `bin/www`): добавлен `dotenv`, `require('dotenv').config()` в
  обеих точках входа. `bin/www` читает `WEB_HOST`/`WEB_PORT` (dev-дефолт 3000 вместо
  привилегированного 80) и `WEB_HTTP_PORT`, а TLS-пути — из `TLS_KEY_PATH`/`TLS_CERT_PATH`
  (убран хардкод `/etc/letsencrypt/live/yzoz.com/*`).
- **Фронт**: `exchange.js` больше не выбирает API по `window.location.hostname`.
  `app.js` кладёт `app.locals.apiUrl = process.env.API_URL`, `layout.pug` инжектит его
  в страницу как `window.API_SERVER`, а `exchange.js` читает
  `var apiServer = window.API_SERVER || 'http://localhost:69'`.
- `requirements.txt` создан (в т.ч. `python-dotenv`); `dotenv` добавлен в `package.json`.
- `.gitignore`: добавлены `.env`, `.venv/`, `__pycache__/`.

**Переменные `.env` (см. `.env.example`):**

```
NODE_ENV, WEB_HOST, WEB_PORT, API_URL, CORS_ORIGIN
PY_MODE, API_HOST, API_PORT, ADMIN_TOKEN
MONGO_HOST, MONGO_PORT, MONGO_USER, MONGO_PASSWORD, MONGO_DB
INFLUX_HOST, INFLUX_PORT, INFLUX_USER, INFLUX_PASSWORD
MEMCACHED_HOST, MEMCACHED_PORT
```

**Подводные камни:**

- `.env` **не коммитится**. При первом запуске: `cp .env.example .env`.
- `API_URL` должен указывать на порт Python-API (по умолчанию `6969`), иначе фронт
  будет молча показывать пустые данные.
- `CORS_ORIGIN` по умолчанию `http://localhost:3000` — если меняете порт веба,
  поменяйте и его (см. задачу 11 частично).

---

### Задача 2 — `docker-compose.yml` 🔴

**Файл:** `docker-compose.yml` (создан).

- `mongo:6.0` (порт `MONGO_PORT`), `memcached:1.6` (`-m 64`), **`influxdb:1.8`**.
- Автосоздание баз: `INFLUXDB_DATABASES: orders,trades,spot` — больше не нужен ручной
  `CREATE DATABASE` из RUNBOOK §3.
- Креды Mongo берутся из `.env` (`MONGO_USER`/`MONGO_PASSWORD`), а не зашиты.
- Healthcheck у Mongo и Influx, именованные тома `mongo-data`, `influx-data`.
- Проверено: `docker compose config --quiet`.

**Подводные камни:**

- **InfluxDB только 1.8.** Python-клиент `influxdb` 5.x из кода несовместим с InfluxDB 2.x.
- Имена контейнеров сохранены (`eq-mongo`, `eq-memcached`, `eq-influx`) — как в RUNBOOK.
- Если порты заняты старыми контейнерами (`docker run ...`), сначала
  `docker rm -f eq-mongo eq-memcached eq-influx`.

---

### Задача 3 — Обезвредить `api/inc/address.py` 🔴

**Файл:** `api/inc/address.py`.

- Печать ключей больше **не выполняется при импорте**: всё в `main()` под
  `if __name__ == '__main__'`. Теперь это явный CLI:
  `python api/inc/address.py`.
- Удалён зашитый `privT` (компрометирован) и отладочные блоки.
- Функции вынесены: `newBitcoinKey()`, `newEthereumKey()`, `signMessage()`, `getAddress()`.
- `getAddress()` возвращает `None`, если `ripemd160` не собрался (OpenSSL 3 держит его
  в legacy-провайдере) — иначе CLI падал бы целиком.
- Зависимости `ecdsa`, `pysha3` — только для CLI, добавлены в `requirements.txt`
  отдельной строкой с пояснением.
- Приложение этот модуль **не импортирует** (проверено grep'ом).

**Подводные камни:**

- Считать старый `privT` скомпрометированным, никогда не использовать.
- Если запускаете CLI на OpenSSL 3 и нужен BTC-адрес — включите legacy-провайдер
  (`openssl` config) либо считайте это некритичным (ключи генерируются, адрес — нет).

---

### Задача 4 — Закрыть `GET /admin/clear/...` 🔴

**Файлы:** `api/app.py`, `api/views/clear.tpl`.

- Роут требует `ADMIN_TOKEN` (из `.env`): принимается `?token=...` **или** заголовок
  `X-Admin-Token`. Неверный/отсутствующий → `401`; если `ADMIN_TOKEN` не задан → `404`
  (чтобы не палить существование роута).
- Из HTML-отчёта убран вывод `seed` пользователя (`clear.tpl` + формирование `balances`
  в `clearing()`). Остальные данные отчёта сохранены.

**Подводные камни:**

- `ADMIN_TOKEN` в `.env.example` — заглушка `change-me-admin-token`, обязательно менять
  в проде.
- Проверка токена — простое сравнение; для прода стоит вынести и не логировать.

---

### Задача 5 — Секреты не в plaintext (вариант B) 🔴

Главное смысловое изменение. Раньше: `seed` был и «паролем», и HMAC-ключом, и лежал
в Mongo **открытым текстом**. Симметричный HMAC требует, чтобы сервер знал ключ, поэтому
«хеш вместо seed» + «проверка HMAC» несовместимы без смены схемы.

Принята **модель B**:

- `key` — публичный идентификатор пользователя (хранится как blake2b-хеш, как и было).
- `seed` — seed-фраза (мнемоника). **Не секрет** с точки зрения аутентификации,
  хранится как есть (это осознанный выбор — можно рассмотреть хранение хеша seed
  отдельной задачей).
- **`password`** — новый секрет, вводится при регистрации и логине. Хранится как
  **PBKDF2-HMAC-SHA512** (`passwordHash` + `passwordSalt`, 200 000 итераций, dklen 32,
  соль 16 байт из `os.urandom`). В БД plaintext-секрета **нет**.
- HMAC теперь считается по паролю, а не по seed.

**Файлы и ключевые точки:**

- `api/inc/utils.py`:
  - `hashPassword(password)` → `(hash, salt)`;
  - `verifyPassword(password, passwordHash, salt)` → `bool` (сравнение через
    `hmac.compare_digest`);
  - `PBKDF2_ITERATIONS = 200000`, `PBKDF2_DKLEN = 32`.
- `api/inc/users.py`: `checkUser(userHash)` теперь возвращает **документ пользователя**
  (было — `cursor['seed']`). Возвращает `False`, если не найден.
- `api/app.py`:
  - `authUser(body)` — общий вход: достаёт `user`/`password`/`hmac`, считает
    `hashUser(user)`, проверяет PBKDF2. Возвращает `(userHash, password)` или `(None, None)`.
  - `jsonBody()` — безопасный парсинг JSON (не падает на пустом/битом теле).
  - `/signup`: поля `key, seed, password` (+ `email` опционально); дубликат Key → `409`;
    сохраняет `seed`, `passwordHash`, `passwordSalt`.
  - `/user`, `/order`: принимают `password` в теле, HMAC-ключ — пароль.
- **Фронт**:
  - `views/exchange.pug`: в регистрации добавлено поле `#regPassword`; в логине вместо
    «Seed» — пароль `#userPassword`.
  - `public/javascripts/exchange.js`: `getMyPassword()` читает `#userPassword`;
    `getHMAC()` ключуется паролем; `signUp()` и все AJAX-вызовы `/user`, `/order`
    отправляют `password` в теле.

**Формат запросов (важно для нового агента):**

```
POST /signup  { key, seed, password, email }
POST /user    { user, password, hmac, question }     # question: contracts|orders|trades|balances
POST /order   { user, password, hmac, question:{action,...} }
```

HMAC считается так же, как раньше, но ключ — **пароль**:
`HMAC_SHA3-512(password, question)`.

**Подводные камни:**

- Пароль передаётся в теле каждого запроса (иначе сервер не сможет проверить HMAC).
  В dev это HTTP — для прода нужен HTTPS.
- Старые пользователи из прошлой схемы (без `passwordHash`) аутентифицироваться **не
  смогут** — БД пришлось чистить при тестировании. Для реальной миграции нужен отдельный
  скрипт (вне текущей задачи).
- `checkUser` сменил возвращаемый тип. Все места вызова уже обновлены, но при добавлении
  новых вызовов помнить: это документ, а не seed.

---

### Сопутствующие правки (нужны для запуска)

Не входили в задачи 1–5 буквально, но без них проверка была бы невозможна / запуск ломался.

- **`api/app.py`**
  - Пути: `open(INSTRUMENTS)` вместо `open('../exchange/instruments.json')`; шаблоны
    через `bottle.TEMPLATE_PATH` с абсолютным путём к `api/views/` (роут `clear` падал
    `Template not found` при запуске не из `api/`).
  - **CORS** (частично задача 11): убран `Access-Control-Allow-Origin: *`, теперь
    конкретный `CORS_ORIGIN` из `.env`.
  - **Старт** (задача 10): `run(host=API_HOST, port=API_PORT)` вместо `port=69`,
    `reloader=False`. Порт `6969` не привилегированный — root/sudo не нужен.
  - Ошибки: переход на `abort(код, текст)` вместо «200 + текст ошибки в теле»
    (частично задача 16). Валидация полей с `400` (частично задача 15).
  - Безопасный разбор JSON, `action` ∈ {send, remove, edit}; `edit` → `501`
    (задача 14 ещё открыта).
- **`api/inc/mc.py`** (частично задача 8): `setPrice()`/`setHV()` используют `CACHE_DIR`
  и не падают, если файла `_cache/<TICKER>_PRICE` / `_HV_7` нет (просто пропускают).
- **`api/inc/settings.py`**: `MemClient(..., debug=0)` — убран шумный вывод.

---

### Как это проверялось (e2e)

Стек: Mongo/Memcached/Influx уже подняты (`docker ps` → `eq-*`), Influx-базы созданы.

1. `cp .env.example .env`; `.venv` c `pip install -r requirements.txt`.
2. `PY_MODE=dev python api/app.py` → слушает `0.0.0.0:6969`, `/counters/ETH_BTC` → 200.
3. Сквозной сценарий (Python + `urllib`): signup → balances → order → **matching
   двух пользователей** → trades — всё 200, сделка создалась.
4. Негативные: неверный пароль → 401, неверный HMAC → 401, повторный signup → 409,
   `/admin/clear/...` без токена → 401, с токеном → 200.
5. В Mongo у пользователя: `seed`, `passwordHash`, `passwordSalt`; plaintext-пароля нет.
6. Веб (`node ./bin/www` на `WEB_PORT`): страница `/exchange/` содержит
   `window.API_SERVER = 'http://localhost:6969'` и поля `#regPassword`/`#userPassword`.
7. `python -m py_compile api/app.py api/inc/*.py`, `node --check ...`,
   `docker compose config --quiet` — чисто.

**Как воспроизвести локально (кратко):**

```bash
cp .env.example .env
docker compose up -d
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
mkdir -p _cache && echo 50000 > _cache/ETH_BTC_PRICE && echo 0.8 > _cache/ETH_BTC_HV_7
PY_MODE=dev python api/app.py &        # API :6969
npm install && node ./bin/www &        # веб :3000
```

`_cache` всё ещё нужен вручную — это задача #7 (Bybit) и частично #8. Для e2e
достаточно любых ненулевых значений.

---

### Известные ограничения / что осталось

- **Задача 5**: `seed` по-прежнему хранится открытым текстом (как мнемоника). Если
  требуется скрыть и его — нужна отдельная доработка (хеш seed / вообще убрать хранение).
- **Задача 14**: `edit`-ветка `/order` не реализована (сейчас `501`).
- **Задачи 6, 7, 9, 12** и остальной Этап 1 не начаты. Полный список — `docs/SPEC.md`.
- Файл `api/inc/calculation.py` (guard в `theo()`, задача 8) был пропатчен в прошлом
  сеансе — **не трогал** в этом блоке.
- Изменения **не закоммичены** (на момент написания).

---

### Риски, на которые смотреть новому агенту

- **Секреты в git-истории** (задача 12) ещё не вычищены; креды `ad/pass` надо
  ротировать, а не просто убрать из текущего кода.
- **CORS/HMAC**: пароль ходит в теле — без HTTPS это небезопасно в проде.
- **`checkUser` contract** изменён — не возвращайте старую логику `seed`.
- **`.env` обязателен**: без него API стартует на дефолтах, а фронт может уйти не на тот порт.

---

## 2026-10-11 — Этап 1, задачи 6–8

Закрыты три P0-задачи: атомарность торгового ядра (#6), живой источник
рыночных данных Bybit (#7) и безопасный `theo()` + необязательный `_cache` (#8).

### Задача 6 — Атомарность торгового ядра 🔴

Выбран вариант **блокировка на asset-тикер + атомарный захват встречных заявок**
(standalone-Mongo, без replica set/транзакций).

**Файлы:** `api/inc/orders.py`, `api/inc/trade.py`.

- `orders.matchOrder(...)` — атомарный «выкуп» встречной заявки:
  - кандидат ищется `find_one` (сортировка по лучшей цене и времени, `user != мой`);
  - если заявку можно забрать целиком — `find_one_and_delete({_id, quant})`;
    если нужна лишь её часть — `find_one_and_update({_id, quant})`.
  - Условие по **текущему `quant`** в фильтре — ключ к защите от гонок: если
    параллельный процесс успел изменить/удалить заявку, запрос вернёт `None`,
    и цикл подберёт следующую. Одну заявку нельзя выкупить дважды.
  - Свои заявки исключены фильтром `user != user` (больше нет ветки «I'm Stupid»).
- `trade.py`:
  - `tickerLock(ticker)` — per-тикерные `threading.Lock` (реестр под общим guard).
    Весь `sendOrder` идёт под блокировкой: убирает гонку между `checkOrder`
    (проверка баланса) и созданием сделки.
  - Матчинг переписан без двойного `ObjectId(...)`/`removeOrder`/`editQuant`:
    цикл `while quant > 0` → `matchOrder` → `makeDeal` на взятый объём.
- **Подводные камни:**
  - Блокировка атомарна только в пределах одного процесса (WSGI в dev / один
    воркер). Для нескольких воркеров нужна распределённая блокировка (Redis/
    Mongo) либо replica set + транзакции — отдельная задача.
  - `makeDeal` теперь вызывается ровно на взятый `matchOrder` объём (раньше
    ветвление `quant >/< /== oppQuant` дублировало логику и объект `_id`).
  - `inOrder(..., 'REMOVE'/'EDIT')` для встречной заявки теперь пишет Influx
    из `matchOrder` (раньше — из `removeOrder`/`editQuant`).

### Задача 7 — Источник данных Bybit 🔴

**Файлы:** `api/inc/mc.py`, `api/utils/robo.py`.

- `mc.py` получил Bybit-хелперы (`api.bybit.com/v5/market`, публичный, без ключей):
  - `bybitSymbol(ticker)`: `ETH_BTC` → `ETHBTC`;
  - `bybitGet(path, params)` — GET + проверка `retCode`;
  - `setCurrent()` — цена `lastPrice` последнего тикера (вместо Poloniex);
  - `bybitHV(ticker, days=7)` — годовая HV из дневных свечей (`kline interval=D`),
    лог-доходности, `std * sqrt(365)`.
- `setPrice()`/`setHV()` — при отсутствии файла `_cache` берут значения с Bybit
  (см. задачу 8); при наличии файла поведение прежнее.
- `robo.py` полностью переписан: `getTrades()`/`volatility()` читают свечи Bybit
  (`klines()`), записывают их в InfluxDB (`spot`) и обновляют `_cache`. Поля
  `buy`/`sell` строятся по знаку «close vs open» (у Bybit нет per-trade buy/sell).
- **Подводные камни:**
  - Bybit отдаёт свечи **от новых к старым** — в `klines()` список разворачивается.
  - Объём Bybit — в базовой валюте; прежний код Poloniex также давал базовый объём.
  - `matplotlib`/`scipy` нужны только для `robo.py` (графики, задача #32 всё ещё
    открыта — генерация PNG не входила в эту задачу, но источник данных уже живой).
  - Старый `api/utils/get.py` (загрузка истории с Poloniex) **не трогали** — при
    необходимости переводить отдельно.

### Задача 8 — Безопасный `theo()` + необязательный `_cache` 🔴/🟠

**Файлы:** `api/inc/calculation.py`, `api/inc/mc.py`.

- `theo()` больше не полагается на «счастливый» `T > 0`: проверяются **все** входы
  (`S > 0`, `K > 0`, `V > 0`, `T > 0`). Иначе возвращается внутренняя стоимость
  (Call: `max(S-K,0)`, Put: `max(K-S,0)`), минимум 1. Это заменяет временную
  заглушку из прошлого блока.
- `setTheo()` пропускает тикер, если нет `PRICE_*` или `HV_*` (не вызывает модель
  с `None`-входами).
- `setLast()` пропускает закрытые позиции (`quant == 0`) — убрано деление на ноль.
- **`_cache` действительно необязателен:** API стартует при отсутствии каталога,
  а цена/HV приходят с Bybit.

### Как это проверялось (e2e)

Сквозной сценарий сохранён как **`tests/e2e.py`** (прогоняется `python tests/e2e.py`
при поднятом API; адрес — из `API_URL`). Дополнять его новыми проверками —
обязанность будущих правок (§0.3.1 `docs/DEVELOPER_GUIDE.md`).

Стек поднят (`eq-mongo`/`eq-memcached`/`eq-influx`), API `PY_MODE=dev` на :6969.

1. `python -m py_compile` по всем `.py`, `node --check` по JS — чисто.
2. `theo()`: ATM 30d; истёкшая серия (`T=-0.5`); нулевые `S`/`V`/`T` — без
   исключений, значения осмысленные.
3. Bybit: `setCurrent()` → `price 30316`, `bybitHV` → `0.20555` при **удалённом**
   `_cache` (API поднялся и отдал `/counters/ETH_BTC`).
4. Сквозной сценарий: signup A/B/C → A `sell 10 @30000` (лимит) → B `buy 4`
   (частичное: у A позиция `-4`, заявка укорочена до `6`) → C `buy 6` (полное
   закрытие: у A `-10`). Баланс B сошёлся (`available.BTC = 99 880 000`).
5. **Гонки:** A2 `sell 10`, два покупателя B2/C2 параллельно `buy 10 @30000`.
   Ровно один матч на 10; у A2 позиция `-10` (**не -20**), лишних заявок нет.
   Второй покупатель получил лимитку на остаток.

### Известные ограничения / что осталось

- **Задача 6**: блокировка — только внутри процесса; multi-worker/транзакции —
  вне этой задачи.
- **Задача 7**: `robo.py`/`get.py` всё ещё пишут историю в InfluxDB `spot`
  (графики — задача #32); серии `instruments.json` по-прежнему истекшие (#17),
  поэтому `theo()` работает в intrinsic-режиме.
- **Задача 9**: `package.json` всё ещё с `"latest"`.
- **Задачи 12** (чистка git-истории) и остальной Этап 1 не начаты.
- Изменения **не закоммичены**.

### Риски, на которые смотреть новому агенту

- **Не возвращайте per-order удаление в `trade.py`** (`removeOrder`/`editQuant`
  напрямую) — только через `matchOrder`, иначе снова появятся гонки.
- **Проверка баланса `checkOrder` не резервирует средства явно** — инвариант
  держится на per-тикерной блокировке. При выносе в несколько воркеров — пере-
  смотреть (резервы или транзакции).
- **Bybit-хелперы живут в `inc.mc`** и переиспользуются `robo.py` — не дублируйте
  HTTP-логику.
- **`_cache` больше не обязателен**: ручное `echo 50000 > _cache/...` из RUNBOOK
  устарело (файл, если есть, имеет приоритет над Bybit).
