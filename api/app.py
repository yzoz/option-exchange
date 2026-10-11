import json
import os
import bottle
from bottle import hook, route, run, template, debug, post, request, response, HTTPError, abort
from bson.objectid import ObjectId
from inc.settings import modb, memdb, INSTRUMENTS
from inc.influx import outOrders, outTrades
from inc.utils import pyMode, getTime, splitAsset, hashUser, hashPassword, verifyPassword, checkHMAC, rateAllow
from inc.orders import userOrders, removeOrder, getOrder, \
     getAsset, getBestPrice
from inc.contracts import userContracts, userTrades
from inc.users import allUsers, checkUser, userBalances, clearContracts
from inc.trade import sendOrder
from inc.mc import setPrice, setHV, setLast, setBest, setAssets, setTickers, setSeries, setStrikes, setTheo, upBest, setCurrencys, getCurrencys

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


def guardRate():
    """Per-IP rate-limit для публичных входов. Превышение → 429."""
    if not rateAllow(request.remote_addr or '?'):
        abort(429, 'Too Many Requests')


def jsonBody():
    """JSON-тело запроса или None, если тело не распарсилось."""
    try:
        return request.json
    except (ValueError, AttributeError):
        return None


def authUser(body):
    """Проверить пользователя: HMAC по паролю + PBKDF2.

    Возвращает (userHash, password) или (None, None), если не аутентифицирован.
    Секрет (пароль) приходит в теле и в БД в open виде не хранится.
    """
    key = body.get('user')
    password = body.get('password')
    yourHMAC = body.get('hmac')
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

all = []
assets = []
tickers = []
series = []
tickerSeries = []
tickerSeriesStrikes = []

with open(INSTRUMENTS) as jsonData:
    instruments = json.load(jsonData)
    for instrument  in instruments:
        for ticker in instrument:
            ___series = instrument[ticker]['series']
            name = instrument[ticker]['name']
            tickers.append(ticker)
            __series = []
            _tickerSeries = []
            for serie in ___series:
                for exp in serie:
                    strikes = serie[exp]['strikes']
                    _assets = []
                    for strike in strikes:
                        j = 1
                        dt = 'C'
                        while j <=2:
                            option = ticker + '_' + exp + '_' + str(strike) + '_' + dt
                            _assets.append(option)
                            assets.append(option)
                            dt = 'P'
                            j+=1
                    __series.append({exp: {'assets': _assets}})
                    tickerSeriesStrikes.append({ticker + '_' + exp: strikes})
                    series.append(ticker + '_' + exp)
                    _tickerSeries.append(exp)
        all.append({ticker: {'name': name, 'series': __series}})
        tickerSeries.append({ticker: _tickerSeries})

setCurrencys(['ETH', 'BTC'])
setTickers(tickers)
setAssets(assets)
setSeries(tickerSeries)
setStrikes(tickerSeriesStrikes)
setPrice()
setHV()
setLast()
setBest()
setTheo()

def getSeries(ticker, exp):
    for asset in all:
        if ticker in asset:
            series = asset[ticker]['series']
            for serie in series:
                if exp in serie:
                    assets = serie[exp]['assets']
                    break
            break
    return assets

def getState():
    out = []
    for serie in series:
        out.append({serie + '_TRADE':  str(mc.get('STATE_' + serie + '_TRADE')), serie + '_ORDER': str(mc.get('STATE_' + serie + '_ORDER'))})
    return out

def getBest(ticker, exp):
    assets = getSeries(ticker, exp)
    sell = []
    for asset in assets:
        sell.append({'asset': asset, 'type': 'sell', 'price': mc.get('BEST_SELL_' + asset)})
    buy = []
    for asset in assets:
        buy.append({'asset': asset, 'type': 'buy', 'price': mc.get('BEST_BUY_' + asset)})
    out = sell + buy
    return out

def getLast(ticker, exp):
    assets = getSeries(ticker, exp)
    out = []
    for asset in assets:
        price = mc.get('LAST_' + asset)
        if price is not None:
            out.append({'asset': asset, 'last': price})
    return out

def getTheo(ticker, exp):
    assets = getSeries(ticker, exp)
    out = []
    for asset in assets:
        out.append({'asset': asset, 'theo': mc.get('THEO_' + asset)})
    return out

def getSaldo():
    cursor = contracts.aggregate(
    [{
        '$group':{
        '_id': {'time': 'time'},
        'quant': {'$sum': 'quant'},
        'amount': {'$sum': 'amount'}
        }}
    ])
    res = []
    if (cursor):
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
    out = getState()
    return json.dumps(out, indent=1)

@route('/saldo')
def saldo():
    out = getSaldo()
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/signup', method=['OPTIONS', 'POST'])
@enable_cors
def signup():
    guardRate()
    body = jsonBody()
    if not body:
        abort(400, 'Bad Request: ожидается JSON-тело')
    key = body.get('key')
    seed = body.get('seed')
    password = body.get('password')
    email = body.get('email')
    if not (key and seed and password):
        abort(400, 'Нужны поля key, seed, password')
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
    return '[{"price": ' + str(mc.get('PRICE_' + ticker)) + ',"vola": '+ str(mc.get('HV_' + ticker)) + '}]'

@post('/user', method=['OPTIONS', 'POST'])
@enable_cors
def user():
    guardRate()
    body = jsonBody()
    if not body:
        abort(400, 'Bad Request: ожидается JSON-тело')
    userHash, password = authUser(body)
    if not userHash:
        abort(401, 'Bad User или Bad Password')
    question = body.get('question')
    yourHMAC = body.get('hmac')
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
        abort(400, 'Bad Question')
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/order', method=['OPTIONS', 'POST'])
@enable_cors
def order():
    guardRate()
    body = jsonBody()
    if not body:
        abort(400, 'Bad Request: ожидается JSON-тело')
    question = body.get('question') or {}
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
        return sendOrder(base, unit, ticker, exp, strike, dude, userHash, reqType, quant, asset, price, assets)

    if action in ('remove', 'edit'):
        id = question.get('id')
        if not id:
            abort(400, 'Нужно поле question.id')
        toHMAC = action + str(id)
        if not checkHMAC(password, toHMAC, yourHMAC):
            abort(401, 'Bad HMAC')
        order = getOrder(ObjectId(id))
        if not order:
            abort(404, 'Bad Order')
        user = order['user']
        type = order['type']
        quant = order['quant']
        asset = order['asset']
        price = order['price']
        ticker = order['ticker']
        exp = order['exp']
        strike = order['strike']
        dude = order['dude']
        if action == 'remove':
            out = removeOrder(ticker, exp, strike, dude, ObjectId(id), user, type, quant, asset, price)
            upBest(asset, type, getBestPrice(type, asset))
            return out
        # edit пока не реализован — отдельная задача ТЗ (#14).
        abort(501, 'Edit not implemented')

    abort(400, 'Bad Action')

@route('/river/orders/<ticker>/<exp>', method=['GET'])
def riverOrders(ticker, exp):
    out = outOrders(ticker, exp)
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/river/trades/<ticker>/<exp>', method=['GET'])
def riverTrades(ticker, exp):
    out = outTrades(ticker, exp)
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/best/<ticker>/<exp>', method=['GET'])
def best(ticker, exp):
    out = getBest(ticker, exp)
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/last/<ticker>/<exp>', method=['GET'])
def last(ticker, exp):
    out = getLast(ticker, exp)
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/theo/<ticker>/<exp>', method=['GET'])
def theo(ticker, exp):
    out = getTheo(ticker, exp)
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

@route('/orders/<asset>', method=['GET'])
def asset(asset):
    sell = getAsset('sell', asset)
    buy = getAsset('buy', asset)
    out = sell + buy
    response.content_type = 'application/json'
    return json.dumps(out, indent=1)

ADMIN_TOKEN = os.getenv('ADMIN_TOKEN')

@route('/admin/clear/<ticker>/<exp>/<price>')
def clearing(ticker, exp, price):
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
