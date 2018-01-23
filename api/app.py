import json
import bottle
from bottle import hook, route, run, template, debug, post, request, response
from bson.objectid import ObjectId
from inc.settings import modb, memdb
from inc.influx import outOrders, outTrades
from inc.utils import pyMode, getTime, splitAsset, hashUser, checkHMAC
from inc.orders import userOrders, removeOrder, getOrder, \
     getAsset, getBestPrice
from inc.contracts import userContracts, userTrades
from inc.users import allUsers, checkUser, userBalances, clearContracts
from inc.trade import sendOrder
from inc.mc import setPrice, setHV, setLast, setBest, setAssets, setTickers, setSeries, setStrikes, setTheo, upBest, setCurrencys, getCurrencys


def enable_cors(fn):
    def _enable_cors(*args, **kwargs):
        if bottle.request.method != 'OPTIONS':
            return fn(*args, **kwargs)
    return _enable_cors

# @hook('before_request')


@hook('after_request')
def enableCORSAfterRequestHook():
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'

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

with open('../exchange/instruments.json') as jsonData:
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
    if (request.json['key'] and request.json['seed']):
        key = request.json['key']
        hash = hashUser(key )
        seed = request.json['seed']
        email = request.json['email']
        cursor = users.insert_one({
        'hash': hash,
        'seed': seed,
        'email': email,
        'time': getTime(),
        'balances': {
                'ETH': 1000,
                'BTC': 100000000
                }
        }).inserted_id
        if (cursor):
            return 'User ' + hash  + ' with Key "' + key  + '" and Seed "' + seed + '" created! Keep it safe.!. You Have 1000 Wei & 100000000 Satoshi'
    else:
        return 'Be shy of something'

@route('/counters/<ticker>')
def counters(ticker):
    response.content_type = 'application/json'
    return '[{"price": ' + str(mc.get('PRICE_' + ticker)) + ',"vola": '+ str(mc.get('HV_' + ticker)) + '}]'

@post('/user', method=['OPTIONS', 'POST'])
@enable_cors
def user():
    if (request.json['user'] and request.json['hmac'] and request.json['question']):
        user = request.json['user']
        userHash = hashUser(user)
        seed = checkUser(userHash)
        if seed:
            yourHMAC = request.json['hmac']
            question = request.json['question']
            if checkHMAC(seed, question, yourHMAC):
                if question == 'contracts':
                    out = userContracts(userHash)
                    response.content_type = 'application/json'
                    return json.dumps(out, indent=1)
                if question == 'orders':
                    out = userOrders(userHash)
                    response.content_type = 'application/json'
                    return json.dumps(out, indent=1)
                if question == 'trades':
                    out = userTrades(userHash)
                    response.content_type = 'application/json'
                    return json.dumps(out, indent=1)
                if question == 'balances':
                    out = userBalances(userHash, assets)
                    response.content_type = 'application/json'
                    return json.dumps(out, indent=1)
                else:
                    out = 'Bad Question'
                    return out
            else:
                out = 'Bad HMAC'
                return out
        else:
            out ='Bad User'
            return out
    else:
        out = 'Be shy of something'
        return out

@route('/order', method=['OPTIONS', 'POST'])
@enable_cors
def order():
    if (request.json['user'] and request.json['hmac'] and request.json['question']['action']):
        user = request.json['user']
        action = request.json['question']['action']
        userHash = hashUser(user)
        seed = checkUser(userHash)
        if seed:
            yourHMAC = request.json['hmac']
            if action == 'send':
                if (request.json['question']['type'] and request.json['question']['quant'] and request.json['question']['asset'] and request.json['question']['price']):
                    action = request.json['question']['action']
                    user = userHash
                    reqType = request.json['question']['type']
                    quant = request.json['question']['quant']
                    reqAsset = request.json['question']['asset']
                    price = request.json['question']['price']
                    toHMAC = action + reqType + str(quant) + reqAsset + str(price)
                    if checkHMAC(seed, toHMAC, yourHMAC):
                        if ((reqType == 'buy' or reqType =='sell')):
                            type = reqType
                        else:
                            out = 'Bad Type! You can only Buy & Sell'
                            return out

                        try:
                            int(quant)
                        except:
                            out = 'Bad Quantity!'
                            return out
                        else:
                            if (int(quant) > 0):
                                quant = int(quant)
                            else:
                                out = 'Quantity must be > 0!'
                                return out

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
                            else:
                                asset = None
                        if not asset:
                            out = 'Bad Asset!'
                            return out

                        try:
                            int(price)
                        except:
                            out = 'Bad Price!'
                            return out
                        else:
                            if (int(price) > 0):
                                price = int(price)
                            else:
                                out = 'Price must be > 0!'
                                return out
                        out = sendOrder(base, unit, ticker, exp, strike, dude, user, type, quant, asset, price, assets)
                        return out
                    else:
                        out = 'Bad HMAC ' + str(toHMAC)
                        return out
                else:
                    out = 'Be shy of something'
                    return out
            else:
                if (request.json['question']['id']):
                    id = request.json['question']['id']
                    toHMAC = action + id
                    if checkHMAC(seed, toHMAC, yourHMAC):
                        order = getOrder(ObjectId(id))
                        if order:
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
                            if action == 'edit':
                                return
                        else:
                            out = 'Bad Order'
                            return out
                    else:
                        out = 'Bad HMAC ' + str(toHMAC)
                        return out
                else:
                    out = 'Be shy of something'
                    return out
        else:
            out ='Bad User'
            return out
    else:
        out = 'Be shy of something'
        return out

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

@route('/admin/clear/<ticker>/<exp>/<price>')
def clearing(ticker, exp, price):
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
        balances.append({'hash': user['hash'], 'seed': user['seed'], 'balance': balance, 'clear': clear, 'trades': trades})
    return template('clear', title='Clearing', price=price, balances=balances, realised=realised, clearTotal=clearTotal)

if mode == 'dev':
    debug(mode=True)
    run(debug=True, reloader=True, host='0.0.0.0', port=69)
else:
    app = application = bottle.default_app()
