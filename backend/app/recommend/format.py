"""Formato obrigatório das recomendações (spec 4.2)."""
from datetime import datetime

from app.chains import CHAINS, Chain
from app.market.category import LABELS as CATEGORY_LABELS
from app.market.manipulation import ManipulationReport
from app.risk.manager import RiskDecision
from app.scoring.engine import LABELS as SCORE_LABELS, ScoreResult, pct_moves
from app.security.rules import SecurityVerdict
from app.strategy.base import HORIZON, AnalysisContext, Signal
from app.strategy.registry import BY_NAME

NO_TRADE_MESSAGE = "SEM OPERAÇÃO RECOMENDADA — aguardando condições melhores."
NO_CALIBRATION = "Sem estimativa confiável (ainda não há modelo calibrado com dados suficientes fora da amostra)"
FOMO_WARNING = ("Confirme no app da FOMO que o token e o contrato são os mesmos antes de executar. "
                "O preço e a taxa exibidos pela FOMO podem diferir do preço observado; nada aqui garante execução ou lucro.")
BAND_LABELS = {"alta_prioridade": "alta prioridade", "interessante": "interessante", "acompanhar": "acompanhar",
               "sem_recomendacao": "sem recomendação"}

FIELD_ORDER = [
    "TOKEN", "REDE", "CONTRATO", "TIPO", "DIREÇÃO", "PREÇO OBSERVADO", "VALOR SUGERIDO", "HORIZONTE", "ENTRADA",
    "ALVO 1", "ALVO 2", "INVALIDAÇÃO", "STOP DE REFERÊNCIA", "PONTUAÇÃO", "CONFIANÇA ESTATÍSTICA", "JUSTIFICATIVA",
    "RISCOS", "CENÁRIO NEGATIVO", "CUSTOS ESTIMADOS", "FONTES",
]


def usd_price(v: float) -> str:
    return f"US$ {v:.6g}" if v < 1 else f"US$ {v:,.4f}"


def _risks(ctx: AnalysisContext, signal: Signal, decision: RiskDecision, sec: SecurityVerdict, manip: ManipulationReport) -> list[str]:
    x = ctx.df.iloc[-1]
    out = []
    if x.atr14 == x.atr14 and x.close:
        out.append(f"Volatilidade: ATR de 5 min = {x.atr14 / x.close * 100:.2f}% do preço")
    c = decision.costs
    if c is not None:
        out.append(f"Custos de ida e volta estimados em {c.round_trip_pct:.2f}% (US$ {c.round_trip_usd:.2f}); "
                   f"taxa FOMO estimada {c.fomo_fee_pct:.2f}% por lado e slippage incerto")
    liq = ctx.snap.liquidity_usd
    if liq:
        out.append(f"Liquidez de US$ {liq:,.0f}: saídas rápidas podem ter preço pior que o observado")
    out += [m for m, _ in sec.penalties]
    out += [m for m, _ in manip.penalties]
    if ctx.category == "new":
        out.append("Token novo: risco alto de queda abrupta, retirada de liquidez e atividade de bots")
    out.append("A verificação automática de segurança não garante que o contrato é seguro")
    return out


def build_recommendation(
    ctx: AnalysisContext,
    signal: Signal,
    score: ScoreResult,
    decision: RiskDecision,
    security: SecurityVerdict,
    manip: ManipulationReport,
    sources: list[dict],
    analysis_at: datetime,
    calibration_text: str | None = None,
) -> dict:
    chain = Chain(ctx.token.get("chain", ctx.snap.chain))
    up, down = pct_moves(signal)
    strategy = BY_NAME.get(signal.strategy)
    loss_usd = decision.amount_usd * down / 100 + (decision.costs.round_trip_usd if decision.costs else 0)
    return {
        "token": ctx.token.get("symbol") or ctx.snap.symbol,
        "nome": ctx.token.get("name") or ctx.snap.name,
        "rede": CHAINS[chain].label,
        "contrato": ctx.token.get("address") or ctx.snap.token_address,
        "par": ctx.token.get("pair_address") or ctx.snap.pair_address,
        "tipo": CATEGORY_LABELS[ctx.category],
        "direcao": "Compra",
        "estrategia": signal.strategy,
        "estrategia_nome": strategy.title if strategy else signal.strategy,
        "preco_observado": signal.price,
        "valor_sugerido": decision.amount_usd,
        "horizonte": HORIZON,
        "entrada": signal.entry_condition,
        "entrada_faixa": [signal.entry_low, signal.entry_high],
        "alvo1": signal.target1,
        "alvo2": signal.target2,
        "alvo1_pct": up,
        "invalidacao": signal.invalidation,
        "stop": signal.stop,
        "stop_pct": -down,
        "pontuacao": round(score.total, 1),
        "faixa": BAND_LABELS[score.band],
        "componentes": score.components_dict(),
        "rr_liquido": round(score.net_rr if decision.net_rr is None else decision.net_rr, 2),
        "confianca_estatistica": calibration_text or NO_CALIBRATION,
        "justificativa": signal.rationale + [f"{SCORE_LABELS[c.name]}: {c.reason}" for c in score.components if c.value >= 7],
        "riscos": _risks(ctx, signal, decision, security, manip),
        "cenario_negativo": (
            f"Se a tese estiver errada, o preço pode recuar até o stop de referência ({-down:.2f}%), "
            f"uma perda estimada de US$ {loss_usd:.2f} com custos. Em movimentos bruscos ou com pouca liquidez "
            f"a saída pode acontecer bem abaixo do stop."
        ),
        "custos": decision.costs.as_dict() if decision.costs else None,
        "fontes": [{"fonte": s["fonte"], "horario": s["horario"].isoformat()} for s in sources],
        "aviso": FOMO_WARNING,
        "risco_decisao": decision.status,
        "risco_motivos": decision.reasons,
        "analysis_at": analysis_at.isoformat(),
    }


def render_text(rec: dict) -> str:
    c = rec.get("custos") or {}
    lines = [
        f"TOKEN: {rec['token']} ({rec['nome']})",
        f"REDE: {rec['rede']}",
        f"CONTRATO: {rec['contrato']}",
        f"TIPO: {rec['tipo']}.",
        f"DIREÇÃO: {rec['direcao']}.",
        f"PREÇO OBSERVADO: {usd_price(rec['preco_observado'])}.",
        f"VALOR SUGERIDO: US$ {rec['valor_sugerido']:.2f}.",
        f"HORIZONTE: {rec['horizonte']}.",
        f"ENTRADA: {rec['entrada']}.",
        f"ALVO 1: {usd_price(rec['alvo1'])} ({rec['alvo1_pct']:+.2f}%).",
        f"ALVO 2: {usd_price(rec['alvo2'])}.",
        f"INVALIDAÇÃO: {rec['invalidacao']}.",
        f"STOP DE REFERÊNCIA: {usd_price(rec['stop'])} ({rec['stop_pct']:.2f}%).",
        f"PONTUAÇÃO: {rec['pontuacao']:.0f}/100 ({rec['faixa']}; a pontuação não é probabilidade de lucro).",
        f"CONFIANÇA ESTATÍSTICA: {rec['confianca_estatistica']}.",
        "JUSTIFICATIVA:",
        *[f"- {j}" for j in rec["justificativa"]],
        "RISCOS:",
        *[f"- {r}" for r in rec["riscos"]],
        f"CENÁRIO NEGATIVO: {rec['cenario_negativo']}",
        (f"CUSTOS ESTIMADOS: {c.get('round_trip_pct', 0):.2f}% de ida e volta (US$ {c.get('round_trip_usd', 0):.2f}); "
         f"R:R líquido {rec['rr_liquido']:.2f}.") if c else "CUSTOS ESTIMADOS: indisponíveis.",
        "FONTES: " + "; ".join(f"{s['fonte']} às {s['horario'][11:19]} UTC" for s in rec["fontes"]),
        "",
        rec["aviso"],
    ]
    return "\n".join(lines)
