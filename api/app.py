import json
import os
import bottle
from bottle import hook, route, run, template, debug, post, request, response, abort
from bson.objectid import ObjectId
from pymongo.errors import PyMongoError
from influxdb.exceptions import InfluxDBClientError as InfluxDBError

from inc.settings import modb, memdb, storageStatus, formatStorageStatus
from inc.influx import outOrders, outTrades
from inc.utils import pyMode, getTime, splitAsset, hashUser, hashPassword, verifyPassword, checkHMAC, rateAllow
from inc.errors import ExchangeError, StorageError
from inc.orders import userOrders, removeOrder, editOrder, getOrder, \
     getAsset, getBestPrice
from inc.contracts import userContracts, userTrades
from inc.users import allUsers, checkUser, userBalances, clearContracts
from inc.trade import sendOrder, tickerLock
from inc.mc import loadCatalog, rebuildCache, upBest
from inc import state as market

# Шаблоны ищутся независимо от текущего каталога запуска.
bottle.TEMPLATE_PATH.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'views'))

# Разрешённый origin для браузера: конкретный, а не '*'.
CORS_ORIGIN = os.getenv('CORS_ORIGIN', 'http://localhost:3000')

def enable_cors(fn):
    def _enable_cors(*args, **kwargs):
        if bottle.request.method != 'OPTIONS':
            return fn(*args, **kwargs)
    return _enable_cors

# @hook('before_request')


@hook('after_request')
def enableCORSAfterRequestHook():
    response.headers['Access-Control-Allow-Origin'] = CORS_ORIGIN
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'


@bottle.error(400)
@bottle.error(401)
@bottle.error(404)
@bottle.error(409)
@bottle.error(429)
@bottle.error(500)
@bottle.error(501)
@bottle.error(503)
def errorBody(error):
    """Единый JSON-формат ошибок для API (задача ТЗ #16).

    Клиент всегда получает `{"error": {"code": ..., "message": ...}}` с настоящим
    HTTP-кодом, вместо прежнего «200 + текст ошибки в теле». CORS-заголовки
    ставятся hook'ом после запроса и здесь не дублируются.
    """
    response.content_type = 'application/json'
    return json.dumps({'error': {'code': error.status_code, 'message': error.body}})


def guardRate():
    """Per-IP rate-limit для публичных входов. Превышение → 429."""
    if not rateAllow(request.remote_addr or '?'):
        abort(429, 'Too Many Requests')


def jsonBody():
    """JSON-тело запроса или None, если тело не распарсилось/не объект."""
    try:
        body = request.json
    except (ValueError, AttributeError):
        return None
    if not isinstance(body, dict):
        return None
    return body


def authUser(body):
    """Проверить пользователя: HMAC по паролю + PBKDF2.

    Возвращает (userHash, password) или (None, None), если не аутентифицирован.
    Секрет (пароль) приходит в теле и в БД в open виде не хранится.
    """
    key = body.get('user')
    password = body.get('password')
    yourHMAC = body.get('hmac')
    if not isinstance(key, str) or not isinstance(password, str) or not isinstance(yourHMAC, str):
        return None, None
    if not key or not password or not yourHMAC:
        return None, None
    userHash = hashUser(key)
    user = checkUser(userHash)
    if not user:
        return None, None
    if not verifyPassword(password, user.get('passwordHash'), user.get('passwordSalt')):
        return None, None
    return userHash, password

mode = pyMode()

orders = modb().orders
contracts = modb().contracts
users = modb().users

mc = memdb()


def _safeGet(key):
    """Прочитать ключ Memcached, не падая при недоступном хранилище (#25)."""
    try:
        return mc.get(key)
    except Exception:
        return None


# Каталог инструментов (тикеры/серии/страйки/активы) раскладывается в Memcached
# общим bootstrap'ом — тем же, что использует планировщик api/theo.py (задача #18).
# При недоступном Mongo/Influx/Memcached приложение всё равно поднимается: запросы
# к «мёртвому» хранилищу вернут понятный 503 (`storageGuard`), а не уронят импорт.
all = loadCatalog()
assets = _safeGet('ASSETS') or []
tickers = _safeGet('TICKERS') or []
series = []
for ticker in tickers:
    for exp in _safeGet(ticker + '_SERIES') or []:
        series.append(ticker + '_' + exp)

# Пересобрать PRICE/HV (Bybit или _cache), LAST/BEST (Mongo) и THEO при старте.
# Memcached не переживает рестарт — без этого BEST/THEO/LAST «пропадают» (#19).
# Функция устойчива к недоступности хранилищ — старт не падает (#25).
rebuildCache()

_status = storageStatus(force=True)
print('YZoZ API: хранилища — %s' % formatStorageStatus(_status), flush=True)
if any(_status.values()):
    print('YZoZ API: часть хранилищ недоступна — поднимусь в degraded-режиме '
          '(запросы к ним вернут 503). См. GET /health.', flush=True)


def storageGuard():
    """Проверка доступности хранилищ на входе чувствительных роутов (задача #25).

    Отвечает 503 с понятным текстом вместо невнятного 500 при недоступном
    Mongo/Influx/Memcached. Результат проверки кэшируется в settings
    (STORAGE_PROBE_TTL), поэтому на горячем пути это почти бесплатно.
    """
    status = storageStatus()
    down = [name for name, err in status.items() if err]
    if down:
        abort(503, 'Хранилище недоступно (%s). Проверьте docker compose up и GET /health.'
                   % ', '.join(down))


# Ошибки драйверов, которые безопасно превращать в 503 (а не 500): соединение
# с Mongo/Influx могло оборваться уже после проверки storageGuard — в этом случае
# клиент всё равно должен получить понятный код, а не «Internal Server Error».
def storageSafe(fn):
    """Декоратор: превращает ошибки хранилищ в 503 с понятным текстом (#25)."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except StorageError as e:
            abort(e.code, e.message)
        except PyMongoError as e:
            abort(503, 'MongoDB недоступен: %s' % e)
        except InfluxDBError as e:
            abort(503, 'InfluxDB недоступен: %s' % e)
    wrapper.__name__ = getattr(fn, '__name__', 'wrapper')
    return wrapper

# Производные рыночные ответы (/state, /best, /last, /theo) собирает модуль
# inc/state.py (задача ТЗ #23): роуты ниже только вызывают его с каталогом `all`
# и безопасным чтением Memcached.
getSeries = market.seriesAssets

def getSaldo():
    # Суммируем по всем контрактам. Раньше `_id` был фиктивным ('$time'), а
    # `$sum: 'quant'` суммировал СТРОКУ '$quant', игнорируя реальные значения —
    # выходило 0/пусто. `$sum: '$quant'` суммирует поле документа (числа).
    cursor = contracts.aggregate(
    [{
        '$group':{
        '_id': None,
        'quant': {'$sum': '$quant'},
        'amount': {'$sum': '$amount'}
        }}
    ])
    res = []
    for doc in cursor:
        res.append({'quant': doc['quant'], 'amount': doc['amount']})
    return res

@route('/', method=['GET'])
def home():
    response.content_type = 'application/json'
    return json.dumps(all, indent=1)

@route('/state', method=['GET'])
def state():
    response.content_type = 'application/json'
    out = market.getState(all, _safeGet, series)
    return json.dumps(out, indent=1)

@route('/saldo')
@storageSafe
def saldo():
    storageGuard()
    out = getSaldo()
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/health', method=['GET'])
def health():
    """Healthcheck API (+ доступность хранилищ) — задача ТЗ #24/25.

    Всегда отвечает 200 с JSON (это liveness-проба процесса); состояние
    хранилищ — в полях mongo/influx/memcached (`ok` либо текст ошибки), а
    сводка — в `status` (`ok` / `degraded`). Для load-balancer'а, которому
    важна лишь готовность зависимостей, поле `status` даёт ответ без разбора
    деталей.
    """
    status = storageStatus(force=True)
    down = {name: err for name, err in status.items() if err}
    response.content_type = 'application/json'
    return json.dumps({
        'status': 'degraded' if down else 'ok',
        'storage': {name: (err or 'ok') for name, err in status.items()},
        'assets': len(assets),
        'tickers': tickers,
    }, indent=1)

@route('/signup', method=['OPTIONS', 'POST'])
@enable_cors
@storageSafe
def signup():
    guardRate()
    storageGuard()
    body = jsonBody()
    if not body:
        abort(400, 'Bad Request: ожидается JSON-тело')
    key = body.get('key')
    seed = body.get('seed')
    password = body.get('password')
    email = body.get('email')
    if not (key and seed and password):
        abort(400, 'Нужны поля key, seed, password')
    if not (isinstance(key, str) and isinstance(seed, str) and isinstance(password, str)):
        abort(400, 'Поля key, seed, password должны быть строками')
    if email is not None and not isinstance(email, str):
        abort(400, 'Поле email должно быть строкой')
    hash = hashUser(key)
    if checkUser(hash):
        abort(409, 'Пользователь с таким Key уже существует')
    passwordHash, passwordSalt = hashPassword(password)
    cursor = users.insert_one({
    'hash': hash,
    'seed': seed,
    'passwordHash': passwordHash,
    'passwordSalt': passwordSalt,
    'email': email,
    'time': getTime(),
    'balances': {
            'ETH': 1000,
            'BTC': 100000000
            }
    }).inserted_id
    if cursor:
        return 'User ' + hash  + ' with Key "' + key  + '" created! Keep Key and password safe.!. You Have 1000 Wei & 100000000 Satoshi'
    abort(500, 'Не удалось создать пользователя')

@route('/counters/<ticker>')
def counters(ticker):
    response.content_type = 'application/json'
    return '[{"price": ' + str(_safeGet('PRICE_' + ticker)) + ',"vola": '+ str(_safeGet('HV_' + ticker)) + '}]'

@post('/user', method=['OPTIONS', 'POST'])
@enable_cors
@storageSafe
def user():
    guardRate()
    storageGuard()
    body = jsonBody()
    if not body:
        abort(400, 'Bad Request: ожидается JSON-тело')
    userHash, password = authUser(body)
    if not userHash:
        abort(401, 'Bad User или Bad Password')
    question = body.get('question')
    yourHMAC = body.get('hmac')
    if not isinstance(question, str):
        abort(400, 'Bad Question: contracts|orders|trades|balances')
    if not checkHMAC(password, question, yourHMAC):
        abort(401, 'Bad HMAC')
    if question == 'contracts':
        out = userContracts(userHash)
    elif question == 'orders':
        out = userOrders(userHash)
    elif question == 'trades':
        out = userTrades(userHash)
    elif question == 'balances':
        out = userBalances(userHash, assets)
    else:
        abort(400, 'Bad Question: contracts|orders|trades|balances')
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/order', method=['OPTIONS', 'POST'])
@enable_cors
@storageSafe
def order():
    guardRate()
    storageGuard()
    body = jsonBody()
    if not body:
        abort(400, 'Bad Request: ожидается JSON-тело')
    question = body.get('question')
    if not isinstance(question, dict):
        abort(400, 'question должен быть объектом')
    action = question.get('action')
    if not action:
        abort(400, 'Нужно поле question.action')
    userHash, password = authUser(body)
    if not userHash:
        abort(401, 'Bad User или Bad Password')
    yourHMAC = body.get('hmac')

    if action == 'send':
        reqType = question.get('type')
        quant = question.get('quant')
        reqAsset = question.get('asset')
        price = question.get('price')
        if not (reqType and quant and reqAsset and price):
            abort(400, 'Нужны поля type, quant, asset, price')
        if reqType not in ('buy', 'sell'):
            abort(400, 'Bad Type! You can only Buy & Sell')
        try:
            quant = int(quant)
            price = int(price)
        except (TypeError, ValueError):
            abort(400, 'Bad Quantity or Price!')
        if quant <= 0:
            abort(400, 'Quantity must be > 0!')
        if price <= 0:
            abort(400, 'Price must be > 0!')
        toHMAC = action + reqType + str(question.get('quant')) + reqAsset + str(question.get('price'))
        if not checkHMAC(password, toHMAC, yourHMAC):
            abort(401, 'Bad HMAC')
        asset = None
        for ass in assets:
            if reqAsset == ass:
                asset = reqAsset
                splited = splitAsset(asset)
                base = splited['base']
                unit = splited['unit']
                ticker = splited['ticker']
                exp = splited['exp']
                strike = splited['strike']
                dude = splited['dude']
                break
        if not asset:
            abort(400, 'Bad Asset!')
        try:
            return sendOrder(base, unit, ticker, exp, strike, dude, userHash, reqType, quant, asset, price, assets)
        except ExchangeError as e:
            abort(e.code, e.message)

    if action in ('remove', 'edit'):
        id = question.get('id')
        if not id:
            abort(400, 'Нужно поле question.id')
        # Правку/снятие подписывают `action + id` (+ новые quant/price для edit).
        quant = question.get('quant')
        price = question.get('price')
        if action == 'edit':
            toHMAC = action + str(id) + str(quant) + str(price)
        else:
            toHMAC = action + str(id)
        if not checkHMAC(password, toHMAC, yourHMAC):
            abort(401, 'Bad HMAC')
        try:
            orderObj = getOrder(ObjectId(id))
        except Exception:
            abort(400, 'Bad Order Id')
        if not orderObj:
            abort(404, 'Bad Order')
        if orderObj['user'] != userHash:
            # Заявку можно менять/снимать только свою (иначе — притвориться «нет заявки»).
            abort(404, 'Bad Order')
        type = orderObj['type']
        oldQuant = orderObj['quant']
        asset = orderObj['asset']
        oldPrice = orderObj['price']
        ticker = orderObj['ticker']
        exp = orderObj['exp']
        strike = orderObj['strike']
        dude = orderObj['dude']
        if action == 'remove':
            out = removeOrder(ticker, exp, strike, dude, ObjectId(id), userHash, type, oldQuant, asset, oldPrice)
            upBest(asset, type, getBestPrice(type, asset))
            return out
        # edit: заменить объём/цену своей заявки под тикерной блокировкой, чтобы
        # правка не гонялась с матчингом. hmac-подпись уже проверена выше.
        if not (quant and price):
            abort(400, 'Нужны поля quant, price')
        try:
            quant = int(quant)
            price = int(price)
        except (TypeError, ValueError):
            abort(400, 'Bad Quantity or Price!')
        if quant <= 0:
            abort(400, 'Quantity must be > 0!')
        if price <= 0:
            abort(400, 'Price must be > 0!')
        with tickerLock(ticker):
            out = editOrder(ticker, exp, strike, dude, ObjectId(id), userHash, type, quant, asset, price)
        if out is None:
            abort(404, 'Bad Order')
        upBest(asset, type, getBestPrice(type, asset))
        return out

    abort(400, 'Bad Action')

@route('/river/orders/<ticker>/<exp>', method=['GET'])
@storageSafe
def riverOrders(ticker, exp):
    storageGuard()
    out = outOrders(ticker, exp)
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/river/trades/<ticker>/<exp>', method=['GET'])
@storageSafe
def riverTrades(ticker, exp):
    storageGuard()
    out = outTrades(ticker, exp)
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/best/<ticker>/<exp>', method=['GET'])
def best(ticker, exp):
    out = market.getBest(all, _safeGet, ticker, exp)
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/last/<ticker>/<exp>', method=['GET'])
def last(ticker, exp):
    out = market.getLast(all, _safeGet, ticker, exp)
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/theo/<ticker>/<exp>', method=['GET'])
def theo(ticker, exp):
    out = market.getTheo(all, _safeGet, ticker, exp)
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/orders/<asset>', method=['GET'])
@storageSafe
def asset(asset):
    storageGuard()
    sell = getAsset('sell', asset)
    buy = getAsset('buy', asset)
    out = sell + buy
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

ADMIN_TOKEN = os.getenv('ADMIN_TOKEN')

@route('/admin/clear/<ticker>/<exp>/<price>')
@storageSafe
def clearing(ticker, exp, price):
    storageGuard()
    # Роут выполняет клиринг по всем пользователям — только с токеном.
    if not ADMIN_TOKEN:
        abort(404, 'Not Found')
    token = request.query.get('token') or request.headers.get('X-Admin-Token')
    if not token or token != ADMIN_TOKEN:
        abort(401, 'Unauthorized')
    balances = []
    clear = []
    balance = []
    realised = 0
    clearTotal = 0
    assets = getSeries(ticker, exp)
    users = allUsers()
    for user in users:
        balance = userBalances(user['hash'], assets)
        clear = clearContracts(user['hash'], int(price))
        trades = userTrades(user['hash'])
        realised += balance['realised']['BTC']
        clearTotal += clear['BTC']
        balances.append({'hash': user['hash'], 'balance': balance, 'clear': clear, 'trades': trades})
    return template('clear', title='Clearing', price=price, balances=balances, realised=realised, clearTotal=clearTotal)

if mode == 'dev':
    debug(mode=True)
    run(debug=True, reloader=False,
        host=os.getenv('API_HOST', '0.0.0.0'),
        port=int(os.getenv('API_PORT', '6969')))
else:
    app = application = bottle.default_app()
