import requests, time, os, math
from .settings import memdb, modb, CACHE_DIR
from .calculation import Calculation

calc = Calculation()
mc = memdb()
contracts = modb().contracts
orders = modb().orders

def getExp(exp):
    now = int(time.time())
    remain = (int(exp) - now) / 60 / 60 / 24 / 365
    return remain

def setState(ticker, exp, type, time):
    mc.set('STATE_' + ticker + '_' + str(exp) + '_' + type, time)

def setPrice():
    # _cache необязателен: при отсутствии файла цена берётся с Bybit.
    # Если недоступны оба источника — цена остаётся не выставленной, но
    # приложение не падает.
    tickers = getTickers() or []
    for ticker in tickers:
        path = os.path.join(CACHE_DIR, ticker + '_PRICE')
        try:
            with open(path) as f:
                price = int(f.read())
        except (FileNotFoundError, ValueError):
            result = bybitGet('/tickers', {'category': 'spot', 'symbol': bybitSymbol(ticker)})
            if not result or not result.get('list'):
                continue
            price = round(float(result['list'][0]['lastPrice']) * 1000000)
        mc.set('PRICE_' + ticker, price)

def setHV():
    # _cache необязателен: при отсутствии файла HV оценивается по дневным
    # свечам Bybit (годовая волатильность лог-доходностей).
    tickers = getTickers() or []
    for ticker in tickers:
        path = os.path.join(CACHE_DIR, ticker + '_HV_7')
        try:
            with open(path) as f:
                vola = float(f.read())
        except (FileNotFoundError, ValueError):
            vola = bybitHV(ticker)
            if vola is None:
                continue
        mc.set('HV_' + ticker, vola)

def bybitHV(ticker, days=7):
    # Годовая историческая волатильность по дневным закрытиям (interval=D).
    result = bybitGet('/kline', {
        'category': 'spot', 'symbol': bybitSymbol(ticker),
        'interval': 'D', 'limit': days + 1})
    if not result or not result.get('list'):
        return None
    # Bybit отдаёт свечи от новых к старым — разворачиваем в хронологию.
    closes = [float(row[4]) for row in result['list']][::-1]
    if len(closes) < 2:
        return None
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return round(math.sqrt(var) * math.sqrt(365), 5)

def getCurrencys():
    return mc.get('CURRENCYS')

def getTickers():
    return mc.get('TICKERS')

def getAssets():
    return mc.get('ASSETS')

def getSeries(ticker):
    return mc.get(ticker + '_SERIES')

def getStrikes(tickerSerie):
    return mc.get(tickerSerie + '_STRIKES')

def setCurrencys(currencys):
    return mc.set('CURRENCYS', currencys)

def setTickers(tickers):
    mc.set('TICKERS', tickers)

def setAssets(assets):
    mc.set('ASSETS', assets)

def setSeries(tickerSeries):
    for series in tickerSeries:
        for ticker in series:
            mc.set(ticker + '_SERIES', series[ticker])

def setStrikes(tickerSeriesStrikes):
    for seriesStrikes in tickerSeriesStrikes:
        for tickerSeries in seriesStrikes:
            mc.set(tickerSeries + '_STRIKES', seriesStrikes[tickerSeries])

BYBIT_API = 'https://api.bybit.com/v5/market'

def bybitSymbol(ticker):
    # 'ETH_BTC' -> spot-символ Bybit 'ETHBTC'.
    return ticker.replace('_', '')

def bybitGet(path, params):
    """GET к публичному API Bybit v5; возвращает result или None при ошибке."""
    try:
        res = requests.get(BYBIT_API + path, params=params, timeout=10).json()
    except requests.exceptions.RequestException as e:
        print('Bybit error: {}'.format(e))
        return None
    if res.get('retCode') != 0:
        print('Bybit error: {}'.format(res.get('retMsg')))
        return None
    return res.get('result')

def setCurrent():
    # Живой источник цены (Bybit spot) вместо мёртвого Poloniex.
    tickers = getTickers() or []
    for ticker in tickers:
        result = bybitGet('/tickers', {'category': 'spot', 'symbol': bybitSymbol(ticker)})
        if not result or not result.get('list'):
            continue
        last = float(result['list'][0]['lastPrice'])
        mc.set('PRICE_' + ticker, round(last * 1000000))

def setLast():
    cursor = contracts.aggregate([
    {'$group': {'_id': '$asset',
        'time': {'$max': '$time'},
        'amount': {'$last': '$amount'},
        'quant': {'$last': '$quant'}
        }
    }])
    for doc in cursor:
        # Пропускаем закрытые позиции (quant == 0) — иначе деление на ноль.
        if not doc['quant']:
            continue
        mc.set('LAST_' + doc['_id'], int(round(doc['amount'] / doc['quant'])))

def upLast(asset, price):
    mc.set('LAST_' + asset, price)

def setBest():
    types = ['sell', 'buy']
    for type in types:
        if type == 'sell':
            dir = '$min'
        else:
            dir = '$max'
        cursor = orders.aggregate([
        {'$match': {'type': type}},
        {'$group': {'_id': '$asset',
            'price': {dir: '$price'}
            }
        }])
        for doc in cursor:
            mc.set('BEST_' + type.upper() + '_' + doc['_id'], doc['price'])

def upBest(asset, type, price):
    key = 'BEST_' + type.upper() + '_' + asset
    if price:
        mc.set(key, price)
    else:
        mc.delete(key)

def setTheo():
    tickers = getTickers() or []
    for ticker in tickers:
        V = mc.get('HV_' + ticker)
        S = mc.get('PRICE_' + ticker)
        # Без цены или волатильности (нет _cache) theo не считаем: модель
        # вернула бы intrinsic-стоимость с нулевыми входами, что бессмысленно.
        if V is None or S is None:
            continue
        series = getSeries(ticker) or []
        for serie in series:
            T = getExp(serie)
            strikes = getStrikes(ticker + '_' + serie) or []
            for strike in strikes:
                K = strike
                j = 1
                dt = 'C'
                while j <= 2:
                    mc.set('THEO_' + ticker + '_' + serie + '_' + str(strike) + '_' + dt, calc.theo(S, K, V, T, dt))
                    dt = 'P'
                    j+=1