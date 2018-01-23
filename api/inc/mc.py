import requests, time
from .settings import memdb, modb
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
    tickers = getTickers()
    for ticker in tickers:
        f = open('../_cache/' + ticker + '_PRICE')
        price = int(f.read())
        f.close()
        mc.set('PRICE_' + ticker, price)

def setHV():
    tickers = getTickers()
    for ticker in tickers:
        f = open('../_cache/' + ticker + '_HV_7')
        vola = float(f.read())
        f.close()
        mc.set('HV_' + ticker, vola)

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

def setCurrent():
    tickers = getTickers()
    for ticker in tickers:
        url = 'https://poloniex.com/public?command=returnTicker'
        try:
            res = requests.get(url).json()
        except requests.exceptions.RequestException as e:
            print('Error: {}'.format(e))
        else:
            mc.set('PRICE_' + ticker, round(float(res['BTC_ETH']['last']) * 1000000))

def setLast():
    cursor = contracts.aggregate([
    {'$group': {'_id': '$asset',
        'time': {'$max': '$time'},
        'amount': {'$last': '$amount'},
        'quant': {'$last': '$quant'}
        }
    }])
    for doc in cursor:
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
    tickers = getTickers()
    for ticker in tickers:
        V = mc.get('HV_' + ticker)
        S = mc.get('PRICE_' + ticker)
        series = getSeries(ticker)
        for serie in series:
            T = getExp(serie)
            strikes = getStrikes(ticker + '_' + serie)
            for strike in strikes:
                K = strike
                j = 1
                dt = 'C'
                while j <= 2:
                    mc.set('THEO_' + ticker + '_' + serie + '_' + str(strike) + '_' + dt, calc.theo(S, K, V, T, dt))
                    dt = 'P'
                    j+=1