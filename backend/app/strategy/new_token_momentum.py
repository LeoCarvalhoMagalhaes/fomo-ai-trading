from datetime import timedelta

from app.strategy.base import AnalysisContext, Signal, Strategy, fmt

MIN_AGE = timedelta(minutes=30)
MAX_AGE = timedelta(hours=72)
MAX_RUN_FROM_LAUNCH = 3.0
MIN_STOP_PCT = 0.12


class NewTokenMomentum(Strategy):
    name = "new_token_momentum"
    title = "Momentum de token novo (somente classe A)"
    categories = {"new"}
    min_candles = 12
    entry = ("Token novo classe A com 30 min a 72 h, razão compras/vendas em 5 min entre 1,2 e 3, transações de 5 min "
             "acima da média da última hora, alta desde o lançamento de no máximo 3× e liquidez sem queda")
    invalidation = "Queda de liquidez, razão compras/vendas abaixo de 1 ou perda do stop"
    indicators = ["Fluxo de compras e vendas", "Liquidez", "ATR(14)", "Preço de referência do lançamento"]
    limitations = "Tokens novos são extremamente voláteis; valor máximo de US$ 5; histórico curto"

    def evaluate(self, ctx: AnalysisContext) -> Signal | None:
        if ctx.classification != "A":
            return None
        s = ctx.snap
        if s.pair_created_at is None or not (MIN_AGE <= ctx.now - s.pair_created_at <= MAX_AGE):
            return None
        b5, s5 = s.buys.get("m5", 0), s.sells.get("m5", 0)
        if s5 == 0 or not (1.2 <= b5 / s5 <= 3):
            return None
        h1 = s.buys.get("h1", 0) + s.sells.get("h1", 0)
        if b5 + s5 < h1 / 12:
            return None
        df = ctx.df
        x = df.iloc[-1]
        # Referência conservadora: menor valor entre a abertura do primeiro candle e a menor mínima disponível
        reference = float(min(df["open"].iloc[0], df["low"].min()))
        if reference <= 0 or x.close / reference > MAX_RUN_FROM_LAUNCH:
            return None
        liqs = [h.liquidity_usd for h in ctx.history if h.liquidity_usd]
        if liqs and s.liquidity_usd is not None and s.liquidity_usd < 0.95 * liqs[0]:
            return None
        atr = x.atr14 if x.atr14 == x.atr14 else 0.0
        stop_pct = max(MIN_STOP_PCT, 1.5 * atr / x.close)
        stop = x.close * (1 - stop_pct)
        return self.make_signal(
            float(x.close), float(stop),
            f"Comprar no máximo US$ 5 entre {fmt(x.close * 0.995)} e {fmt(x.close * 1.01)} se o fluxo comprador se mantiver",
            [
                f"Classe A: segurança sem bloqueios e liquidez estável",
                f"{b5} compras contra {s5} vendas em 5 min (razão {b5 / s5:.2f})",
                f"Atividade de 5 min ({b5 + s5}) acima da média da última hora ({h1 / 12:.1f})",
                f"Preço {x.close / reference:.2f}× a referência de lançamento ({fmt(reference)})",
            ],
        )
