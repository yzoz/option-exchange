import os
import time
from inc.mc import bybitGet, bybitSymbol
from inc.settings import indb, ROOT, CACHE_DIR
from inc.utils import fromTS
import numpy as np
import math
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams as rc

path = os.path.join(ROOT, 'public', 'img') + os.sep

rc.update({'font.size': 21, 'font.family': 'Courier, Courier New, Terminal, monospace'})
db = indb('spot')
timenow = int(str(time.time()).split('.')[0])


def symbol(token, unit):
    return token + unit


def getLast(token, unit, exchange):
    if not unit:
        res = db.query('SELECT LAST("price") FROM "%s" WHERE "exchange"=\'%s\'' % (token, exchange), epoch='s')
    elif not exchange:
        res = db.query('SELECT LAST("price") FROM "%s" WHERE "unit"=\'%s\'' % (token, unit), epoch='s')
    else:
        res = db.query('SELECT LAST("price") FROM "%s" WHERE "unit"=\'%s\' AND "exchange"=\'%s\'' % (token, unit, exchange), epoch='s')
    for row in res:
        price = row[0]['last']
        times = row[0]['time']
    return {'price': price, 'time': times}


def movingaverage(values, window):
    weights = np.repeat(1.0, window) / window
    sma = np.convolve(values, weights, 'valid')
    return sma


def klines(token, unit, interval='D', limit=1000):
    """Дневные (по умолчанию) свечи Bybit, хронологический порядок."""
    result = bybitGet('/kline', {
        'category': 'spot', 'symbol': symbol(token, unit),
        'interval': interval, 'limit': limit})
    if not result or not result.get('list'):
        return []
    # Bybit отдаёт свечи от новых к старым — разворачиваем.
    return [[int(row[0]), float(row[1]), float(row[2]), float(row[3]),
             float(row[4]), float(row[5])] for row in result['list']][::-1]


def getTrades(token, unit, exchange):
    """Записать свечи в InfluxDB ('spot') и обновить _cache/<TICKER>_PRICE."""
    rows = klines(token, unit)
    price = 0
    for row in rows:
        times = int(row[0] / 1000)
        o, h, l, c, v = row[1], row[2], row[3], row[4], row[5]
        # Для графика Accumulation/Distribution объём относим к «покупкам»,
        # если свеча закрылась выше открытия, иначе — к «продажам».
        buy = int(v) if c >= o else 0
        sell = int(v) if c < o else 0
        price = c
        data = [{
            'measurement': token,
            'tags': {'unit': unit, 'exchange': exchange},
            'time': times,
            'fields': {'price': price, 'buy': buy, 'sell': sell}
        }]
        db.write_points(data, time_precision='s')
    if price:
        with open(os.path.join(CACHE_DIR, token + '_' + unit + '_PRICE'), 'w') as f:
            f.write(str(round(price * 1000000)))


def volatility(weighted):
    period = 365
    rows = klines('ETH', 'BTC')
    if len(rows) < weighted + 1:
        return
    prices = [[row[4], int(row[0] / 1000)] for row in rows]

    logPrices = []
    logDates = []
    for i in range(1, len(prices)):
        logPrices.append(np.log(prices[i][0] / prices[i - 1][0]))
        logDates.append(prices[i - 1][1])

    stdPrices = []
    stdDates = []
    i = 0
    j = weighted
    while j < len(logPrices):
        stdPrices.append(np.std(logPrices[i:j]) * math.sqrt(period) * 100)
        stdDates.append(fromTS(logDates[j]))
        i += 1
        j += 1

    fig = plt.figure(figsize=(30, 15))
    a = fig.gca()
    a.set_frame_on(False)
    plt.plot(stdDates, stdPrices, color='#000000')
    plt.title("ETH/BTC Historical Volatility")
    plt.ylabel("HV" + str(weighted))
    plt.xlabel("yzoz.com")
    plt.grid(True)
    plt.savefig(path + 'eth-btc-volatility-' + str(weighted) + '.png', dpi=72, bbox_inches='tight', pad_inches=0)
    plt.close()
    if stdPrices:
        with open(os.path.join(CACHE_DIR, 'ETH_BTC_HV_' + str(weighted)), 'w') as f:
            f.write(str(round(stdPrices[len(stdPrices) - 1] / 100, 5)))
    print('Make Vola!' + str(weighted))


def ac(period, name):
    res = db.query('SELECT "price", "buy", "sell" FROM "ETH" WHERE "time" > %s' % (period), epoch='s')
    vol = 0
    date = []
    volume = []
    for row in res:
        for row in row:
            vol = vol + row['buy'] - row['sell']
            volume.append(vol)
            date.append(fromTS(row['time']))
    if len(volume) < 13:
        return
    ma = movingaverage(volume, 13)
    fig = plt.figure(figsize=(30, 15))
    a = fig.gca()
    a.set_frame_on(False)
    plt.plot(date[len(date) - len(ma):], ma, color='#000000')
    plt.title("ETH/BTC Accumulation/Distribution")
    plt.ylabel("Relative Volume")
    plt.xlabel("yzoz.com")
    plt.grid(True)
    plt.savefig(path + 'eth-btc-ac-' + name + '.png', dpi=72, bbox_inches='tight', pad_inches=0)
    plt.close()
    print('Make AC! ' + name)


def bubbles(period, bubble, vol, name):
    res = db.query('SELECT "price", "buy", "sell" FROM "ETH" WHERE "time" > %s' % (period), epoch='s')

    x = []
    y = []
    area = []
    colors = []
    v = 0
    first = None
    last = None
    for row in res:
        first = row[0]['time']
        last = row[len(row) - 1]['time']
        for row in row:
            v = int(row['buy'] - row['sell'])
            if abs(v) >= vol:
                x.append(fromTS(row['time']))
                y.append(row['price'])
                area.append(abs(int(v / bubble)))
                colors.append('#00C180' if v > 0 else '#FF2D33')
    if not y:
        return
    hi = max(y, key=float)
    low = min(y, key=float)
    fig = plt.figure(figsize=(30, 15))
    a = fig.gca()
    a.set_frame_on(False)
    plt.scatter(x=x, y=y, s=area, c=colors, linewidths=0, alpha=0.5)
    plt.ylim([low - 0.000025, hi + 0.000025])
    plt.xlim([fromTS(first - 3600), fromTS(last + 3600)])
    plt.title("ETH/BTC Volume Bubbles")
    plt.ylabel("Price")
    plt.xlabel("yzoz.com")
    plt.grid(True)
    plt.savefig(path + 'eth-btc-bubbles-' + name + '.png', dpi=72, bbox_inches='tight', pad_inches=0)
    plt.close()
    print('Make Bubbles! ' + name)


intervalV = {
    0: {'weighted': 7},
    1: {'weighted': 30},
    2: {'weighted': 60},
    3: {'weighted': 90},
}

for row in intervalV:
    volatility(intervalV[row]['weighted'])

getTrades('ETH', 'BTC', 'BYB')


def makeCharts(period, bubble, vol, name):
    bubbles(period, bubble, vol, name)
    ac(period, name)


interval = {
    0: {'name': 'week', 'timeback': 604800, 'bubble': 10, 'vol': 1},
    1: {'name': 'month', 'timeback': 2419200, 'bubble': 100, 'vol': 10},
    2: {'name': 'month4', 'timeback': 9676800, 'bubble': 250, 'vol': 5000},
    3: {'name': 'year', 'timeback': 29030400, 'bubble': 250, 'vol': 7500},
    4: {'name': 'full', 'timeback': timenow, 'bubble': 500, 'vol': 15000},
}

for row in interval:
    name = interval[row]['name']
    timeback = interval[row]['timeback']
    timestart = int(str(timenow - timeback) + '000000000')
    makeCharts(timestart, interval[row]['bubble'], interval[row]['vol'], name)
