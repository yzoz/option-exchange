import time, random, requests
from inc.utils import pyMode
from inc.settings import memdb
import hashlib
import hmac
from inc.calculation import Calculation

calc = Calculation()

mode = pyMode()
mc = memdb()

if mode == 'dev':
    host = 'http://localhost:69'
else:
    host = 'https://yzoz.com:8080'

users ={"TSTTQ-7CYPW-OMJNY-D8IXR-I" : "cafe a foot step-fathers binate a wheezy turns stem killing a british", "T62HS-3HMQE-TXAJ4-PUHNQ-R" : "claus an ice speedboats pipeless a gular radars curtain scanty a foundation", "2X4O7-U5ZTO-BN4L8-WMPSL-C" : "chess an arm fibers marching a peeling requests germany stormproof a toothpaste", "OKSLK-DAE3Z-J7F4Q-9RA10-P" : "whip a kettledrum armies flawy a woodwind flares bronze sleepwalk a macaroni", "E4LEA-WNBJR-IGD8K-56IBV-5" :"team a study alligators nudist a hasty transports oak dozen a care"}

def trader():
    i = 1
    while i < 1000000:
        K = random.randrange(10000, 200001, 10000)
        V = random.randrange(0, 60, 1)
        dT01 = random.randrange(0, 2)
        if dT01 == 1:
            dT = 'C'
        else:
            dT = 'P'
        D01 = random.randrange(0, 2)
        if D01 == 1:
            D = 'buy'
        else:
            D = 'sell'
        """E01 = random.randrange(0, 2)
        if E01 == 1:
            E = '1495411199_'
        else:
            E = '1497734322_'
        T01 = random.randrange(0, 5)
        if T01 == 0:
            T = 'ETH_BTC_1495533525'
        elif T01 == 1:
            T = 'ETH_BTC_1495965525'
        elif T01 == 2:
            T = 'BR_BTC_1498211925'
        elif T01 == 3:
            T = 'BR_BTC_1500803925'
        elif T01 == 4:
            T = 'BR_BTC_1503482325'"""
        T = 'ETH_BTC_1519862400'
        U, S = random.choice(list(users.items()))
        Q = random.randrange(1, 25)
        #Q = 25
        #theo = int(calc.theo(45000, K, 0.7, 0.02, dT))
        print('+++'  + T + '_' + str(K) + '_' + dT + '+++')
        theo = mc.get('THEO_' + T + '_' + str(K) + '_' + dT)
        if theo < 10:
            theo = 10
        theoMin = int(round(theo - theo * 0.25))
        theoMax = int(round(theo + theo * 0.25))
        P = random.randrange(theoMin, theoMax, 1)
        #A = T + E + str(K) + '_' + dT
        #A = T + '_' + str(K) + '_' + dT
        A = T + '_' + str(K) + '_' + dT
        G = {
            'action': 'send',
            'type': D,
            'quant': Q,
            'asset': A,
            'price': P
        }
        W = ('send' + D + str(Q) + A + str(P)).encode()
        H = hmac.new(S.encode(), W, hashlib.sha3_512).hexdigest()
        print('----------------------------------------------------------------------')
        print(U, S, '|', D, Q, A, P)
        try:
            send = requests.post(host + '/order', json={
            'user': U,
            'hmac': H,
            'question': G
            })
        except requests.exceptions.RequestException as e:
            print('Error: {}'.format(e))
        else:
            print(send.text)
        print(str(i) + ' Done! ::: Sleep ' + str(V) + ' seconds')
        print('----------------------------------------------------------------------')
        time.sleep(V)
        i+=1
trader()
