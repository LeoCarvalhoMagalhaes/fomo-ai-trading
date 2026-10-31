from app.strategy.base import AnalysisContext, Signal, Strategy, fmt
from app.strategy.indicators import rsi_bullish_divergence


class ReversalConfirmed(Strategy):
    name = "reversal_confirmed"
    title = "Reversão com confirmação"
    categories = {"established"}
    entry = "Divergência de alta no RSI nos últimos 12 candles e fechamento acima da banda inferior de Bollinger e da EMA9"
    invalidation = "Nova mínima abaixo da mínima da divergência"
    indicators = ["RSI(14) e divergência", "Bandas de Bollinger(20,2)", "EMA9", "ATR(14)"]
    limitations = "Em tendências de baixa fortes a divergência pode se repetir várias vezes antes de reverter"

    def evaluate(self, ctx: AnalysisContext) -> Signal | None:
        df = ctx.df
        pos = rsi_bullish_divergence(df, lookback=12)
        if pos is None:
            return None
        x = df.iloc[-1]
        if not (x.close > x.bb_low and x.close > x.ema9):
            return None
        div_low = float(df["low"].iloc[pos])
        stop = div_low - 0.25 * x.atr14
        return self.make_signal(
            float(x.close), float(stop),
            f"Comprar entre {fmt(x.close * 0.995)} e {fmt(x.close * 1.01)} enquanto a mínima {fmt(div_low)} não for perdida",
            [
                f"Divergência de alta: preço fez mínima menor ({fmt(div_low)}) com RSI mais alto ({df['rsi14'].iloc[pos]:.1f})",
                f"Fechamento {fmt(x.close)} acima da banda inferior ({fmt(x.bb_low)}) e da EMA9 ({fmt(x.ema9)})",
            ],
        )
