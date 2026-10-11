import requests
import time
import os
import math
import json
from .settings import memdb, modb, CACHE_DIR, INSTRUMENTS
from .calculation import Calculation

calc = Calculation()
mc = memdb()
contracts = modb().contracts
orders = modb().orders


def _mcSet(key, value):
    """Записать значение в Memcached, не падая при недоступном Memcached.

    Memcached — кэш: его недоступность не должна валить API (задача ТЗ #25).
    """
    try:
        return mc.set(key, value)
    except Exception:
        # Хранилище недоступно — значение просто не кэшируется. Состояние
        # восстановит rebuildCache()/планировщик, когда Memcached вернётся.
        return 0


def _mcDelete(key):
    """Удалить ключ Memcached, не падая при недоступном хранилище."""
    try:
        return mc.delete(key)
    except Exception:
        return 0


def _mcGet(key):
    """Прочитать ключ Memcached, не падая при недоступном хранилище (#25).

    Возвращает None, как и штатный промах кэша: вызывающий код уже умеет
    обрабатывать отсутствие значения.
    """
    try:
        return mc.get(key)
    except Exception:
        return None

def getExp(exp):
    now = int(time.time())
    remain = (int(exp) - now) / 60 / 60 / 24 / 365
    return remain

def setState(ticker, exp, type, time):
    _mcSet('STATE_' + ticker + '_' + str(exp) + '_' + type, time)

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
        _mcSet('PRICE_' + ticker, price)

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
        _mcSet('HV_' + ticker, vola)

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
    return _mcGet('CURRENCYS')

def getTickers():
    return _mcGet('TICKERS')

def getAssets():
    return _mcGet('ASSETS')

def getSeries(ticker):
    return _mcGet(ticker + '_SERIES')

def getStrikes(tickerSerie):
    return _mcGet(tickerSerie + '_STRIKES')

def setCurrencys(currencys):
    return _mcSet('CURRENCYS', currencys)

def setTickers(tickers):
    _mcSet('TICKERS', tickers)

def setAssets(assets):
    _mcSet('ASSETS', assets)

def setSeries(tickerSeries):
    for series in tickerSeries:
        for ticker in series:
            _mcSet(ticker + '_SERIES', series[ticker])

def setStrikes(tickerSeriesStrikes):
    for seriesStrikes in tickerSeriesStrikes:
        for tickerSeries in seriesStrikes:
            _mcSet(tickerSeries + '_STRIKES', seriesStrikes[tickerSeries])

def loadCatalog():
    """Прочитать exchange/instruments.json и разложить каталог по Memcached.

    Общий bootstrap для API (api/app.py) и планировщика (api/theo.py): оба
    процесса должны видеть актуальные тикеры/серии/страйки/активы. Возвращает
    структуру `all` для публичного GET / (тикер → имя и серии с активами).

    Не падает, если Memcached недоступен (задача ТЗ #25): каталог всё равно
    возвращается вызывающему, а записи в Memcached молча пропускаются.
    """
    try:
        with open(INSTRUMENTS) as jsonData:
            instruments = json.load(jsonData)
    except (OSError, ValueError) as e:
        print('loadCatalog: не удалось прочитать %s: %s' % (INSTRUMENTS, e))
        return []
    allInstruments = []
    assets = []
    tickers = []
    series = []
    tickerSeries = []
    tickerSeriesStrikes = []
    for instrument in instruments:
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
                        while j <= 2:
                            option = ticker + '_' + exp + '_' + str(strike) + '_' + dt
                            _assets.append(option)
                            assets.append(option)
                            dt = 'P'
                            j += 1
                    __series.append({exp: {'assets': _assets}})
                    tickerSeriesStrikes.append({ticker + '_' + exp: strikes})
                    series.append(ticker + '_' + exp)
                    _tickerSeries.append(exp)
        allInstruments.append({ticker: {'name': name, 'series': __series}})
        tickerSeries.append({ticker: _tickerSeries})
    setCurrencys(['ETH', 'BTC'])
    setTickers(tickers)
    setAssets(assets)
    setSeries(tickerSeries)
    setStrikes(tickerSeriesStrikes)
    return allInstruments

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
    # Возвращает {ticker: price} — планировщик по нему решает, что пересчитывать
    # (задача ТЗ #30: THEO считаем только для изменившихся цен).
    prices = {}
    tickers = getTickers() or []
    for ticker in tickers:
        result = bybitGet('/tickers', {'category': 'spot', 'symbol': bybitSymbol(ticker)})
        if not result or not result.get('list'):
            continue
        last = float(result['list'][0]['lastPrice'])
        price = round(last * 1000000)
        _mcSet('PRICE_' + ticker, price)
        prices[ticker] = price
    return prices

def setLast():
    # LAST — цена последней сделки по активу. Memcached не переживает рестарт,
    # поэтому восстанавливаем из Mongo (contracts) при старте. Перед пересчётом
    # чистим прежние LAST_* по каталогу, иначе останутся ключи мёртвых активов.
    for asset in getAssets() or []:
        _mcDelete('LAST_' + asset)
    # Mongo может быть недоступен — LAST останется не восстановленным, но это
    # не должно валить bootstrap API (задача ТЗ #25).
    try:
        # $sort по времени до $group — иначе $last берёт произвольный документ.
        cursor = contracts.aggregate([
        {'$sort': {'time': 1}},
        {'$group': {'_id': '$asset',
            'time': {'$max': '$time'},
            'amount': {'$last': '$amount'},
            'quant': {'$last': '$quant'}
            }
        }])
    except Exception as e:
        print('setLast: Mongo недоступен: %s' % e)
        return
    for doc in cursor:
        # Пропускаем закрытые позиции (quant == 0) — иначе деление на ноль.
        if not doc['quant']:
            continue
        _mcSet('LAST_' + doc['_id'], int(round(doc['amount'] / doc['quant'])))

def upLast(asset, price):
    _mcSet('LAST_' + asset, price)

def setBest():
    # BEST — лучшая цена по активу из открытых заявок Mongo. Memcached не
    # переживает рестарт; чистим ключи каталога и пере создаём из orders.
    for asset in getAssets() or []:
        _mcDelete('BEST_SELL_' + asset)
        _mcDelete('BEST_BUY_' + asset)
    types = ['sell', 'buy']
    for type in types:
        if type == 'sell':
            dir = '$min'
        else:
            dir = '$max'
        try:
            cursor = orders.aggregate([
            {'$match': {'type': type}},
            {'$group': {'_id': '$asset',
                'price': {dir: '$price'}
                }
            }])
        except Exception as e:
            # Mongo недоступен — BEST останется пустым, API не падает (#25).
            print('setBest: Mongo недоступен: %s' % e)
            return
        for doc in cursor:
            _mcSet('BEST_' + type.upper() + '_' + doc['_id'], doc['price'])

def upBest(asset, type, price):
    key = 'BEST_' + type.upper() + '_' + asset
    if price:
        _mcSet(key, price)
    else:
        _mcDelete(key)

def setTheo(ticker=None):
    """Пересчитать THEO по сериям тикера (или всем тикерам).

    Задача ТЗ #30: прежняя версия каждую минуту считала THEO по ВСЕМ тикерам,
    сериям и страйкам — полный перебор каталога. Теперь тикер можно передать
    явно (`setTheo('ETH_BTC')`), чтобы планировщик не трогал те инструменты,
    которые не менялись. Аргумент по умолчанию сохраняет прежнее поведение
    (полный пересчёт) для bootstrap `rebuildCache()`.
    """
    tickers = [ticker] if ticker else (getTickers() or [])
    for tick in tickers:
        V = _mcGet('HV_' + tick)
        S = _mcGet('PRICE_' + tick)
        # Без цены или волатильности (нет _cache) theo не считаем: модель
        # вернула бы intrinsic-стоимость с нулевыми входами, что бессмысленно.
        if V is None or S is None:
            continue
        series = getSeries(tick) or []
        for serie in series:
            T = getExp(serie)
            strikes = getStrikes(tick + '_' + serie) or []
            for strike in strikes:
                K = strike
                j = 1
                dt = 'C'
                while j <= 2:
                    _mcSet('THEO_' + tick + '_' + serie + '_' + str(strike) + '_' + dt, calc.theo(S, K, V, T, dt))
                    dt = 'P'
                    j += 1

def rebuildCache():
    """Пересобрать рыночный кэш из внешних источников и из Mongo.

    Memcached — не только кэш, но и единственный источник истины для
    PRICE/HV/LAST/BEST/THEO (см. DEVELOPER_GUIDE §4.4). После рестарта
    Memcached эти ключи теряются, и стол «пропадает» (задача ТЗ #19). Эта
    функция вызывается при старте API и планировщиком (api/theo.py), чтобы
    восстановить состояние из Bybit (PRICE/HV), Mongo-контрактов (LAST),
    Mongo-заявок (BEST) и заново посчитать THEO.

    Порядок существенен: THEO зависит от PRICE и HV. Каждый шаг сам по себе
    устойчив к недоступности своего хранилища (задача ТЗ #25), поэтому
    недоступный Mongo/Influx/Memcached не валит здесь весь bootstrap.
    """
    setPrice()
    setHV()
    setLast()
    setBest()
    setTheo()
