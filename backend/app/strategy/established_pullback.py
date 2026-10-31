from app.strategy.base import AnalysisContext, Signal, Strategy, fmt


class EstablishedPullback(Strategy):
    name = "established_pullback"
    title = "Recuo em tendência (tokens estabelecidos)"
    categories = {"established"}
    entry = "EMA20 acima da EMA50, preço a até 0,5 ATR da EMA20 e RSI entre 40 e 55 voltando a subir"
    invalidation = "Fechamento abaixo da mínima dos últimos 6 candles ou EMA20 cruzando abaixo da EMA50"
    indicators = ["EMA20", "EMA50", "RSI(14)", "ATR(14)"]
    limitations = "Falha quando a tendência reverte rápido; depende de tendência estabelecida em 5 min"

    def evaluate(self, ctx: AnalysisContext) -> Signal | None:
        df = ctx.df
        x, p = df.iloc[-1], df.iloc[-2]
        if not (x.ema20 > x.ema50):
            return None
        if abs(x.close - x.ema20) > 0.5 * x.atr14:
            return None
        if not (40 <= x.rsi14 <= 55 and x.rsi14 > p.rsi14):
            return None
        stop = df["low"].iloc[-6:].min() - 0.25 * x.atr14
        return self.make_signal(
            float(x.close), float(stop),
            f"Comprar entre {fmt(x.close * 0.995)} e {fmt(x.close * 1.01)} enquanto o preço se mantiver acima de {fmt(stop)}",
            [
                f"EMA20 ({fmt(x.ema20)}) acima da EMA50 ({fmt(x.ema50)}): tendência de alta em 5 min",
                f"Preço {fmt(x.close)} a {abs(x.close - x.ema20) / x.atr14:.2f} ATR da EMA20 (recuo)",
                f"RSI subindo de {p.rsi14:.1f} para {x.rsi14:.1f}",
            ],
        )
