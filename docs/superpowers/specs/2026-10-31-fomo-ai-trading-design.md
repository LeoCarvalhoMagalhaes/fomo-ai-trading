# FOMO AI Trading Intelligence — Especificação de design

Data: 31/10/2026 · Autor: Leonardo Carvalho Magalhães (com Claude) · Status: aprovado para implementação

## 0. Propósito e limites

Ferramenta **consultiva**, local, para Windows, que monitora tokens negociáveis no ecossistema da FOMO
(fomo.family), encontra poucas oportunidades de curto prazo (horizonte ~60 min), explica cada uma
com evidências verificáveis e registra o resultado. O usuário executa manualmente no app da FOMO.

Limites inegociáveis:

- Nenhuma integração com a FOMO. A FOMO não publica API; os Termos (atualizados em 26/10/2026)
  proíbem bots, crawlers, data mining e ferramentas de terceiros acessando a conta. O app nunca
  lê fomo.family, nunca guarda credenciais, cookies ou sessões da FOMO e nunca executa ordens.
- Só provedores com uso documentado (seção 2). Sem scraping.
- Nenhum dado inventado. Dado ausente reduz confiança ou bloqueia.
- Nenhuma recomendação contorna o Risk Manager. "Sem operação" é um resultado válido.
- Pontuação não é probabilidade. Probabilidade só com modelo calibrado fora da amostra.
- Simulação e operações reais ficam em livros separados.

Fora do escopo: execução de ordens, alavancagem, venda a descoberto (DIREÇÃO é sempre Compra,
porque a FOMO só faz spot), Telegram ativo (só a porta de integração, desligada).

## 1. Arquitetura

App web local num único processo de backend.

- Backend: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 + SQLite (WAL), httpx assíncrono,
  pandas/numpy para indicadores (implementados no projeto e testados contra valores conhecidos;
  sem TA-Lib, que exige compilação no Windows).
- Frontend: React + TypeScript + Vite + Tailwind + lightweight-charts (TradingView, Apache-2.0).
  O build é servido pelo próprio FastAPI; em desenvolvimento, Vite com proxy.
- Comunicação: REST + WebSocket (`/ws`) para eventos ao vivo.
- Notificações desktop: toast do Windows emitido pelo backend (funciona com o navegador fechado).
- Inicialização: `iniciar.bat`. Docker opcional (Dockerfile), não necessário.

```
backend/app/
  config.py        configurações (env + tabela settings editável, com auditoria)
  db/              modelos SQLAlchemy, sessão, criação de schema
  providers/       adaptadores; interfaces MarketDataProvider, SecurityProvider
  collector/       agendador, orçamento de chamadas (token bucket), saúde dos provedores
  market/          normalização, snapshots, candles amostrados, detectores de manipulação
  security/        regras SPL e EVM → bloqueios e penalidades
  newtokens/       classificação A/B/C
  strategy/        indicators.py + uma estratégia por arquivo
  scoring/         pontuação 0–100 explicável
  costs.py         taxas, slippage, gás por rede
  risk/            Risk Manager (não importa strategy nem scoring)
  recommend/       ciclo, expiração, deduplicação, formato padrão
  portfolio/       livros SIM e REAL, P&L, drawdown, sequências
  notify/          in-app, toast Windows, porta Telegram
  backtest/        replay, divisão temporal, métricas, calibração
  api/             rotas REST e WebSocket
  main.py          app FastAPI + ciclo de vida das tarefas
backend/tests/     pytest; respostas reais dos provedores gravadas em fixtures
frontend/          SPA
docs/              arquitetura, fontes de dados, uso
```

Fluxo: coletores → snapshots (timestamp, origem, confiabilidade) → features de mercado e segurança →
estratégias geram candidatos → custos → pontuação → Risk Manager (aprova, reduz ou veta) →
recomendação **ou** rejeição registrada com motivo → notificação. Rejeições e recomendações são
acompanhadas por 60 min para medir o que teria acontecido.

## 2. Fontes de dados

Verificado ao vivo em 31/10/2026:

| Rede | GeckoTerminal | DexScreener | GoPlus |
|---|---|---|---|
| Solana | solana | solana | solana |
| Base | base | base | 8453 |
| BNB Chain | bsc | bsc | 56 |
| Ethereum | eth | ethereum | 1 |
| Monad | monad | monad | 143 |
| Robinhood Chain | robinhood | robinhood | 4663 |

| Provedor | Uso | Limite |
|---|---|---|
| GeckoTerminal API v2 (`api.geckoterminal.com/api/v2`, sem chave) | `new_pools` por rede (pools das últimas 48 h), `trending_pools`, OHLCV 1/5/15 min (até 1000 candles), `tokens/{addr}/info` (holders top 10, mint/freeze, honeypot) | ~10 chamadas/min (documentado no plano gratuito). Orçamento: 10/min, configurável |
| DexScreener (`api.dexscreener.com`, sem chave) | `tokens/v1/{chain}/{até 30 endereços}` para preço, liquidez, volume, compras/vendas por janela (m5, h1, h6, h24), `pairCreatedAt`, fdv, market cap | 300/min nos endpoints de pares e tokens. Orçamento: 60/min |
| GoPlus (`api.gopluslabs.io`, sem chave) | `token_security/{chain_id}` (EVM) e `solana/token_security` | Cota gratuita; orçamento de 20/min |
| RugCheck (opcional, chave gratuita do usuário) | relatório de risco Solana | só candidatos Solana |

Termos: a DexScreener permite uso comercial e não comercial, proíbe revender o acesso ou repassar os
dados a terceiros. Uso pessoal local é compatível. Atribuição: o app mostra a fonte de cada dado.

**Pré-seleção em dois níveis.** Nível 1 (amplo, barato): tokens descobertos via `new_pools` e
`trending_pools` das 6 redes, atualizados pela DexScreener em lote a cada 60 s. Nível 2
(profundo, até 40 ativos): os que passam nos filtros mínimos recebem candles 5 min e checagem de
segurança. O painel mostra quantos ativos estão em cada nível. O app não afirma cobrir "todo o mercado".

**Universo FOMO.** Sem API da FOMO não há lista oficial. Pressuposto: tokens com pool em DEX numa das
6 redes podem estar disponíveis na FOMO. Toda recomendação traz "Confirme no app da FOMO que o token
e o contrato são os mesmos antes de executar".

**Confiabilidade (0–1)** de cada snapshot: começa em 1; ×0,5 se a fonte é derivada (candles
amostrados); ×0,6 se o preço da DexScreener e o do GeckoTerminal divergem > 2%; decai com a idade
(preço > 120 s = obsoleto → bloqueia). Holders em beta: confiança do componente de concentração ×0,8.

**Falhas.** Backoff exponencial (2 s → 5 min). GeckoTerminal fora do ar: candles amostrados dos
snapshots DexScreener, estratégias de volume suspensas. GoPlus fora do ar: nenhum token novo
recomendado; estabelecidos com penalidade. Todos fora: sistema em estado BLOQUEADO, sem recomendações.

## 3. Segurança, mercado, estratégias e pontuação

### 3.1 Bloqueios de segurança (veto absoluto)

EVM (GoPlus): `is_honeypot=1`; `cannot_sell_all=1`; `cannot_buy=1`; `buy_tax` ou `sell_tax`
> 10%; `selfdestruct=1`; `hidden_owner=1`; `can_take_back_ownership=1`; `honeypot_with_same_creator=1`.
Permissões administrativas (`transfer_pausable`, `is_blacklisted`, `owner_change_balance`,
`slippage_modifiable`, `trading_cooldown`) vetam apenas se houver owner ativo (`owner_address` não
vazio e diferente de 0x000…000/0x…dead); com owner renunciado viram penalidade leve. Motivo: dados
reais (PEPE, owner renunciado) trazem `transfer_pausable=1` e `is_blacklisted=1` sem ninguém capaz
de usar essas funções.

Solana (GoPlus `solana/token_security`, GeckoTerminal `tokens/{addr}/info`, RugCheck opcional):
`freezable.status=1` ou `freeze_authority=yes`; `balance_mutable_authority.status=1`;
`non_transferable=1`; `transfer_fee` > 5%; `transfer_hook` não vazio em token novo; honeypot
reportado (`is_honeypot=yes`); em token novo, `mintable.status=1` ou `mint_authority=yes`.
O GeckoTerminal também traz `buyers`/`sellers` (carteiras únicas por janela) nos pools — usado para
medir carteiras independentes.

Comuns: token novo sem nenhum dado de segurança; concentração top 10 > 60% (excluindo pools/queima
quando identificáveis) em token novo; liquidez caiu > 30% em 15 min (possível remoção).

Penalidades (não vetam): mint ativo em token estabelecido; owner não renunciado; contrato não
verificado; taxa de 3–10%; criador com > 10%; concentração 40–60%; holders sem dado.

Passar nos filtros não significa token seguro, só ausência de sinais críticos nas fontes consultadas.
A tela diz isso.

### 3.2 Detectores de manipulação de mercado

- Pump: alta 1 h > +100% → penalidade forte; > +300% → bloqueio.
- Wash trading (proxy): volume 24 h / liquidez > 30× → suspeito; > 80× → bloqueio. Também
  compras ≈ vendas (±5%) com volume alto e preço parado.
- Volume incompatível: volume 5 min > 50% da liquidez.
- Baixa liquidez: estabelecido < US$ 50 mil, novo < US$ 15 mil → bloqueio.
- Pressão compradora artificial: razão compras/vendas 5 min > 6 → suspeito (bots/snipers).
- Queda de liquidez (ver 3.1).

### 3.3 Categorias

- Estabelecido: par mais líquido com idade ≥ 7 dias e liquidez ≥ US$ 250 mil.
- Novo: idade < 72 h.
- Intermediário (7 dias > idade ≥ 72 h, ou liquidez menor): tratado como estabelecido para limites
  de valor, com penalidade de dados.

Novos tokens são classificados A (oportunidade potencial: zero bloqueios, segurança de 2 fontes
ou 1 fonte limpa com cobertura completa, compradores crescendo, liquidez estável ou crescente,
idade ≥ 30 min), B (acompanhar: sem bloqueios mas falta confirmação) ou C (evitar: qualquer
bloqueio). Só A pode virar recomendação.

### 3.4 Indicadores

RSI(14), EMA(9/20/21/50), SMA(20), MACD(12,26,9), Bandas de Bollinger(20,2), ATR(14), VWAP de
sessão (reinicia às 00:00 UTC; só quando há volume por candle real), volume relativo (volume do
candle / média de 20), máximas e mínimas de 24 candles (suporte e resistência), divergência de RSI.
Volume Profile não é implementado porque os provedores gratuitos não dão volume por preço.

### 3.5 Estratégias (candles de 5 min, horizonte 60 min)

Cada uma declara entrada, invalidação, saída, indicadores e limitações em `describe()`.

1. **established_pullback** (estabelecidos): EMA20 > EMA50; preço recua até ±0,5 ATR da EMA20;
   RSI 40–55 subindo. Stop: mínima dos últimos 6 candles − 0,25 ATR. Alvos 1,5R e 2,5R.
   Limitação: falha em reversões rápidas de tendência.
2. **uptrend_momentum**: EMA9 > EMA21 > EMA50; histograma MACD > 0 e crescendo há 2 candles; RSI 55–70;
   preço > VWAP. Stop 1,5 ATR. Alvos 1,5R/2,5R. Limitação: entra tarde em movimentos curtos.
3. **breakout_retest**: fechamento acima da máxima de 24 candles com volume relativo ≥ 2 e o candle
   seguinte reteste o nível sem fechar abaixo. Stop: nível − 0,5 ATR. Limitação: rompimentos falsos.
4. **reversal_confirmed** (só estabelecidos): divergência de alta no RSI nos últimos 12 candles,
   fechamento de volta acima da banda inferior e acima da EMA9. Stop: mínima da divergência −
   0,25 ATR. Limitação: tendência de baixa forte invalida.
5. **new_token_momentum** (só novos classe A): idade 30 min–72 h; compras/vendas 5 min entre 1,2 e
   3; transações 5 min ≥ média de 5 min da última hora; alta desde o lançamento ≤ 3×; liquidez sem
   queda. Stop: máx(12%, 1,5 ATR). Alvos 1,5R/2,5R. Valor máximo US$ 5.
6. **abnormal_volume**: volume relativo ≥ 3, candle de alta, compras > vendas, liquidez estável,
   preço ainda ≤ 1 ATR acima da abertura do candle de volume. Stop: mínima do candle de volume.

O stop nunca fica a menos de 2× o custo total de ida e volta. Se ficaria, a operação é rejeitada.

### 3.6 Custos

Por lado: taxa FOMO (configurável, padrão 1,0%, porque a FOMO só mostra a taxa na confirmação),
taxa de pool (padrão 0,3%), impacto de preço estimado = valor / (liquidez / 2), slippage base 0,5%.
Gás por operação (configurável, padrão): Solana US$ 0,01, Base 0,02, BSC 0,05, Monad 0,02,
Robinhood 0,02, Ethereum 1,50. Custo total ida e volta em % do valor entra em todas as contas de
risco/retorno. Com US$ 5 no Ethereum o gás sozinho é 60% de ida e volta — o sistema rejeita.

### 3.7 Pontuação (0–100)

Dez componentes, cada um 0–10, com peso configurável (padrão 10% cada): momentum, volume,
liquidez, estrutura técnica, confirmação de tendência, qualidade dos dados, segurança do contrato,
risco de manipulação (invertido), relação risco/retorno líquida, condições de mercado (proporção
de ativos monitorados em alta, ponderada por liquidez). Cada componente vem com a frase que o
justifica. Faixas: 90–100 alta prioridade; 80–89 interessante; 70–79 acompanhar; < 70 sem
recomendação. Recomendação exige ≥ 80 (configurável), R:R líquido ≥ 1,5 e alvo 1 líquido ≥ 2× custo.
Uma nota alta nunca derruba um veto.

Entre candidatos de um mesmo ativo vence a estratégia de maior R:R líquido; entre ativos, maior
pontuação, desempate por R:R.

## 4. Risco, recomendações e portfólio

### 4.1 Risk Manager

Entrada: proposta (ativo, categoria, valor desejado, preço, stop, alvos, custos, nota) + estado do
livro ativo + configurações. Saída: APROVADA (valor final), REDUZIDA, VETADA (motivos).

Padrões (todos configuráveis, alterações auditadas): capital US$ 50; estabelecido US$ 5–10; novo
máx. US$ 5; exposição simultânea máx. US$ 15; novos máx. US$ 5; reserva mínima US$ 30; perda
diária máx. US$ 2,50 (dia UTC); sem alavancagem; 3 perdas seguidas pausam novas recomendações
por 2 h; sem duplicatas (mesmo ativo + estratégia com recomendação ativa ou nos últimos 60 min, ou
posição aberta no ativo).

Valor: base = máximo da categoria × fator de nota (80→0,6; 90→0,8; ≥ 95→1,0) × confiança dos dados,
limitado por impacto de preço ≤ 0,5%, pelo espaço de exposição e pela reserva. Nunca acima do
valor-base depois de perdas (sem martingale). Abaixo do mínimo da categoria → veto.

Disponível = capital atual − posições abertas − reserva. Capital atual = inicial + P&L realizado do livro.

### 4.2 Ciclo

- A cada 60 s: atualização nível 1 e avaliação rápida dos ativos nível 2 com dados novos.
- A cada 5 min: candles nível 2 (dentro do orçamento).
- A cada 60 min: varredura completa (descoberta em todas as redes, segurança, todas as estratégias,
  comparação global).
- Execução informada pelo usuário: dispara uma varredura completa imediata.
- Sem candidato aprovado: estado "SEM OPERAÇÃO RECOMENDADA — aguardando condições melhores."

Recomendação: estados ATIVA → EXECUTADA | IGNORADA | EXPIRADA. Expira em 10 min, se o preço sair
da zona de entrada (> 1,5% acima do preço observado ou abaixo do stop), se o dado ficar obsoleto
ou se um veto aparecer. Guarda horário da análise, horário da recomendação, preço observado; a
execução guarda horário e preço informados pelo usuário; o fechamento guarda horário, preço,
taxas e resultado.

Formato obrigatório: TOKEN, REDE, CONTRATO, TIPO, DIREÇÃO (Compra), PREÇO OBSERVADO, VALOR
SUGERIDO, HORIZONTE, ENTRADA (zona + condição), ALVO 1, ALVO 2, INVALIDAÇÃO, STOP DE REFERÊNCIA,
PONTUAÇÃO, CONFIANÇA ESTATÍSTICA ("Sem estimativa confiável" até haver calibração), JUSTIFICATIVA,
RISCOS, CENÁRIO NEGATIVO, CUSTOS ESTIMADOS, FONTES (com horário), aviso de confirmar no app da FOMO.

### 4.3 Portfólio

Dois livros: SIMULAÇÃO e REAL. Modo padrão: SIMULAÇÃO.

- SIMULAÇÃO: toda recomendação aprovada é executada no papel ao preço observado + custos;
  o usuário também pode registrar operações simuladas manualmente.
- REAL: só o que o usuário informa (preço, valor e taxa vistos na FOMO).
- Posições abertas são monitoradas: alerta de alvo, stop e fim do horizonte. No livro SIM a saída é
  automática (alvo 1, stop ou 60 min — o que vier primeiro, avaliado nos snapshots de 60 s, que é
  uma aproximação declarada). No REAL o usuário fecha.
- Métricas por livro: saldo, reservado, exposição por ativo e por novos, P&L realizado e não
  realizado estimado, taxas, rentabilidade, drawdown máximo, sequências.
- Período de observação: até 50 operações SIM fechadas e 14 dias, o modo REAL mostra aviso fixo.

## 5. Interface, notificações, backtest e testes

### 5.1 Páginas

1 Dashboard · 2 Oportunidades · 3 Novos tokens · 4 Ativo (gráfico com candles, EMAs, Bollinger,
RSI, segurança, histórico) · 5 Recomendações (ativa + histórico, botões Executei/Ignorei) ·
6 Portfólio · 7 Histórico de operações · 8 Estatísticas (por estratégia, categoria, novos) ·
9 Risco (limites editáveis) · 10 Provedores (status, orçamento, chaves opcionais) · 11 Logs e
diagnóstico (eventos, auditoria, pausa do monitoramento). Tema escuro padrão, alternância claro.

Dashboard: capital, disponível, posições, melhor oportunidade, top notas, novos tokens relevantes,
regime de mercado, última análise, próxima varredura, status dos provedores, alertas.

### 5.2 Notificações

Eventos: oportunidade alta prioridade, novo token A, risco crítico em ativo monitorado ou posição,
recomendação expirada, alvo/stop/horizonte, operação informada, limite de perda, falha de coleta,
dado obsoleto, operação encerrada. Canais: in-app (WebSocket + central de notificações), toast do
Windows (opcional), Telegram (interface, desligada). Deduplicação por chave (tipo + ativo +
estado) com silêncio de 30 min salvo mudança relevante (nota ±5, mudança de estado).

### 5.3 Backtest e validação

- Dados: snapshots gravados pelo próprio app + OHLCV histórico do GeckoTerminal para estabelecidos.
- Divisão temporal 60/20/20 (treino/validação/teste), sem embaralhar; parâmetros escolhidos em
  validação, relatório final só em teste.
- Simula entrada no fechamento do candle de sinal + slippage, custos completos, saída por alvo 1,
  stop ou 12 candles; se alvo e stop caem no mesmo candle, conta o stop (conservador).
- Métricas: nº de operações, taxa de acerto, retorno médio, expectativa, profit factor, R:R médio,
  drawdown máximo, por estratégia, categoria e novos.
- Calibração: regressão isotônica nota → P(alvo 1 antes do stop), só com ≥ 200 resultados no
  conjunto de teste; caso contrário "Sem estimativa confiável".
- Rejeições também têm o resultado de 60 min registrado, para medir os filtros.

### 5.4 Confiabilidade e segurança

Variáveis sensíveis só em `.env` (chaves opcionais de provedores); `.env` no `.gitignore`.
Validação Pydantic de toda resposta externa; resposta inválida é descartada e registrada.
Logs estruturados JSON em `data/logs/`. Tabela de eventos e tabela de auditoria de configurações.
Pausa global. Estado BLOQUEADO diante de falha crítica.

### 5.5 Testes

pytest para todos os módulos do backend, com fixtures gravadas das respostas reais dos provedores;
nenhum teste chama a rede, exceto `-m live` (opt-in). Testes do Risk Manager cobrem cada limite.
Frontend: build TypeScript estrito e testes Vitest dos utilitários de formatação. Teste prolongado:
execução real por um período definido, com verificação de erros no log.

### 5.6 Custos e riscos técnicos

Custo: US$ 0. Riscos: limite de 10/min do GeckoTerminal restringe a profundidade; provedores mudam
APIs sem aviso (adaptadores isolados + testes de contrato); dados de holders em beta; preço e taxa
da FOMO diferentes dos de DEX; custos de ida e volta podem tornar a estratégia sem expectativa
positiva — o sistema deve mostrar isso se acontecer; resolução de 60 s no acompanhamento.
