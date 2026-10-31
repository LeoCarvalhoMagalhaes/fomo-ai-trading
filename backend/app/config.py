"""Configuração de inicialização (.env) e valores padrão das configurações editáveis em tempo de execução."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.chains import CHAINS

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="FOMOAI_", extra="ignore")

    data_dir: Path = ROOT / "data"
    db_url: str | None = None
    host: str = "127.0.0.1"
    port: int = 8765
    # API pública: limite dinâmico (~5–15/min, HTTP 429 observado a 10/min em 31/10/2026). Com chave Demo grátis: suba para 25.
    gecko_rpm: int = 6
    dex_rpm: int = 60
    goplus_rpm: int = 20
    coingecko_demo_key: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    def database_url(self) -> str:
        if self.db_url:
            return self.db_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(self.data_dir / 'fomo_ai.db').as_posix()}"


SCORE_COMPONENTS = (
    "momentum", "volume", "liquidez", "estrutura_tecnica", "confirmacao_tendencia",
    "qualidade_dados", "seguranca_contrato", "risco_manipulacao", "risco_retorno", "condicoes_mercado",
)

# Chaves planas; todas editáveis pela página de configurações, com auditoria.
DEFAULT_RUNTIME: dict[str, object] = {
    "mode": "SIM",
    "monitoring.paused": False,
    # Risco (spec 4.1)
    "risk.capital_usd": 50,
    "risk.established_min_usd": 5,
    "risk.established_max_usd": 10,
    "risk.new_max_usd": 5,
    "risk.max_exposure_usd": 15,
    "risk.max_new_exposure_usd": 5,
    "risk.min_reserve_usd": 30,
    "risk.max_daily_loss_usd": 2.5,
    "risk.loss_streak_pause": 3,
    "risk.loss_streak_pause_hours": 2,
    "risk.dedupe_minutes": 60,
    "risk.max_impact_pct": 0.5,
    "risk.new_min_usd": 2,
    # Recomendações (spec 3.7 e 4.2)
    "rec.min_score": 80,
    "rec.min_net_rr": 1.5,
    "rec.min_target_cost_multiple": 2,
    "rec.ttl_minutes": 10,
    "rec.max_entry_run_pct": 1.5,
    "rec.horizon_minutes": 60,
    # Dados
    "data.max_price_age_s": 120,
    "data.tier2_max_assets": 20,
    # Filtros de mercado (spec 3.2)
    "market.min_liquidity_established": 50_000,
    "market.min_liquidity_new": 15_000,
    # Custos (spec 3.6)
    # FOMO: 0,5% por operação com mínimo por ordem pequena (fontes não oficiais, out/2026). Confira no app.
    "cost.fomo_fee_pct": 0.5,
    "cost.fomo_min_fee_usd": 0.5,
    "cost.pool_fee_pct": 0.3,
    "cost.base_slippage_pct": 0.5,
    **{f"cost.gas_usd.{chain.value}": info.default_gas_usd for chain, info in CHAINS.items()},
    # Pontuação: pesos iguais (10% cada)
    **{f"score.weight.{name}": 0.1 for name in SCORE_COMPONENTS},
    # Notificações
    "notify.windows_toast": True,
    "notify.dedupe_minutes": 30,
}
