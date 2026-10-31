from app.strategy.base import AnalysisContext, Signal, Strategy, fmt


class UptrendMomentum(Strategy):
    name = "uptrend_momentum"
    title = "Momentum em tendência de alta"
    categories = {"established", "intermediate"}
    entry = "EMA9 > EMA21 > EMA50, histograma do MACD positivo e crescente há 2 candles, RSI entre 55 e 70 e preço acima do VWAP"
    invalidation = "Fechamento abaixo da EMA21 ou histograma do MACD virando negativo"
    indicators = ["EMA9", "EMA21", "EMA50", "MACD(12,26,9)", "RSI(14)", "VWAP", "ATR(14)"]
    limitations = "Entra tarde em movimentos curtos; VWAP depende de volume por candle real"

    def evaluate(self, ctx: AnalysisContext) -> Signal | None:
        df = ctx.df
        x = df.iloc[-1]
        h = df["macd_hist"].iloc[-3:].tolist()
        if not (x.ema9 > x.ema21 > x.ema50):
            return None
        if not (h[-1] > 0 and h[-1] > h[-2] > h[-3]):
            return None
        if not (55 <= x.rsi14 <= 70):
            return None
        if not (x.vwap == x.vwap and x.close > x.vwap):  # VWAP ausente (NaN) bloqueia
            return None
        stop = x.close - 1.5 * x.atr14
        return self.make_signal(
            float(x.close), float(stop),
            f"Comprar entre {fmt(x.close * 0.995)} e {fmt(x.close * 1.01)} se o candle seguinte não fechar abaixo da EMA9 ({fmt(x.ema9)})",
            [
                f"Médias alinhadas: EMA9 {fmt(x.ema9)} > EMA21 {fmt(x.ema21)} > EMA50 {fmt(x.ema50)}",
                f"Histograma do MACD crescendo: {h[-3]:.3g} → {h[-2]:.3g} → {h[-1]:.3g}",
                f"RSI {x.rsi14:.1f} (força sem sobrecompra extrema)",
                f"Preço {fmt(x.close)} acima do VWAP {fmt(x.vwap)}",
            ],
        )
