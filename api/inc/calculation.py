import math
from scipy.stats import norm

class Calculation():

    def d1(self, S, K, V, T):
        return (math.log(S / float(K)) + (V**2 / 2) * T) / (V * math.sqrt(T))

    def d2(self, S, K, V, T):
        return self.d1(S, K, V, T) - (V * math.sqrt(T))

    def theo(self, S, K, V, T, dT):
        if dT == 'C':
            theo = int(round(S * norm.cdf(self.d1(S, K, V, T)) - K * norm.cdf(self.d2(S, K, V, T))))
        else:
            theo = int(round(K * norm.cdf(-self.d2(S, K, V, T)) - S * norm.cdf(-self.d1(S, K, V, T))))
        if theo > 0:
            return theo
        else:
            return 1