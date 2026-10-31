"""Risk Manager independente (spec 4.1).

Recebe uma proposta já pontuada e o estado do livro; devolve APROVADA, REDUZIDA ou VETADA.
Não importa nada de estratégias nem de pontuação: nenhuma nota alta consegue contornar estas regras.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from app.chains import Chain
from app.costs import CostEstimate, estimate_costs


@dataclass(frozen=True)
class RiskLimits:
    capital_usd: float
    established_min_usd: float
    established_max_usd: float
    new_min_usd: float
    new_max_usd: float
    max_exposure_usd: float
    max_new_exposure_usd: float
    min_reserve_usd: float
    max_daily_loss_usd: float
    loss_streak_pause: int
    loss_streak_pause_hours: float
    dedupe_minutes: float
    max_impact_pct: float
    min_score: float
    min_net_rr: float
    min_target_cost_multiple: float
    cost_cfg: dict = field(default_factory=dict, hash=False, compare=False)

    @classmethod
    def from_settings(cls, d: dict) -> "RiskLimits":
        return cls(
            capital_usd=float(d["risk.capital_usd"]),
            established_min_usd=float(d["risk.established_min_usd"]),
            established_max_usd=float(d["risk.established_max_usd"]),
            new_min_usd=float(d["risk.new_min_usd"]),
            new_max_usd=float(d["risk.new_max_usd"]),
            max_exposure_usd=float(d["risk.max_exposure_usd"]),
            max_new_exposure_usd=float(d["risk.max_new_exposure_usd"]),
            min_reserve_usd=float(d["risk.min_reserve_usd"]),
            max_daily_loss_usd=float(d["risk.max_daily_loss_usd"]),
            loss_streak_pause=int(d["risk.loss_streak_pause"]),
            loss_streak_pause_hours=float(d["risk.loss_streak_pause_hours"]),
            dedupe_minutes=float(d["risk.dedupe_minutes"]),
            max_impact_pct=float(d["risk.max_impact_pct"]),
            min_score=float(d["rec.min_score"]),
            min_net_rr=float(d["rec.min_net_rr"]),
            min_target_cost_multiple=float(d["rec.min_target_cost_multiple"]),
            cost_cfg={k: v for k, v in d.items() if k.startswith("cost.")},
        )


@dataclass(frozen=True)
class OpenPosition:
    token_address: str
    category: str
    amount_usd: float


@dataclass
class BookState:
    capital_initial: float
    realized_pnl: float
    open_positions: list[OpenPosition]
    day_realized_pnl: float
    consecutive_losses: int
    last_loss_at: datetime | None
    recent_recs: list[tuple[str, str, datetime]]
    paused: bool = False

    @property
    def capital_current(self) -> float:
        return self.capital_initial + self.realized_pnl

    @property
    def exposure(self) -> float:
        return sum(p.amount_usd for p in self.open_positions)

    @property
    def new_exposure(self) -> float:
        return sum(p.amount_usd for p in self.open_positions if p.category == "new")

    @property
    def available(self) -> float:
        return self.capital_current - self.exposure


@dataclass
class TradeProposal:
    chain: Chain
    token_address: str
    strategy: str
    category: str
    score: float
    price: float
    stop: float
    target1: float
    liquidity_usd: float | None
    data_reliability: float
    blocks: list[str]


@dataclass
class RiskDecision:
    status: Literal["APROVADA", "REDUZIDA", "VETADA"]
    amount_usd: float
    reasons: list[str]
    costs: CostEstimate | None = None
    net_rr: float | None = None


def quality_factor(score: float) -> float:
    """80 → 0,6; 90 → 0,8; ≥ 95 → 1,0 (interpolação linear)."""
    if score >= 95:
        return 1.0
    if score >= 90:
        return 0.8 + (score - 90) / 5 * 0.2
    return max(0.0, 0.6 + (score - 80) / 10 * 0.2)


def _veto(reasons: list[str]) -> RiskDecision:
    return RiskDecision("VETADA", 0.0, reasons)


def evaluate(p: TradeProposal, book: BookState, limits: RiskLimits, now: datetime) -> RiskDecision:
    if p.blocks:
        return _veto(list(p.blocks))
    if book.paused:
        return _veto(["Monitoramento pausado: recomendações operacionais suspensas"])
    if p.score < limits.min_score:
        return _veto([f"Pontuação {p.score:.1f} abaixo do mínimo de {limits.min_score:.0f}"])
    if book.day_realized_pnl <= -limits.max_daily_loss_usd:
        return _veto([f"Limite de perda diária de US$ {limits.max_daily_loss_usd:.2f} atingido"])
    if (
        book.consecutive_losses >= limits.loss_streak_pause
        and book.last_loss_at is not None
        and now - book.last_loss_at < timedelta(hours=limits.loss_streak_pause_hours)
    ):
        return _veto([f"{book.consecutive_losses} perdas seguidas: pausa de {limits.loss_streak_pause_hours:g} h"])
    if any(pos.token_address == p.token_address for pos in book.open_positions):
        return _veto(["Já existe posição aberta neste ativo"])
    window = timedelta(minutes=limits.dedupe_minutes)
    if any(tok == p.token_address and strat == p.strategy and now - at < window for tok, strat, at in book.recent_recs):
        return _veto([f"Recomendação igual emitida nos últimos {limits.dedupe_minutes:g} min"])
    if not p.liquidity_usd:
        return _veto(["Liquidez desconhecida"])

    is_new = p.category == "new"
    cat_min = limits.new_min_usd if is_new else limits.established_min_usd
    cat_max = limits.new_max_usd if is_new else limits.established_max_usd
    loss_factor = max(0.5, 1 - 0.2 * book.consecutive_losses)  # nunca aumenta depois de perdas
    desired = cat_max * quality_factor(p.score) * min(1.0, max(0.0, p.data_reliability)) * loss_factor

    caps = {
        "impacto de preço": limits.max_impact_pct / 100 * p.liquidity_usd / 2,
        "exposição máxima simultânea": limits.max_exposure_usd - book.exposure,
        "reserva mínima de capital": book.capital_current - book.exposure - limits.min_reserve_usd,
    }
    if is_new:
        caps["exposição máxima em tokens novos"] = limits.max_new_exposure_usd - book.new_exposure
    amount = math.floor(min(desired, *caps.values()) * 100) / 100
    binding = min(caps, key=caps.get)
    if amount < cat_min:
        return _veto([f"Valor possível de US$ {max(amount, 0):.2f} abaixo do mínimo de US$ {cat_min:.2f} (limitado por {binding})"])

    costs = estimate_costs(p.chain, amount, p.liquidity_usd, limits.cost_cfg)
    up = (p.target1 / p.price - 1) * 100
    down = (1 - p.stop / p.price) * 100
    cost = costs.round_trip_pct
    reasons = []
    if down < limits.min_target_cost_multiple * cost:
        reasons.append(f"Stop a {down:.2f}% do preço, menor que {limits.min_target_cost_multiple:g}× o custo de ida e volta ({cost:.2f}%)")
    if up - cost < limits.min_target_cost_multiple * cost:
        reasons.append(f"Alvo 1 líquido de {up - cost:.2f}% abaixo de {limits.min_target_cost_multiple:g}× o custo de ida e volta ({cost:.2f}%)")
    rr = (up - cost) / (down + cost)
    if rr < limits.min_net_rr:
        reasons.append(f"R:R líquido de custos {rr:.2f} abaixo de {limits.min_net_rr:g}")
    if reasons:
        decision = _veto(reasons)
        decision.costs = costs
        decision.net_rr = rr
        return decision

    if amount < math.floor(desired * 100) / 100:
        return RiskDecision("REDUZIDA", amount, [f"Valor reduzido para US$ {amount:.2f} por {binding}"], costs, rr)
    return RiskDecision("APROVADA", amount, [f"Valor de US$ {amount:.2f} dentro de todos os limites"], costs, rr)
