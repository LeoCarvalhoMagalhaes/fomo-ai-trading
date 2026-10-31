from app.strategy.base import AnalysisContext, Signal, Strategy, fmt

RETEST_TOLERANCE = 0.005


class BreakoutRetest(Strategy):
    name = "breakout_retest"
    title = "Rompimento confirmado com reteste"
    categories = {"established", "intermediate"}
    entry = "Fechamento acima da máxima dos 24 candles anteriores com volume relativo ≥ 2, seguido de reteste do nível sem fechar abaixo dele"
    invalidation = "Fechamento abaixo do nível rompido"
    indicators = ["Máxima de 24 candles (resistência)", "Volume relativo", "ATR(14)"]
    limitations = "Rompimentos falsos são comuns em ativos de baixa liquidez"

    def evaluate(self, ctx: AnalysisContext) -> Signal | None:
        df = ctx.df
        b, x = df.iloc[-2], df.iloc[-1]
        level = b.hh24
        if not (level == level and b.close > level and b.rel_vol >= 2):
            return None
        if not (x.low <= level * (1 + RETEST_TOLERANCE) and x.close >= level):
            return None
        stop = level - 0.5 * x.atr14
        return self.make_signal(
            float(x.close), float(stop),
            f"Comprar entre {fmt(x.close * 0.995)} e {fmt(x.close * 1.01)} com o preço acima de {fmt(level)}",
            [
                f"Rompimento de {fmt(level)} (máxima de 2 h) com volume {b.rel_vol:.1f}× a média",
                f"Reteste: mínima {fmt(x.low)} tocou o nível e o candle fechou acima ({fmt(x.close)})",
            ],
        )
