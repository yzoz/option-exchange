#!/usr/local/bin/python3.6

import schedule, time
from inc.mc import setHV, setCurrent, setTheo

def calcTheo():
    setCurrent()
    setTheo()

#calcTheo()
#getHV()

schedule.every(1).minutes.do(calcTheo)
schedule.every(15).minutes.do(setHV)
#schedule.every(2).hour.do(getHV)

while True:
    schedule.run_pending()
    time.sleep(1)