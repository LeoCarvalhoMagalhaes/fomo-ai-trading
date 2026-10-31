# FOMO AI Trading Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App local consultivo que coleta dados públicos de DEX em 6 redes, filtra riscos, pontua oportunidades, aplica um Risk Manager independente e registra recomendações, simulações e operações manuais.

**Architecture:** Um processo FastAPI com tarefas asyncio (coleta, ciclo de análise, monitoramento), SQLite via SQLAlchemy, módulos de domínio puros (indicadores, segurança, estratégias, pontuação, risco) testados sem rede, e uma SPA React servida pelo backend.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, httpx, pandas, numpy, pytest, pytest-asyncio, respx, winotify; React 18, TypeScript, Vite, Tailwind 3, lightweight-charts 4, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-31-fomo-ai-trading-design.md`

## Global Constraints

- Nunca acessar fomo.family; nunca armazenar credenciais da FOMO; nunca executar ordens.
- Redes: solana, base, bsc, ethereum, monad, robinhood (IDs por provedor na seção 2 da spec).
- Orçamentos: GeckoTerminal 10/min, DexScreener 60/min, GoPlus 20/min.
- Limites padrão: capital 50; estabelecido 5–10; novo ≤ 5; exposição ≤ 15; novos ≤ 5; reserva ≥ 30; perda diária ≤ 2,50; 3 perdas seguidas → pausa de 2 h.
- Recomendação exige nota ≥ 80, R:R líquido ≥ 1,5, alvo 1 líquido ≥ 2× custo de ida e volta, zero vetos.
- Preço com mais de 120 s = obsoleto → bloqueia.
- Nenhum teste acessa a rede, exceto os marcados `-m live`.
- Textos da interface e das recomendações em pt-BR.
- Windows: caminhos com pathlib; scripts `.bat`; sem dependências que exijam compilador C.

## Review Focus

1. Campo ausente ou `null` numa resposta de provedor (ex.: `liquidity` null na DexScreener, `market_cap_usd` null no GeckoTerminal) → o snapshot é gravado com o campo ausente, a confiança cai, nada quebra. Teste: `test_parse_tokens_handles_null_liquidity` (Task 4), `test_parse_pools_null_fields` (Task 5).
2. Candles em ordem decrescente e com buracos (o GeckoTerminal devolve o mais recente primeiro) → indicadores recebem série crescente. Teste: `test_parse_ohlcv_sorted_ascending` (Task 5).
3. Token sem dado de segurança numa rede pouco coberta → token novo vetado, estabelecido penalizado. Teste: `test_new_token_without_security_is_blocked` (Task 8).
4. Usuário informa execução de uma recomendação já expirada ou valor acima do limite → registra a operação (é fato), mas marca alerta de limite excedido. Teste: `test_manual_trade_over_limit_is_flagged` (Task 14).
5. Dois ciclos simultâneos (varredura horária + disparo por execução) → nunca duas recomendações ativas iguais. Teste: `test_cycle_lock_prevents_duplicates` (Task 16).

---

### Task 1: Esqueleto do backend, configuração e redes

**Files:**
- Create: `backend/requirements.txt`, `backend/pyproject.toml` (config pytest), `backend/app/__init__.py`, `backend/app/chains.py`, `backend/app/config.py`
- Test: `backend/tests/test_chains_config.py`

**Interfaces:**
- Produces: `Chain` (StrEnum: solana, base, bsc, ethereum, monad, robinhood); `CHAINS: dict[Chain, ChainInfo]` com `gecko_id`, `dex_id`, `goplus_id`, `family: Literal["svm","evm"]`, `default_gas_usd`; `Settings` (pydantic-settings: `data_dir: Path`, `db_url`, `gecko_rpm=10`, `dex_rpm=60`, `goplus_rpm=20`, `coingecko_demo_key: str|None`); `DEFAULT_RUNTIME: dict` com todos os limites de risco, custos e pesos de pontuação (chaves planas como `risk.max_exposure_usd`).

- [ ] Step 1: teste `test_chain_ids_match_spec` (ethereum → gecko `eth`, dex `ethereum`, goplus `1`; robinhood → `robinhood`, `robinhood`, `4663`; monad goplus `143`) e `test_default_risk_limits` (valores das Global Constraints).
- [ ] Step 2: criar venv `backend/.venv`, instalar requirements, rodar pytest → FAIL (import).
- [ ] Step 3: implementar `chains.py` e `config.py`.
- [ ] Step 4: pytest → PASS. Commit.

### Task 2: Modelos de domínio e banco

**Files:** Create `backend/app/domain.py`, `backend/app/db/__init__.py`, `backend/app/db/models.py`, `backend/app/db/session.py`, `backend/app/db/runtime_settings.py`. Test `backend/tests/test_db.py`.

**Interfaces:**
- Produces (domain, Pydantic): `PairSnapshot(chain, token_address, pair_address, symbol, name, price_usd: float|None, liquidity_usd: float|None, volume: dict[str,float], buys: dict[str,int], sells: dict[str,int], buyers: dict[str,int]|None, sellers: dict[str,int]|None, price_change: dict[str,float], fdv_usd, market_cap_usd, pair_created_at: datetime|None, observed_at: datetime, source: str, reliability: float)`; `Candle(ts: datetime, open, high, low, close, volume: float)`; `SecurityReport(chain, token_address, source, observed_at, flags: dict[str, bool|None], taxes: dict[str, float|None], owner_active: bool|None, top10_pct: float|None, creator_pct: float|None, holder_count: int|None, raw: dict)`.
- Produces (DB, SQLAlchemy): tabelas `tokens`, `snapshots`, `candles` (único token_id+tf+ts), `security_reports`, `evaluations`, `recommendations`, `trades`, `events`, `notifications`, `settings`, `audit_log`.
- `make_engine(url) -> Engine` (WAL ligado), `session_scope()`; `RuntimeSettings.get(key)`, `.set(key, value, actor) -> None` grava auditoria com valor antigo/novo, `.all() -> dict`.

- [ ] Steps: teste `test_settings_change_is_audited` e `test_candle_unique_constraint` (inserir duplicado → upsert sem erro via `upsert_candles`) → FAIL → implementar → PASS → commit.

### Task 3: Limitador de taxa e base de provedores

**Files:** Create `backend/app/providers/__init__.py`, `backend/app/providers/base.py`. Test `backend/tests/test_rate_limit.py`.

**Interfaces:** `RateLimiter(rpm: int)` com `async acquire()`; `ProviderError(provider, status, message)`; `ProviderHealth` (ok, last_success, last_error, consecutive_failures, backoff_until) com `record_success()`, `record_failure(err)` (backoff 2 s × 2^n até 300 s), `available(now) -> bool`; `fetch_json(client, provider, url, params, limiter, health) -> Any` (trata 429 como falha com backoff, levanta `ProviderError`).

- [ ] Steps: testes `test_limiter_spaces_calls` (rpm=600 → 3 chamadas ≥ 0,2 s), `test_backoff_caps_at_300s`, `test_fetch_json_429_records_failure` (respx) → FAIL → implementar → PASS → commit.

### Task 4: Adaptador DexScreener

**Files:** Create `backend/app/providers/dexscreener.py`. Test `backend/tests/test_dexscreener.py` (fixture `dexscreener_tokens_bonk.json`).

**Interfaces:** `parse_tokens(data: list, observed_at) -> list[PairSnapshot]`; `best_pair_per_token(snaps) -> dict[str, PairSnapshot]` (maior liquidez); classe `DexScreener(client, limiter, health)` com `async tokens(chain: Chain, addresses: list[str]) -> list[PairSnapshot]` (lotes de 30).

- [ ] Steps: testes `test_parse_tokens_bonk` (preço float, liquidez 295550.21, buys h1 179, pair_created_at 2022-12-25), `test_parse_tokens_handles_null_liquidity`, `test_tokens_batches_by_30` (respx, 31 endereços → 2 chamadas) → implementar → commit.

### Task 5: Adaptador GeckoTerminal

**Files:** Create `backend/app/providers/geckoterminal.py`. Test `backend/tests/test_geckoterminal.py`.

**Interfaces:** `parse_pools(data, chain, observed_at) -> list[PairSnapshot]` (inclui buyers/sellers); `parse_ohlcv(data) -> list[Candle]` crescente; `parse_token_info(data, chain, observed_at) -> SecurityReport` (mint_authority/freeze_authority "yes"/"no" → bool, is_honeypot "unknown" → None, top10_pct de holders); classe `GeckoTerminal` com `new_pools(chain)`, `trending_pools(chain, duration="1h")`, `ohlcv(chain, pool, aggregate=5, limit=100)`, `token_info(chain, address)`; header da chave Demo quando configurada.

- [ ] Steps: testes `test_parse_pools_new_solana` (buyers m5 = 4 no primeiro pool), `test_parse_pools_null_fields`, `test_parse_ohlcv_sorted_ascending`, `test_parse_token_info_bonk` (freeze False, mint False, honeypot None, top10 38.8358) → implementar → commit.

### Task 6: Adaptador GoPlus

**Files:** Create `backend/app/providers/goplus.py`. Test `backend/tests/test_goplus.py`.

**Interfaces:** `parse_evm(data, chain, address, observed_at) -> SecurityReport|None`; `parse_solana(...) -> SecurityReport|None`; `GoPlus.token_security(chain, address) -> SecurityReport|None`. Flags normalizados: `honeypot, cannot_sell_all, cannot_buy, selfdestruct, hidden_owner, can_take_back_ownership, honeypot_same_creator, transfer_pausable, blacklist, owner_change_balance, slippage_modifiable, trading_cooldown, mintable, freezable, balance_mutable, non_transferable, transfer_hook, open_source, proxy`. `owner_active` = owner_address não vazio e não em {0x0…0, 0x…dead}.

- [ ] Steps: testes `test_parse_evm_pepe` (honeypot False, transfer_pausable True, owner_active False, sell_tax 0.0), `test_parse_solana_bonk` (freezable False, mintable False, holder_count 1020153), `test_parse_missing_result_returns_none` → implementar → commit.

### Task 7: Indicadores

**Files:** Create `backend/app/strategy/__init__.py`, `backend/app/strategy/indicators.py`. Test `backend/tests/test_indicators.py`.

**Interfaces:** `candles_to_frame(candles) -> DataFrame` (índice ts, colunas open..volume); `add_indicators(df) -> DataFrame` acrescenta `ema9, ema20, ema21, ema50, sma20, rsi14, macd, macd_signal, macd_hist, bb_mid, bb_up, bb_low, atr14, rel_vol, hh24, ll24, vwap`; `rsi_bullish_divergence(df, lookback=12) -> int|None` (posição da mínima mais recente da divergência). RSI e ATR com suavização de Wilder; VWAP reinicia por dia UTC.

- [ ] Steps: testes com séries conhecidas: `test_rsi_all_up_is_100`, `test_rsi_wilder_reference` (série clássica de 15 fechamentos de Wilder; RSI ≈ 70,46 com tolerância 0,5), `test_ema_constant_series`, `test_atr_constant_range`, `test_vwap_resets_daily`, `test_divergence_detected` → implementar → commit.

### Task 8: Segurança, categorias e classificação de novos tokens

**Files:** Create `backend/app/security/__init__.py`, `backend/app/security/rules.py`, `backend/app/newtokens/__init__.py`, `backend/app/newtokens/classify.py`, `backend/app/market/__init__.py`, `backend/app/market/category.py`. Tests `backend/tests/test_security_rules.py`, `backend/tests/test_newtokens.py`.

**Interfaces:**
- `categorize(pair_created_at, liquidity_usd, now) -> Literal["established","intermediate","new"]` (spec 3.3).
- `SecurityVerdict(blocks: list[str], penalties: list[tuple[str, float]], coverage: float, sources: list[str])`; `evaluate_security(reports: list[SecurityReport], family, category) -> SecurityVerdict` aplicando spec 3.1 (mensagens pt-BR).
- `classify_new_token(snap, history: list[PairSnapshot], verdict, manip) -> tuple[Literal["A","B","C"], list[str]]`.

- [ ] Steps: testes `test_pepe_not_blocked_owner_renounced`, `test_honeypot_blocks`, `test_sell_tax_over_10_blocks`, `test_owner_active_pausable_blocks`, `test_solana_freeze_blocks`, `test_mint_blocks_new_penalizes_established`, `test_new_token_without_security_is_blocked`, `test_top10_over_60_blocks_new`, `test_classify_A_requires_two_sources_or_full_coverage`, `test_classify_C_on_any_block`, `test_classify_B_when_too_young` (idade < 30 min) → implementar → commit.

### Task 9: Detectores de manipulação e confiabilidade

**Files:** Create `backend/app/market/manipulation.py`, `backend/app/market/reliability.py`. Test `backend/tests/test_manipulation.py`.

**Interfaces:** `ManipulationReport(blocks, penalties, flags: dict[str, bool])`; `detect_manipulation(snap, history, category) -> ManipulationReport` (spec 3.2; queda de liquidez > 30% em 15 min usa history); `reliability(snap, other_price: float|None, now) -> float`; `is_stale(snap, now, max_age_s=120) -> bool`.

- [ ] Steps: testes `test_pump_over_300_blocks`, `test_wash_ratio_80x_blocks`, `test_low_liquidity_blocks_established_under_50k`, `test_liquidity_drop_30pct_blocks`, `test_buy_sell_ratio_over_6_flags`, `test_reliability_divergence_penalty` (2,5% → ×0,6), `test_stale_after_120s` → implementar → commit.

### Task 10: Custos

**Files:** Create `backend/app/costs.py`. Test `backend/tests/test_costs.py`.

**Interfaces:** `CostEstimate(fomo_fee_pct, pool_fee_pct, impact_pct, slippage_pct, gas_usd, round_trip_pct, round_trip_usd)`; `estimate_costs(chain, amount_usd, liquidity_usd, cfg: dict) -> CostEstimate`. Por lado = fomo + pool + impacto + slippage; ida e volta = 2× por lado + 2× gás / valor.

- [ ] Steps: testes `test_solana_10usd_100k_liquidity` (impacto 0,02%; ida e volta ≈ 3,64% + gás 0,2% ≈ 3,84%), `test_ethereum_5usd_gas_dominates` (≥ 60%), `test_none_liquidity_raises_or_inf` (liquidez None → `round_trip_pct = inf`) → implementar → commit.

### Task 11: Estratégias

**Files:** Create `backend/app/strategy/base.py`, `established_pullback.py`, `uptrend_momentum.py`, `breakout_retest.py`, `reversal_confirmed.py`, `new_token_momentum.py`, `abnormal_volume.py`, `registry.py` em `backend/app/strategy/`. Test `backend/tests/test_strategies.py` (séries sintéticas geradas no teste, identificadas como sintéticas).

**Interfaces:** `AnalysisContext(token: dict, category, df: DataFrame com indicadores, snap: PairSnapshot, history: list[PairSnapshot], now)`; `Signal(strategy, entry_low, entry_high, stop, target1, target2, entry_condition: str, invalidation: str, rationale: list[str])`; classe base `Strategy` com `name`, `categories: set[str]`, `min_candles`, `evaluate(ctx) -> Signal|None`, `describe() -> dict` (entrada, invalidação, saída, horizonte, indicadores, limitações). `ALL_STRATEGIES: list[Strategy]`; `run_strategies(ctx) -> list[Signal]` filtra por categoria e `min_candles`.

- [ ] Steps: para cada estratégia, um teste positivo e um negativo com séries sintéticas construídas para satisfazer ou violar a regra da spec 3.5 (ex.: `test_breakout_retest_positive`, `test_breakout_without_volume_rejected`); `test_new_token_momentum_only_new`; `test_all_strategies_describe_complete` (as 7 chaves presentes) → implementar → commit.

### Task 12: Pontuação

**Files:** Create `backend/app/scoring/__init__.py`, `backend/app/scoring/engine.py`. Test `backend/tests/test_scoring.py`.

**Interfaces:** `Component(name, value: float 0–10, weight, reason: str)`; `ScoreResult(total: float, components: list[Component], band: str, net_rr: float, net_target1_pct: float)`; `score_signal(ctx, signal, costs, security, manip, market_regime: float, data_reliability: float, weights: dict) -> ScoreResult`; `band(total) -> "alta_prioridade"|"interessante"|"acompanhar"|"sem_recomendacao"`; `net_rr(signal, costs) -> float` = (alvo1% − custo%) / (stop% + custo%).

- [ ] Steps: testes `test_total_is_weighted_mean_times_10`, `test_bands`, `test_net_rr_includes_costs`, `test_each_component_has_reason` → implementar → commit.

### Task 13: Risk Manager

**Files:** Create `backend/app/risk/__init__.py`, `backend/app/risk/manager.py`. Test `backend/tests/test_risk_manager.py`.

**Interfaces:** `TradeProposal(chain, token_address, strategy, category, score, price, stop, target1, costs: CostEstimate, liquidity_usd, data_reliability, blocks: list[str])`; `BookState(capital_initial, realized_pnl, open_positions: list[OpenPosition(token_address, category, amount_usd)], day_realized_pnl, consecutive_losses, last_loss_at, recent_recs: list[tuple[token, strategy, created_at]], paused: bool)`; `RiskLimits.from_settings(d)`; `RiskDecision(status: Literal["APROVADA","REDUZIDA","VETADA"], amount_usd: float, reasons: list[str])`; `evaluate(proposal, book, limits, now) -> RiskDecision`. `backend/app/risk/` não importa `strategy` nem `scoring` (teste verifica com `ast`).

- [ ] Steps: um teste por limite: `test_veto_on_blocks`, `test_veto_score_below_min`, `test_veto_rr_below_1_5`, `test_veto_target_below_2x_cost`, `test_new_token_capped_at_5`, `test_exposure_cap_15`, `test_new_exposure_cap_5`, `test_reserve_30_respected`, `test_daily_loss_stops`, `test_three_losses_pause_2h`, `test_duplicate_vetoed`, `test_open_position_same_token_vetoed`, `test_size_reduced_by_liquidity_impact`, `test_below_min_after_reduction_vetoed`, `test_no_size_increase_after_loss`, `test_risk_module_has_no_strategy_imports` → implementar → commit.

### Task 14: Portfólio

**Files:** Create `backend/app/portfolio/__init__.py`, `backend/app/portfolio/ledger.py`, `backend/app/portfolio/metrics.py`. Test `backend/tests/test_portfolio.py`.

**Interfaces:** `open_trade(s, ledger: "SIM"|"REAL", token_id, amount_usd, entry_price, fee_usd, executed_at, recommendation_id=None, note="") -> Trade` (com `limit_flags: list[str]`); `close_trade(s, trade_id, exit_price, fee_usd, closed_at, reason) -> Trade` (P&L = amount × (exit/entry − 1) − taxas); `book_state(s, ledger, now, limits) -> BookState`; `compute_metrics(trades) -> dict` (n, win_rate, avg_return_pct, expectancy_usd, profit_factor, max_drawdown_usd, best/worst streak, by_strategy, by_category).

- [ ] Steps: testes `test_pnl_with_fees`, `test_ledgers_are_separate`, `test_manual_trade_over_limit_is_flagged`, `test_drawdown_and_streaks`, `test_profit_factor_no_losses_is_inf` → implementar → commit.

### Task 15: Recomendações (formato, expiração, deduplicação)

**Files:** Create `backend/app/recommend/__init__.py`, `backend/app/recommend/format.py`, `backend/app/recommend/lifecycle.py`. Test `backend/tests/test_recommend.py`.

**Interfaces:** `build_recommendation(ctx, signal, score, decision, costs, sources) -> dict` (todas as chaves da spec 4.2); `render_text(rec: dict) -> str` (blocos em maiúsculas na ordem da spec; "CONFIANÇA ESTATÍSTICA: Sem estimativa confiável" sem calibração); `should_expire(rec, latest_snap, now, verdict_blocks) -> str|None` (motivo); constante `NO_TRADE_MESSAGE = "SEM OPERAÇÃO RECOMENDADA — aguardando condições melhores."`.

- [ ] Steps: testes `test_render_has_all_fields_in_order`, `test_expires_after_10_min`, `test_expires_when_price_runs_1_5pct`, `test_expires_below_stop`, `test_expires_on_stale_data` → implementar → commit.

### Task 16: Coletor e ciclo de análise

**Files:** Create `backend/app/collector/__init__.py`, `backend/app/collector/service.py`, `backend/app/recommend/engine.py`. Test `backend/tests/test_engine.py` (provedores falsos em memória com dados dos fixtures).

**Interfaces:** `MarketService(dex, gecko, goplus, session_factory, settings)` com `async discover()`, `async refresh_tier1()`, `async refresh_candles()`, `async refresh_security(token)`, `provider_status() -> list[dict]`, contadores de nível; `AnalysisEngine(market, session_factory, notifier, runtime)` com `async run_cycle(kind: "quick"|"full", trigger: str) -> CycleResult(analyzed, candidates, recommendations, rejections, message)` sob `asyncio.Lock`; `async monitor_positions()`; `async track_outcomes()` (preço 60 min após cada avaliação); `Scheduler` com tarefas periódicas (60 s, 5 min, 60 min) e `pause()/resume()`.

- [ ] Steps: testes `test_full_cycle_without_candidates_returns_no_trade_message`, `test_full_cycle_rejections_are_recorded`, `test_cycle_lock_prevents_duplicates` (duas `run_cycle` concorrentes → ≤ 1 ativa por ativo+estratégia), `test_blocked_when_all_providers_down`, `test_sim_ledger_auto_opens_on_approval`, `test_monitor_closes_sim_on_stop` → implementar → commit.

### Task 17: Notificações

**Files:** Create `backend/app/notify/__init__.py`, `backend/app/notify/hub.py`, `backend/app/notify/channels.py`. Test `backend/tests/test_notify.py`.

**Interfaces:** `Notifier(session_factory, channels)` com `async notify(kind, key, title, body, severity, data, relevant_change=False) -> bool` (dedupe 30 min por key); canais `InAppChannel(broadcast)`, `WindowsToastChannel(enabled)` (winotify, ignora fora do Windows), `TelegramChannel` (só com token+chat_id; padrão desligado; envio via Bot API documentada).

- [ ] Steps: testes `test_duplicate_within_30min_suppressed`, `test_relevant_change_bypasses_dedupe`, `test_telegram_disabled_without_config` → implementar → commit.

### Task 18: Backtest e calibração

**Files:** Create `backend/app/backtest/__init__.py`, `backend/app/backtest/engine.py`, `backend/app/backtest/calibration.py`. Test `backend/tests/test_backtest.py`.

**Interfaces:** `time_split(items, ratios=(0.6,0.2,0.2))`; `simulate(df_by_token: dict, strategies, cost_cfg, chain_of: dict, max_bars=12) -> list[BTTrade]` (entrada no fechamento + slippage; alvo e stop no mesmo candle → stop); `bt_metrics(trades) -> dict`; `isotonic_fit(x, y) -> callable` (PAV); `calibrate(scores, outcomes, min_samples=200) -> Calibrator|None`.

- [ ] Steps: testes `test_same_bar_target_and_stop_counts_stop`, `test_time_split_no_shuffle`, `test_isotonic_monotonic`, `test_calibrate_returns_none_under_200` → implementar → commit. Script `backend/scripts/backtest.py` roda sobre o banco local e imprime relatório.

### Task 19: API REST e WebSocket

**Files:** Create `backend/app/api/__init__.py`, `backend/app/api/routes.py`, `backend/app/api/ws.py`, `backend/app/main.py`. Test `backend/tests/test_api.py` (TestClient, sem iniciar o scheduler).

**Interfaces:** `GET /api/dashboard`, `/api/opportunities`, `/api/new-tokens`, `/api/tokens/{id}` (+candles, segurança, avaliações), `/api/recommendations`, `POST /api/recommendations/{id}/executed` (`{price, amount_usd, fee_usd, executed_at}`), `/ignored`, `GET /api/portfolio/{ledger}`, `POST /api/trades`, `POST /api/trades/{id}/close`, `GET /api/trades`, `/api/stats`, `GET/PUT /api/settings`, `GET /api/providers`, `GET /api/logs`, `/api/audit`, `POST /api/control/pause|resume|scan`, `GET /api/notifications`, `WS /ws`. `create_app(start_background: bool = True)`.

- [ ] Steps: testes `test_dashboard_shape`, `test_execute_triggers_full_cycle`, `test_settings_put_audits`, `test_invalid_settings_rejected` (ex.: reserva > capital) → implementar → commit.

### Task 20: Frontend

**Files:** `frontend/` (Vite React TS), `src/api.ts`, `src/ws.ts`, `src/format.ts`, `src/components/*`, `src/pages/*` (11 páginas da spec 5.1), `src/format.test.ts`.

- [ ] Steps: teste Vitest `formatUsd`, `formatPrice` (preços muito pequenos com dígitos significativos), `formatAge` → implementar páginas → `npm run build` sem erros de tipo → abrir no navegador e conferir cada página com o backend real → commit.

### Task 21: Inicialização e documentação

**Files:** `iniciar.bat`, `backend/Dockerfile` (opcional), `README.md`, `docs/arquitetura.md`, `docs/fontes-de-dados.md`, `docs/uso.md`, `.env.example`.

- [ ] Steps: `iniciar.bat` cria venv se faltar, instala, faz build do frontend se faltar e sobe `uvicorn` em 127.0.0.1:8765 abrindo o navegador; rodar e conferir → commit.

### Task 22: Teste prolongado

- [ ] Steps: rodar o app com provedores reais por um período contínuo; conferir logs sem exceções não tratadas, consumo de orçamento dentro dos limites, recomendações ou rejeições registradas; corrigir falhas; documentar resultado em `docs/uso.md` → commit.
