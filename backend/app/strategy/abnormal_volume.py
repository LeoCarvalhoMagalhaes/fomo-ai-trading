from app.strategy.base import AnalysisContext, Signal, Strategy, fmt


class AbnormalVolume(Strategy):
    name = "abnormal_volume"
    title = "Volume anormal comprador"
    categories = {"established", "intermediate"}
    entry = "Volume relativo ≥ 3 num candle de alta, compras maiores que vendas, liquidez estável e preço até 1 ATR acima da abertura do candle"
    invalidation = "Perda da mínima do candle de volume"
    indicators = ["Volume relativo", "Fluxo de compras e vendas", "Liquidez", "ATR(14)"]
    limitations = "Volume anormal pode ser uma venda grande disfarçada ou wash trading; exige filtros de manipulação"

    def evaluate(self, ctx: AnalysisContext) -> Signal | None:
        x = ctx.df.iloc[-1]
        if not (x.rel_vol == x.rel_vol and x.rel_vol >= 3 and x.close > x.open):
            return None
        if x.close > x.open + x.atr14:
            return None
        s = ctx.snap
        if s.buys.get("m5", 0) <= s.sells.get("m5", 0):
            return None
        liqs = [h.liquidity_usd for h in ctx.history if h.liquidity_usd]
        if liqs and s.liquidity_usd is not None and s.liquidity_usd < 0.95 * liqs[0]:
            return None
        return self.make_signal(
            float(x.close), float(x.low),
            f"Comprar entre {fmt(x.close * 0.995)} e {fmt(x.close * 1.01)} enquanto a mínima {fmt(x.low)} se mantiver",
            [
                f"Volume {x.rel_vol:.1f}× a média dos 20 candles anteriores em candle de alta",
                f"{s.buys.get('m5', 0)} compras contra {s.sells.get('m5', 0)} vendas em 5 min",
                f"Preço {fmt(x.close)} ainda a {(x.close - x.open) / x.atr14:.2f} ATR da abertura do candle",
            ],
        )
