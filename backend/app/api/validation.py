"""Validação das alterações de configuração antes de gravar (nada inválido chega ao Risk Manager)."""
from app.config import DEFAULT_RUNTIME, SCORE_COMPONENTS


class SettingsError(ValueError):
    pass


def validate_changes(current: dict, changes: dict) -> dict:
    merged = dict(current)
    for key, value in changes.items():
        if key not in DEFAULT_RUNTIME:
            raise SettingsError(f"Configuração desconhecida: {key}")
        default = DEFAULT_RUNTIME[key]
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise SettingsError(f"{key} precisa ser verdadeiro ou falso")
        elif isinstance(default, (int, float)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SettingsError(f"{key} precisa ser numérico")
            if value < 0:
                raise SettingsError(f"{key} não pode ser negativo")
        elif isinstance(default, str) and not isinstance(value, str):
            raise SettingsError(f"{key} precisa ser texto")
        merged[key] = value

    def g(k):
        return merged[k]

    if g("data.retention_snapshots_hours") < 2 or g("data.retention_candles_days") < 1 or g("data.retention_logs_days") < 1:
        raise SettingsError("A limpeza precisa manter pelo menos 2 h de preços e 1 dia de candles e de registros")
    if g("mode") not in ("SIM", "REAL"):
        raise SettingsError("Modo precisa ser SIM ou REAL")
    if g("risk.min_reserve_usd") >= g("risk.capital_usd"):
        raise SettingsError("A reserva mínima precisa ser menor que o capital")
    if g("risk.established_min_usd") > g("risk.established_max_usd"):
        raise SettingsError("Valor mínimo de token estabelecido maior que o máximo")
    if g("risk.new_min_usd") > g("risk.new_max_usd"):
        raise SettingsError("Valor mínimo de token novo maior que o máximo")
    if g("risk.max_new_exposure_usd") > g("risk.max_exposure_usd"):
        raise SettingsError("Exposição em tokens novos maior que a exposição total")
    if not 0 <= g("rec.min_score") <= 100:
        raise SettingsError("Pontuação mínima precisa estar entre 0 e 100")
    if sum(g(f"score.weight.{k}") for k in SCORE_COMPONENTS) <= 0:
        raise SettingsError("A soma dos pesos da pontuação precisa ser positiva")
    if g("data.max_price_age_s") < 30:
        raise SettingsError("Idade máxima do preço precisa ser de pelo menos 30 s")
    return {k: v for k, v in changes.items()}
