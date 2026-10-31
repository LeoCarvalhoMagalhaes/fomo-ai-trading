"""Relatórios de validação: backtest sobre candles gravados e eficácia dos filtros sobre as avaliações registradas."""
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.backtest.calibration import calibrate
from app.backtest.engine import simulate, split_report
from app.backtest.engine import time_split
from app.chains import Chain
from app.db.models import Candle as CandleRow, Evaluation, Token
from app.db.session import Database
from app.domain import Candle
from app.strategy.indicators import add_indicators, candles_to_frame
from app.strategy.registry import ALL_STRATEGIES

MIN_CANDLES = 150


def backtest_from_db(db: Database, cfg: dict, liquidity_of: dict[int, float]) -> dict:
    with db.session() as s:
        counts = s.execute(
            select(CandleRow.token_id, func.count()).where(CandleRow.tf == "5m").group_by(CandleRow.token_id)
        ).all()
        eligible = [tid for tid, n in counts if n >= MIN_CANDLES and liquidity_of.get(tid)]
        tokens = {t.id: t for t in s.scalars(select(Token).where(Token.id.in_(eligible)))}
        frames = {}
        for tid in eligible:
            rows = s.scalars(select(CandleRow).where(CandleRow.token_id == tid, CandleRow.tf == "5m").order_by(CandleRow.ts)).all()
            frames[str(tid)] = add_indicators(candles_to_frame(
                [Candle(ts=r.ts, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume) for r in rows]))
    if not frames:
        return {"status": "sem_dados", "mensagem": f"Nenhum ativo com pelo menos {MIN_CANDLES} candles de 5 min gravados ainda."}
    trades = simulate(
        frames, ALL_STRATEGIES, cfg,
        {k: Chain(tokens[int(k)].chain) for k in frames},
        {k: tokens[int(k)].category or "intermediate" for k in frames},
        {k: liquidity_of[int(k)] for k in frames},
    )
    return {
        "status": "ok",
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "ativos": len(frames),
        "operacoes": len(trades),
        "limitacoes": [
            "Somente estratégias baseadas em candles (sem fluxo de compras/vendas).",
            "Regras fixas, sem otimização; a divisão 60/20/20 verifica estabilidade fora da amostra.",
            "Alvo e stop no mesmo candle contam como stop.",
            "Custos usam a liquidez atual de cada ativo.",
        ],
        "resultado": split_report(trades),
    }


def filter_report(db: Database) -> dict:
    """O que aconteceu 60 min depois das avaliações recomendadas e rejeitadas (eficácia dos filtros)."""
    with db.session() as s:
        rows = s.execute(
            select(Evaluation.decision, Evaluation.outcome_hit, Evaluation.outcome_return_pct, Evaluation.score, Evaluation.created_at)
            .where(Evaluation.outcome_hit.is_not(None), Evaluation.outcome_hit != "sem_dados")
            .order_by(Evaluation.created_at)
        ).all()
    out = {}
    for decision in ("RECOMENDADA", "REJEITADA"):
        sel = [r for r in rows if r.decision == decision]
        rets = [r.outcome_return_pct for r in sel if r.outcome_return_pct is not None]
        out[decision.lower()] = {
            "n": len(sel),
            "retorno_medio_60min_pct": sum(rets) / len(rets) if rets else None,
            "alvo1": sum(1 for r in sel if r.outcome_hit == "alvo1"),
            "stop": sum(1 for r in sel if r.outcome_hit == "stop"),
            "tempo": sum(1 for r in sel if r.outcome_hit == "tempo"),
        }
    scored = [(r.score, 1 if r.outcome_hit == "alvo1" else 0) for r in rows if r.score is not None and r.outcome_hit in ("alvo1", "stop")]
    train, _, test = time_split(scored, (0.8, 0.0, 0.2))
    cal = calibrate([s for s, _ in train], [o for _, o in train]) if len(test) >= 200 else None
    out["calibracao"] = (
        {"status": "ok", "amostras_treino": len(train), "amostras_teste": len(test),
         "brier_teste": sum((cal.predict(s) - o) ** 2 for s, o in test) / len(test)}
        if cal else {"status": "insuficiente", "mensagem": f"Sem estimativa confiável: {len(test)} de 200 resultados necessários no conjunto de teste."}
    )
    return out


def save_report(report: dict, data_dir: Path) -> Path:
    out = data_dir / "backtests"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "ultimo.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
