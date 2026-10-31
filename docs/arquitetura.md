# Arquitetura

O app é um único processo local: FastAPI com tarefas asyncio, banco SQLite em modo WAL e uma interface
React compilada, servida pelo próprio backend em `127.0.0.1:8765`. Não depende de Docker, PostgreSQL,
Redis nem hospedagem paga.

```
backend/app/
  chains.py          redes e identificadores por provedor
  config.py          .env (Settings) e padrões editáveis (DEFAULT_RUNTIME)
  domain.py          PairSnapshot, Candle, SecurityReport
  costs.py           custo de ida e volta: taxa FOMO (com mínimo), pool, impacto, slippage, gás
  db/                modelos, sessão, configurações auditadas
  providers/         base (limite, backoff, saúde), dexscreener, geckoterminal, goplus
  collector/         MarketService (coleta em dois níveis) e Scheduler (tarefas periódicas)
  market/            categoria, detectores de manipulação, confiabilidade
  security/rules.py  bloqueios e penalidades de contrato (EVM e Solana)
  newtokens/         classificação A/B/C
  strategy/          indicadores (RSI/ATR de Wilder, EMA, MACD, Bollinger, VWAP) e 6 estratégias
  scoring/           nota de 0 a 100 com 10 componentes explicados
  risk/manager.py    Risk Manager independente (não importa strategy nem scoring)
  recommend/         motor do ciclo, formato obrigatório, expiração
  portfolio/         livros SIM e REAL, métricas
  notify/            central com deduplicação; canais app, Windows e Telegram (desligado)
  backtest/          simulação com custos, divisão temporal, calibração isotônica, relatórios
  api/               REST, WebSocket, validação de configurações
  main.py            montagem da aplicação
frontend/src/        React + TypeScript + Tailwind + lightweight-charts, 11 páginas
```

## Fluxo de dados

1. **Descoberta:** o ciclo completo e, a cada 15 min, `new_pools` buscam no GeckoTerminal pools novos e em alta nas 6 redes.
2. **Nível 1:** a cada 60 s, a DexScreener atualiza em lote o preço, a liquidez, o volume e as compras/vendas.
3. **Nível 2:** a tarefa contínua busca candles de 5 min para os 20 ativos mais ativos que passam nos filtros.
4. **Ciclo:** o ciclo rápido roda a cada 60 s e o completo a cada 60 min. O completo também roda logo depois de você informar uma execução. Para cada ativo, o ciclo:
   - aplica segurança, manipulação, categoria e classe A/B/C;
   - calcula os indicadores e roda as estratégias;
   - estima custos, pontua e passa pelo Risk Manager;
   - grava a avaliação.
5. **Seleção:** as aprovadas são ordenadas por nota (desempate pelo R:R líquido). O risco é reavaliado a cada escolha, e as recomendações ativas reservam capital.
6. **Publicação:** a recomendação recebe o texto padrão, gera notificação e abre uma operação no livro SIM.
7. **Acompanhamento:**
   - as recomendações expiram por tempo, preço, dado obsoleto ou novo bloqueio;
   - as posições recebem alertas de saída, e as do livro SIM fecham sozinhas;
   - 60 min depois, o resultado de cada avaliação (recomendada ou rejeitada) é gravado.

## Decisões de engenharia

| Decisão | Motivo |
|---|---|
| Um processo e SQLite | Um usuário e poucas chamadas por minuto: PostgreSQL e Redis não se pagam. O SQLAlchemy permite trocar depois. |
| Indicadores próprios, sem TA-Lib | A TA-Lib exige compilação no Windows. Os indicadores próprios são testados contra o exemplo clássico de Wilder. |
| Risk Manager sem imports de estratégia | Um teste com `ast` garante que nenhuma nota alta consegue contornar os limites. |
| Pior caso entre fontes de segurança | Um sinal de risco em qualquer fonte conta. |
| Permissões administrativas só vetam com owner ativo | O PEPE (owner renunciado) tem `transfer_pausable=1` e `is_blacklisted=1` no GoPlus. |
| Alvos em 2,5R e 4R | Com alvo de 1,5R, o R:R líquido mínimo de 1,5 seria matematicamente impossível. |
| Recomendações ativas reservam capital | Não supor que o capital está todo disponível. |
| Livro SIM sempre alimentado; `mode` escolhe o livro do Risk Manager | Simulação e real nunca se misturam. |
| Avaliações sem sinal só gravadas nos ciclos completos | Evita cerca de 2.400 linhas por hora. |

## Banco (SQLite, `data/fomo_ai.db`)

| Tabela | Conteúdo |
|---|---|
| `tokens` | rede, contrato, par, categoria, nível, classe A/B/C |
| `snapshots` | dados brutos imutáveis, com horário, origem e confiabilidade |
| `candles` | 5 min, único por token e horário |
| `security_reports` | relatórios de segurança brutos |
| `cycles` | histórico de execução dos ciclos |
| `evaluations` | toda avaliação, com nota, componentes, decisão, motivos e resultado em 60 min |
| `recommendations` | horários da análise e da recomendação, preço, valores, texto completo |
| `trades` | livros SIM e REAL, com horários, preços, taxas, P&L e alertas de limite |
| `events`, `notifications` | registros do sistema e notificações |
| `settings`, `audit_log` | configuração e auditoria de alterações |

## Testes

- Backend: `pytest`, 168 testes. Nenhum acessa a rede; as respostas reais dos provedores ficam gravadas em `backend/tests/fixtures`.
- Frontend: `vitest` para os formatadores e build TypeScript estrito.
