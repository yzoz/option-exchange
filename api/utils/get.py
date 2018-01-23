import requests, logging, time
from influxdb import InfluxDBClient
logging.getLogger("requests").setLevel(logging.WARNING)
from inc.utils import getLast, indb, toTS, fromTS
db = InfluxDBClient('localhost', 8086, 'root', 'root', 'spot')
#https://poloniex.com/public?command=returnTradeHistory&currencyPair=BTC_ETH&start=1519939800+&end=1519943400
#CREATE RETENTION POLICY "monthly" ON "spot" DURATION INF REPLICATION 1 SHARD DURATION 4w DEFAULT
db = indb()
step = 720
last = getLast('ETH','BTC','POL')
start = last['time'] + 1
end = start + step - 1
stop = time.time()

while end <= stop:
    url = 'https://poloniex.com/public?command=returnTradeHistory&currencyPair=BTC_ETH&start='+str(start)+'&end='+str(end)
    
    #print(fromTS(start), ' | ', fromTS(end))
    #print(url)
    
    res = requests.get(url).json()
    #res = sorted(res, key=lambda k: k['tradeID'])
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
