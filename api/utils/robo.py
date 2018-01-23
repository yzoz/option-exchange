import requests, time
from inc.utils import fromTS
from inc.settings import indb
import numpy as np
import math
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams as rc
#from inc.settings import memdb

#mc = memdb()

#CREATE RETENTION POLICY "monthly" ON "spot" DURATION INF REPLICATION 1 SHARD DURATION 4w DEFAULT

path = '../public/img/'

rc.update({'font.size': 21, 'font.family': 'Courier, Courier New, Terminal, monospace'})
db = indb('spot')
timenow = int(str(time.time()).split('.')[0])

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

def movingaverage (values, window):
    weights = np.repeat(1.0, window)/window
    sma = np.convolve(values, weights, 'valid')
    return sma

def getTrades(token, unit, exchange):
    step = 720
    last = getLast(token, unit, exchange)
    start = last['time'] + 1
    end = start + step - 1
    while end <= timenow:
        url = 'https://poloniex.com/public?command=returnTradeHistory&currencyPair=BTC_ETH&start='+str(start)+'&end='+str(end)
        try:
            res = requests.get(url).json()
        except requests.exceptions.RequestException as e:
            print('Error: {}'.format(e))
        else:
            res = sorted(res, key=lambda k: k['tradeID'])
        q = len(res)
        buy = 0
        sell = 0
        price = 0
        if q:
            for row in res:
                if row['type'] == 'buy':
                    buy = float(buy + float(row['amount']))
                else:
                    sell = float(sell + float(row['amount']))
                price = float(price + float(row['rate']))
            price = round(price / q, 8)
            buy = int(buy)
            sell = int(sell)
            data = [
                {
                    "measurement": 'ETH',
                    "tags": {
                        "unit": 'BTC',
                        "exchange": 'POL'
                    },
                    "time": end,
                    "fields": {
                        "price": price,
                        "buy": buy,
                        "sell": sell
                    }
                }
            ]
            db.write_points(data, time_precision='s')
        print(fromTS(start), ' : ',fromTS(end) , ' | ', start, ' ||| ', price, buy, sell)
        start += step
        end += step
    with open('../_cache/ETH_BTC_PRICE', 'w') as f:
        f.write(str(round(price * 1000000)))
        f.close()

def volatility(weighted):
    period = 365
    try:
        res = requests.get('https://poloniex.com/public?command=returnChartData&currencyPair=BTC_ETH&start=1450656000&end=9999999999&period=86400').json()
        #with open('../_cache/ETH24h.json') as jsonData:
            #res = json.load(jsonData)
    except requests.exceptions.RequestException as e:
        print('Error: {}'.format(e))
    else:
        prices = []
        for row in res:
            prices.append([row['weightedAverage'], row['date']])
    
        i = 1
        n = len(prices)
        logPrices = []
        logDates = []
        while i < n:
            logPrices.append(np.log(prices[i][0]/prices[i-1][0]))
            logDates.append(prices[i-1][1])
            i+=1
        i = 0
        j = weighted
        n = len(logPrices)
        stdPrices = []
        stdDates = []
        while j < n:
            stdPrices.append(np.std(logPrices[i:j]) * math.sqrt(period) * 100)
            stdDates.append(fromTS(logDates[j]))
            i+=1
            j+=1
        fig = plt.figure(figsize=(30,15))
        a=fig.gca()
        a.set_frame_on(False)
        plt.plot(stdDates, stdPrices, color='#000000')
        plt.title("ETH/BTC Historical Volatility")
        plt.ylabel("HV" + str(weighted))
        plt.xlabel("yzoz.com")
        plt.grid(True)
        plt.savefig(path + 'eth-btc-volatility-' + str(weighted) + '.png', dpi=72, bbox_inches='tight', pad_inches=0)
        #plt.show()
        plt.close()
        with open('../_cache/ETH_BTC_HV_' + str(weighted), 'w') as f:
            f.write(str(round(stdPrices[len(stdPrices) - 1] / 100, 5)))
            f.close()
        #mc.set('ETHHV', round(stdPrices[len(stdPrices) - 1] / 100, 5), time=0)
        print('Make Vola!' + str(weighted))
        #logging.info('Make Vola!')

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
            #print(fromTS(row['time']))
    ma = movingaverage(volume, 13)
    fig = plt.figure(figsize=(30,15))
    a=fig.gca()
    a.set_frame_on(False)
    plt.plot(date[len(date)-len(ma):], ma, color='#000000')
    plt.title("ETH/BTC Accumulation/Distribution")
    plt.ylabel("Relative Volume")
    plt.xlabel("yzoz.com")
    plt.grid(True)
    plt.savefig(path + 'eth-btc-ac-' + name + '.png', dpi=72, bbox_inches='tight', pad_inches=0)
    #plt.show()
    plt.close()
    print('Make AC! ' + name)
    #logging.info('Make AC!')


def bubbles(period, bubble, vol, name):
    
    res = db.query('SELECT "price", "buy", "sell" FROM "ETH" WHERE "time" > %s' % (period), epoch='s')
        
    x = []
    y = []
    area = []
    colors = []
    v = 0
    
    for row in res:
        first = row[0]['time']
        last = row[len(row)-1]['time']
        #print(row)
        for row in row:
            v = int(row['buy'] - row['sell'])
            if abs(v) >= vol:
                x.append(fromTS(row['time']))
                y.append(row['price'])
                area.append(abs(int(v/bubble)))
                if v > 0:
                    color = '#00C180'
                else:
                    color = '#FF2D33'
                colors.append(color)
    hi = max(y, key=float)
    low = min(y, key=float)
    fig = plt.figure(figsize=(30,15))
    a=fig.gca()
    a.set_frame_on(False)
    #a.set_xticks([])
    #a.set_yticks([])
    plt.scatter(x=x, y=y, s=area, c=colors, linewidths=0, alpha=0.5)
    plt.ylim([low - 0.000025, hi + 0.000025])
    plt.xlim([fromTS(first - 3600),fromTS(last + 3600)])
    plt.title("ETH/BTC Volume Bubbles")
    plt.ylabel("Price")
    plt.xlabel("yzoz.com")
    plt.grid(True)
    plt.savefig(path +  'eth-btc-bubbles-' + name + '.png', dpi=72, bbox_inches='tight', pad_inches=0)
    #plt.show()
    plt.close()
    print('Make Bubbles! ' + name)
    #logging.info('Make Bubbles!')

intervalV = {}
intervalV[0] = {'weighted': 7}
intervalV[1] = {'weighted': 30}
intervalV[2] = {'weighted': 60}
intervalV[3] = {'weighted': 90}

for row in intervalV:
    weighted = intervalV[row]['weighted']
    volatility(weighted)

getTrades('ETH','BTC','POL')

def makeCharts(period, bubble, vol, name):
    bubbles(period, bubble, vol, name)
    ac(period, name)

interval = {}
interval[0] = {'name': 'week', 'timeback': 604800, 'bubble': 10, 'vol': 1}
interval[1] = {'name': 'month', 'timeback': 2419200, 'bubble': 100, 'vol': 10}
interval[2] = {'name': 'month4', 'timeback': 9676800, 'bubble': 250, 'vol': 5000}
interval[3] = {'name': 'year', 'timeback': 29030400, 'bubble': 250, 'vol': 7500}
interval[4] = {'name': 'full', 'timeback': timenow, 'bubble': 500, 'vol': 15000}

for row in interval:
    name = interval[row]['name']
    timeback = interval[row]['timeback']
    timestart = int(str(timenow - timeback) + '000000000')
    bubble = interval[row]['bubble']
    vol = interval[row]['vol']
    makeCharts(timestart, bubble, vol, name)