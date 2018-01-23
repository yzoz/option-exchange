from bson.objectid import ObjectId
from .orders import alreadyOrders, getBestPrice, sendLimit, getLimit, removeOrder, editQuant
from .contracts import alreadyContracts, makeDeal
from .users import userBalances
from .mc import upBest

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
    send = checkOrder(base, unit, ticker, exp, strike, dude, user, type, quant, asset, price, assets)
    if send:
        if (type == 'sell'):
            oppType = 'buy'
        else:
            oppType = 'sell'
        bestPrice = getBestPrice(oppType, asset)
        #If I Sell, bestPrice (bid) must be < then my price, to place limit order, else I place market order
        #But if I want to buy, best ask must be > then my price, to send limit
        if (type == 'sell'):
            dir = price - bestPrice
        else:
            dir = bestPrice - price
        if (dir > 0):
            limit = sendLimit(ticker, exp, strike, dude, user, type, quant, asset, price)
            out = out + limit
            upBest(asset, type, getBestPrice(type, asset))
        else:
            machOrders = getLimit(oppType, asset, price)
            for oppOrder in machOrders:
    
                oppUser = oppOrder['user']
                oppQuant = oppOrder['quant']
                oppPrice = oppOrder['price']
                oppId = ObjectId(oppOrder['_id'])
                optTime = oppOrder['time']
    
                if (user == oppUser):
    
                    remove = removeOrder(ticker, exp, strike, dude, oppId, oppUser, oppType, oppQuant, asset, oppPrice)
    
                    out = out + remove
                    out = out + 'I\'m Stupid!\n'
                    
                    upBest(asset, oppType, getBestPrice(oppType, asset))
    
                    continue
    
                if (quant > oppQuant):
    
                    out = out + 'Food ' + 'from ' + str(oppUser) + ' User with ' + str(oppQuant) + ' of ' + str(asset) + ' for ' +  str(oppPrice) + ' in ' + str(optTime) + '\n'
    
                    make = makeDeal(ticker, exp, strike, dude, user, oppUser, type, oppQuant, asset, oppPrice)
                    out = out + make
    
                    remove = removeOrder(ticker, exp, strike, dude, oppId, oppUser, oppType, oppQuant, asset, oppPrice)
    
                    quant-=oppQuant
    
                    out = out + remove
                    out = out + 'Stay eat: ' + str(quant) + '\n'
                    
                    upBest(asset, oppType, getBestPrice(oppType, asset))
    
                elif (quant == oppQuant):
    
                    out = out + 'Best Food ' + 'from ' + str(oppUser) + 'User with ' + str(oppQuant) + ' of ' + str(asset) + ' for ' + str(oppPrice) + ' in ' + str(optTime) + '\n'
    
                    make = makeDeal(ticker, exp, strike, dude, user, oppUser, type, oppQuant, asset, oppPrice)
                    out = out + make
    
                    remove = removeOrder(ticker, exp, strike, dude, oppId, oppUser, oppType, oppQuant, asset, oppPrice)
    
                    quant = 0
    
                    out = out + remove
                    
                    upBest(asset, oppType, getBestPrice(oppType, asset))
    
                    break
    
                else:
    
                    out = out + 'Last food: ' + 'from ' + str(oppUser) + ' User with ' + str(oppQuant) + ' of ' + str(asset) + ' for ' + str(oppPrice) + ' in ' + str(optTime) + '\n'
    
                    make = makeDeal(ticker, exp, strike, dude, user, oppUser, type, quant, asset, oppPrice)
                    out = out + make
    
                    oppQuant-=quant
                    out = out + 'Leave over: ' + str(oppQuant) + '\n'
                    edit = editQuant(ticker, exp, strike, dude, oppId, oppUser, oppType, oppQuant, asset, oppPrice)
    
                    quant = 0
    
                    out = out + edit
    
                    break
    
            if (quant > 0):
    
                limit = sendLimit(ticker, exp, strike, dude, user, type, quant, asset, price)
    
                out = out + limit
                
                upBest(asset, type, getBestPrice(type, asset))
    else:
        out = 'No Money!'
    return out