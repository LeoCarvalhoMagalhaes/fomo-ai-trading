"""Pontuação 0–100 explicável (spec 3.7). A nota ordena oportunidades; não é probabilidade de lucro."""
import math
from dataclasses import asdict, dataclass

from app.config import SCORE_COMPONENTS
from app.costs import CostEstimate
from app.market.manipulation import ManipulationReport
from app.security.rules import SecurityVerdict
from app.strategy.base import AnalysisContext, Signal

LABELS = {
    "momentum": "Momentum",
    "volume": "Volume",
    "liquidez": "Liquidez",
    "estrutura_tecnica": "Estrutura técnica",
    "confirmacao_tendencia": "Confirmação de tendência",
    "qualidade_dados": "Qualidade dos dados",
    "seguranca_contrato": "Segurança do contrato",
    "risco_manipulacao": "Risco de manipulação",
    "risco_retorno": "Relação risco/retorno",
    "condicoes_mercado": "Condições de mercado",
}


@dataclass
class Component:
    name: str
    value: float
    weight: float
    reason: str


@dataclass
class ScoreResult:
    total: float
    components: list[Component]
    band: str
    net_rr: float
    net_target1_pct: float

    def components_dict(self) -> list[dict]:
        return [dict(asdict(c), label=LABELS[c.name]) for c in self.components]


def _clamp(v: float) -> float:
    return max(0.0, min(10.0, v))


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def band(total: float) -> str:
    if total >= 90:
        return "alta_prioridade"
    if total >= 80:
        return "interessante"
    if total >= 70:
        return "acompanhar"
    return "sem_recomendacao"


def pct_moves(signal: Signal) -> tuple[float, float]:
    return (signal.target1 / signal.price - 1) * 100, (1 - signal.stop / signal.price) * 100


def net_rr(signal: Signal, costs: CostEstimate) -> float:
    up, down = pct_moves(signal)
    return (up - costs.round_trip_pct) / (down + costs.round_trip_pct)


def _momentum(ctx: AnalysisContext) -> tuple[float, str]:
    x = ctx.df.iloc[-1]
    v, parts = 5.0, []
    if _ok(x.rsi14):
        if 50 <= x.rsi14 <= 70:
            v += 2
        elif x.rsi14 > 75:
            v -= 2
        parts.append(f"RSI {x.rsi14:.1f}")
    if _ok(x.macd_hist):
        v += 1.5 if x.macd_hist > 0 else -1.5
        parts.append(f"histograma MACD {x.macd_hist:.3g}")
    h1 = ctx.snap.price_change.get("h1")
    if h1 is not None:
        v += 1.5 if 0 < h1 <= 30 else (-1.5 if h1 < 0 else 0)
        parts.append(f"variação 1 h {h1:+.1f}%")
    return _clamp(v), ", ".join(parts) or "Sem dados de momentum"


def _volume(ctx: AnalysisContext) -> tuple[float, str]:
    x = ctx.df.iloc[-1]
    b, s = ctx.snap.buys.get("m5", 0), ctx.snap.sells.get("m5", 0)
    if not _ok(x.rel_vol):
        return 3.0, "Volume relativo indisponível"
    v = 5 + min(x.rel_vol - 1, 2) * 2 + (1 if b > s else -1)
    return _clamp(v), f"Volume {x.rel_vol:.1f}× a média; {b} compras e {s} vendas em 5 min"


def _liquidity(ctx: AnalysisContext, costs: CostEstimate) -> tuple[float, str]:
    liq = ctx.snap.liquidity_usd or 0
    v = 10 if liq >= 1_000_000 else 8 if liq >= 250_000 else 6 if liq >= 50_000 else 4 if liq >= 15_000 else 1
    return float(v), f"Liquidez de US$ {liq:,.0f}; impacto estimado {costs.impact_pct:.3f}% por lado"


def _structure(ctx: AnalysisContext) -> tuple[float, str]:
    x = ctx.df.iloc[-1]
    v, parts = 4.0, []
    if _ok(x.ema20) and x.close > x.ema20:
        v += 2
        parts.append("preço acima da EMA20")
    if _ok(x.bb_up) and x.close > x.bb_up:
        v -= 2
        parts.append("preço acima da banda superior (esticado)")
    elif _ok(x.bb_mid) and x.close >= x.bb_mid:
        v += 2
        parts.append("preço entre a média e a banda superior")
    if _ok(x.hh24) and x.close > x.hh24:
        v += 2
        parts.append("acima da máxima de 2 h")
    return _clamp(v), ", ".join(parts) or "Estrutura neutra"


def _trend(ctx: AnalysisContext) -> tuple[float, str]:
    x = ctx.df.iloc[-1]
    if _ok(x.ema50) and x.ema9 > x.ema21 > x.ema50:
        return 10.0, "EMA9 > EMA21 > EMA50"
    if _ok(x.ema50) and x.ema20 > x.ema50:
        return 7.0, "EMA20 acima da EMA50"
    if not _ok(x.ema50):
        return 3.0, "Histórico curto para EMA50"
    return 3.0, "Sem tendência de alta confirmada"


def score_signal(
    ctx: AnalysisContext,
    signal: Signal,
    costs: CostEstimate,
    security: SecurityVerdict,
    manip: ManipulationReport,
    market_regime: float,
    data_reliability: float,
    weights: dict[str, float],
) -> ScoreResult:
    rr = net_rr(signal, costs)
    up, _ = pct_moves(signal)
    sec_pen = sum(p for _, p in security.penalties)
    man_pen = sum(p for _, p in manip.penalties)
    values = {
        "momentum": _momentum(ctx),
        "volume": _volume(ctx),
        "liquidez": _liquidity(ctx, costs),
        "estrutura_tecnica": _structure(ctx),
        "confirmacao_tendencia": _trend(ctx),
        "qualidade_dados": (_clamp(data_reliability * 10), f"Confiabilidade dos dados {data_reliability:.2f}"),
        "seguranca_contrato": (
            _clamp(10 - sec_pen),
            "; ".join(m for m, _ in security.penalties) or f"Sem alertas nas fontes {', '.join(security.sources) or '—'}",
        ),
        "risco_manipulacao": (_clamp(10 - man_pen), "; ".join(m for m, _ in manip.penalties) or "Sem sinais de manipulação"),
        "risco_retorno": (_clamp(rr * 10 / 3), f"R:R líquido de custos {rr:.2f}; alvo 1 líquido {up - costs.round_trip_pct:+.2f}%"),
        "condicoes_mercado": (_clamp(market_regime * 10), f"{market_regime:.0%} da liquidez monitorada em alta na última hora"),
    }
    comps = [Component(name, round(values[name][0], 2), float(weights.get(name, 0.1)), values[name][1]) for name in SCORE_COMPONENTS]
    wsum = sum(c.weight for c in comps) or 1.0
    total = sum(c.value * c.weight for c in comps) / wsum * 10
    return ScoreResult(total=total, components=comps, band=band(total), net_rr=rr, net_target1_pct=up - costs.round_trip_pct)
