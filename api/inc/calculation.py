import math
from scipy.stats import norm


class Calculation():

    def d1(self, S, K, V, T):
        return (math.log(S / float(K)) + (V**2 / 2) * T) / (V * math.sqrt(T))

    def d2(self, S, K, V, T):
        return self.d1(S, K, V, T) - (V * math.sqrt(T))

    def theo(self, S, K, V, T, dT):
        # Black-Scholes undefined for non-positive inputs:
        #  - T <= 0: серия истекла (или экспирация наступила) — модель не применима;
        #  - V <= 0: нет волатильности — d1/d2 делят на ноль;
        #  - S <= 0 или K <= 0: нет цены/страйка — log/sqrt вне области определения.
        # В этих случаях возвращаем внутреннюю стоимость (intrinsic value):
        # для Call — max(S-K, 0), для Put — max(K-S, 0). Истёкший опцион «в деньгах»
        # чего-то стоит, «вне денег» — обесценивается, но храним минимум 1 (цена > 0
        # ожидается фронтом и хранилищем THEO).
        if not (S > 0) or not (K > 0) or not (V > 0) or not (T > 0):
            if dT == 'C':
                intrinsic = S - K
            else:
                intrinsic = K - S
            theo = int(round(max(intrinsic, 0)))
            return theo if theo > 0 else 1
        if dT == 'C':
            theo = int(round(S * norm.cdf(self.d1(S, K, V, T)) - K * norm.cdf(self.d2(S, K, V, T))))
        else:
            theo = int(round(K * norm.cdf(-self.d2(S, K, V, T)) - S * norm.cdf(-self.d1(S, K, V, T))))
        if theo > 0:
            return theo
        else:
            return 1
