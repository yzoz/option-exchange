import threading
from .orders import alreadyOrders, getBestPrice, sendLimit, matchOrder
from .contracts import alreadyContracts, makeDeal
from .users import userBalances
from .mc import upBest

# Пер-тикерные блокировки: сериализуют матчинг в рамках процесса, чтобы два
# параллельных ордера не выкупали одну и ту же встречную заявку. Само по себе
# снятие заявки атомарно (см. orders.matchOrder), блокировка убирает гонку
# между проверкой баланса и сделкой.
_locks = {}
_locks_guard = threading.Lock()

def tickerLock(ticker):
    with _locks_guard:
        lock = _locks.get(ticker)
        if lock is None:
            lock = threading.Lock()
            _locks[ticker] = lock
        return lock

def checkOrder(base, unit, ticker, exp, strike, dude, user, type, quant, asset, price, assets):
    allContracts = alreadyContracts(user)
    allSellOrders = alreadyOrders(user, 'sell')
    allBuyOrders = alreadyOrders(user, 'buy')
    balances = userBalances(user, assets)
    baseBalance = balances['available'][base]
    unitBalance = balances['available'][unit]
    if asset in allContracts and allContracts[asset] < 0 and type == 'buy':
        if asset in allBuyOrders:
            avail = -allContracts[asset] - allBuyOrders[asset]
        else:
            avail = -allContracts[asset]
        if unitBalance >= price * (quant - avail):
            send = True
        else:
            send = False
    elif asset in allContracts and allContracts[asset] > 0 and type == 'sell':
        if asset in allSellOrders:
            avail = allContracts[asset] - allSellOrders[asset]
        else:
            avail = allContracts[asset]
        if baseBalance >= (quant - avail) and dude == 'C':
            send = True
        elif unitBalance >= int(strike) * (quant - avail) and dude == 'P':
            send = True
        else:
            send = False
    else:
        if type == 'sell' and dude == 'C' and baseBalance >= quant:
            send = True
        elif type == 'sell' and dude == 'P' and unitBalance >= int(strike) * quant:
            send = True
        elif type == 'buy' and unitBalance >= price * quant:
            send = True
        else:
            send = False
    return send

def sendOrder(base, unit, ticker, exp, strike, dude, user, type, quant, asset, price, assets):
    out = 'User ' + str(user) + ' wants eat ' + str(quant) + ' of ' + str(asset) + ' for ' + str(price) + '\n'
    with tickerLock(ticker):
        send = checkOrder(base, unit, ticker, exp, strike, dude, user, type, quant, asset, price, assets)
        if not send:
            return 'No Money!'
        if type == 'sell':
            oppType = 'buy'
        else:
            oppType = 'sell'
        bestPrice = getBestPrice(oppType, asset)
        # Sell ставит лимит, если ask выше лучшего bid; Buy — если bid ниже
        # лучшего ask. Иначе цена выгодна и заявка сводится со встречными.
        if type == 'sell':
            dir = price - bestPrice
        else:
            dir = bestPrice - price
        if dir > 0:
            out = out + sendLimit(ticker, exp, strike, dude, user, type, quant, asset, price)
            upBest(asset, type, getBestPrice(type, asset))
            return out
        while quant > 0:
            oppOrder, taken = matchOrder(ticker, exp, strike, dude, oppType, asset, price, quant, user)
            if oppOrder is None:
                break
            oppUser = oppOrder['user']
            oppPrice = oppOrder['price']
            out = out + 'Food from ' + str(oppUser) + ' User with ' + str(taken) + ' of ' + str(asset) + ' for ' + str(oppPrice) + '\n'
            out = out + makeDeal(ticker, exp, strike, dude, user, oppUser, type, taken, asset, oppPrice)
            quant -= taken
            upBest(asset, oppType, getBestPrice(oppType, asset))
        if quant > 0:
            out = out + 'Stay eat: ' + str(quant) + '\n'
            out = out + sendLimit(ticker, exp, strike, dude, user, type, quant, asset, price)
            upBest(asset, type, getBestPrice(type, asset))
    return out
