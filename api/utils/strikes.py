first = 10000
last = 200000
step = 10000

strikes = ''

while last >= first:
    strikes += str(last) + ', '
    last -= step

print(strikes)