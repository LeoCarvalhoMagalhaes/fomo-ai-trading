from app.strategy.abnormal_volume import AbnormalVolume
from app.strategy.base import AnalysisContext, Signal, Strategy
from app.strategy.breakout_retest import BreakoutRetest
from app.strategy.established_pullback import EstablishedPullback
from app.strategy.new_token_momentum import NewTokenMomentum
from app.strategy.reversal_confirmed import ReversalConfirmed
from app.strategy.uptrend_momentum import UptrendMomentum

ALL_STRATEGIES: list[Strategy] = [
    EstablishedPullback(), UptrendMomentum(), BreakoutRetest(), ReversalConfirmed(), NewTokenMomentum(), AbnormalVolume(),
]
BY_NAME = {s.name: s for s in ALL_STRATEGIES}


def run_strategies(ctx: AnalysisContext) -> list[Signal]:
    signals = []
    for strategy in ALL_STRATEGIES:
        if ctx.category not in strategy.categories or len(ctx.df) < strategy.min_candles:
            continue
        sig = strategy.evaluate(ctx)
        if sig is not None:
            signals.append(sig)
    return signals
