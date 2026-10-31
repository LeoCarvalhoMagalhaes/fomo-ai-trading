"""Regras de segurança de contrato (spec 3.1).

Passar nestas regras significa apenas que as fontes consultadas não mostraram sinais críticos;
não significa que o token é seguro. Entre fontes, vale o pior caso: um sinal de risco em qualquer
fonte conta.
"""
from dataclasses import dataclass, field

from app.domain import SecurityReport

EVM_CRITICAL = {
    "honeypot": "Honeypot detectado: a venda pode ser impossível",
    "cannot_sell_all": "Contrato impede vender todo o saldo",
    "cannot_buy": "Contrato impede compras",
    "selfdestruct": "Contrato pode se autodestruir",
    "hidden_owner": "Owner oculto no contrato",
    "can_take_back_ownership": "Owner pode retomar a propriedade depois de renunciar",
    "honeypot_same_creator": "Criador já lançou honeypots",
}
EVM_ADMIN = {
    "transfer_pausable": "pausar transferências",
    "blacklist": "colocar carteiras em lista negra",
    "owner_change_balance": "alterar saldos",
    "slippage_modifiable": "alterar taxas de compra/venda",
    "trading_cooldown": "impor intervalo entre negociações",
}
MAX_TRADE_TAX = 10.0
MAX_SOLANA_TRANSFER_FEE = 5.0
TOP10_BLOCK_NEW = 60.0
TOP10_PENALTY = 40.0


@dataclass
class SecurityVerdict:
    blocks: list[str] = field(default_factory=list)
    penalties: list[tuple[str, float]] = field(default_factory=list)
    coverage: float = 0.0
    sources: list[str] = field(default_factory=list)


def _merge_flag(reports: list[SecurityReport], key: str) -> bool | None:
    values = [r.flags.get(key) for r in reports if key in r.flags]
    if any(v is True for v in values):
        return True
    if any(v is False for v in values):
        return False
    return None


def _max_value(values) -> float | None:
    known = [v for v in values if v is not None]
    return max(known) if known else None


def evaluate_security(reports: list[SecurityReport], family: str, category: str) -> SecurityVerdict:
    v = SecurityVerdict(sources=sorted({r.source for r in reports}))
    is_new = category == "new"
    if not reports:
        if is_new:
            v.blocks.append("Sem dados de segurança para um token novo")
        else:
            v.penalties.append(("Sem dados de segurança do contrato", 4.0))
        return v

    known = 0
    total = 0

    def check(key: str) -> bool | None:
        nonlocal known, total
        total += 1
        value = _merge_flag(reports, key)
        if value is not None:
            known += 1
        return value

    honeypot = check("honeypot") if family == "evm" else _merge_flag(reports, "honeypot")
    if honeypot is True and family == "svm":
        v.blocks.append(EVM_CRITICAL["honeypot"])

    if family == "evm":
        if honeypot is True:
            v.blocks.append(EVM_CRITICAL["honeypot"])
        for key, msg in EVM_CRITICAL.items():
            if key == "honeypot":
                continue
            if (check(key) if key == "cannot_sell_all" else _merge_flag(reports, key)) is True:
                v.blocks.append(msg)
        buy = _max_value(r.taxes.get("buy") for r in reports)
        sell = _max_value(r.taxes.get("sell") for r in reports)
        total += 2
        known += (buy is not None) + (sell is not None)
        for label, tax in (("compra", buy), ("venda", sell)):
            if tax is None:
                continue
            if tax > MAX_TRADE_TAX:
                v.blocks.append(f"Taxa de {label} de {tax:.1f}% (acima de {MAX_TRADE_TAX:.0f}%)")
            elif tax >= 3:
                v.penalties.append((f"Taxa de {label} de {tax:.1f}%", 1.5))
        owner_values = [r.owner_active for r in reports if r.owner_active is not None]
        owner_active = True if True in owner_values else (False if owner_values else None)
        total += 1
        known += owner_active is not None
        admin = [msg for key, msg in EVM_ADMIN.items() if _merge_flag(reports, key) is True]
        if admin:
            joined = ", ".join(admin)
            if owner_active is True:
                v.blocks.append(f"Owner ativo pode {joined}")
            elif owner_active is None:
                v.penalties.append((f"Contrato permite {joined}; owner desconhecido", 2.0))
            else:
                v.penalties.append((f"Contrato permite {joined}, mas o owner foi renunciado", 0.5))
        elif owner_active is True:
            v.penalties.append(("Owner do contrato não renunciado", 1.0))
        if _merge_flag(reports, "open_source") is False:
            v.penalties.append(("Contrato não verificado (código fechado)", 2.0))
        if _merge_flag(reports, "proxy") is True:
            v.penalties.append(("Contrato proxy (lógica pode ser trocada)", 1.0))
    else:
        if check("freezable") is True:
            v.blocks.append("Autoridade de congelamento ativa: o emissor pode congelar seus tokens")
        if check("balance_mutable") is True:
            v.blocks.append("Autoridade capaz de alterar saldos ativa")
        if check("non_transferable") is True:
            v.blocks.append("Token não transferível")
        fee = _max_value(r.taxes.get("transfer") for r in reports)
        if fee is not None and fee > MAX_SOLANA_TRANSFER_FEE:
            v.blocks.append(f"Taxa de transferência de {fee:.1f}%")
        if _merge_flag(reports, "transfer_hook") is True:
            if is_new:
                v.blocks.append("Transfer hook ativo em token novo")
            else:
                v.penalties.append(("Transfer hook ativo", 1.5))

    mint = check("mintable")
    if mint is True:
        if is_new:
            v.blocks.append("Autoridade de mint ativa em token novo")
        else:
            v.penalties.append(("Autoridade de mint ativa", 2.0))

    top10 = _max_value(r.top10_pct for r in reports)
    total += 1
    if top10 is None:
        v.penalties.append(("Concentração de holders sem dado", 1.0))
    else:
        known += 1
        if top10 > TOP10_BLOCK_NEW and is_new:
            v.blocks.append(f"Os 10 maiores holders têm {top10:.1f}% da oferta")
        elif top10 > TOP10_PENALTY:
            v.penalties.append((f"Os 10 maiores holders têm {top10:.1f}% da oferta", 1.5))

    creator = _max_value(r.creator_pct for r in reports)
    if creator is not None and creator > 10:
        v.penalties.append((f"Criador detém {creator:.1f}%", 1.5))

    v.coverage = known / total if total else 0.0
    if v.coverage < 1 and not v.blocks:
        v.penalties.append((f"Cobertura de segurança incompleta ({v.coverage:.0%})", 1.0))
    return v
