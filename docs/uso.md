# Guia de uso

## Páginas

| Página | Para que serve |
|---|---|
| Dashboard | Capital, saldo, posições, melhor oportunidade, notas recentes, novos tokens, regime de mercado, última e próxima varredura, provedores, alertas e custo de ida e volta por rede |
| Oportunidades | Todas as avaliações (recomendadas e rejeitadas) com motivos e o resultado 60 min depois |
| Novos tokens | Tokens com menos de 72 h, classe A, B ou C, com os motivos |
| Análise de ativo | Gráfico de 5 min (EMA20, EMA50, Bollinger, alvos e stop da recomendação ativa), segurança detalhada por fonte, histórico de análises e componentes da nota |
| Recomendações | Recomendações ativas no formato completo, com os botões "Executei na FOMO" e "Ignorar", e o histórico |
| Portfólio | Livros SIM e REAL separados: saldo, reserva, exposição, P&L realizado e estimado, taxas e registro manual de operações |
| Histórico | Todas as operações, com filtro e ordenação |
| Estatísticas | Taxa de acerto, expectativa, profit factor, drawdown e sequências por estratégia e categoria; eficácia dos filtros; calibração; backtest |
| Risco | Todos os limites, custos, filtros e pesos, editáveis e com auditoria |
| Provedores | Saúde, chamadas por minuto, espera (backoff), níveis de análise e identificadores por rede |
| Logs e diagnóstico | Ciclos, eventos, notificações e varredura manual |

O botão **Pausar monitoramento** fica no topo de todas as páginas e suspende as recomendações. Os
dados continuam sendo coletados.

## Ciclo de uma hora

- **A cada 60 s:** atualiza os preços, expira recomendações, acompanha posições e roda a análise rápida dos ativos do nível 2.
- **A cada 5 min:** renova os candles dos ativos do nível 2.
- **A cada 15 min:** descobre pools novos.
- **A cada 60 min (e logo depois de "Executei na FOMO"):** roda a varredura completa, com descoberta, segurança e comparação global.
- **Quando nada passa nos critérios:** mostra *SEM OPERAÇÃO RECOMENDADA — aguardando condições melhores.*

## Critérios para uma recomendação

Todos são obrigatórios e configuráveis em *Risco*:

- nenhum bloqueio de segurança ou de manipulação;
- token novo só na classe A;
- nota ≥ 80;
- R:R líquido de custos ≥ 1,5 no alvo 1;
- alvo 1 líquido ≥ 2× o custo de ida e volta;
- stop a pelo menos 2× o custo;
- valor dentro dos limites: estabelecidos de US$ 5 a 10, novos até US$ 5;
- exposição total até US$ 15, novos até US$ 5 e reserva mínima de US$ 30;
- perda do dia abaixo de US$ 2,50;
- sem 3 perdas seguidas nas últimas 2 h;
- sem recomendação igual nos últimos 60 min e sem posição aberta no ativo.

## Notificações

- Aparecem no app (canto inferior direito e em *Logs*) e no Windows, para eventos de gravidade alta ou crítica.
- Avisos repetidos do mesmo assunto ficam em silêncio por 30 min, a menos que haja mudança relevante.
- O Telegram fica desligado até você preencher `FOMOAI_TELEGRAM_BOT_TOKEN` e `FOMOAI_TELEGRAM_CHAT_ID` no `.env`.

## Backtest

Em *Estatísticas → Rodar backtest*, ou pelo terminal com `backend\.venv\Scripts\python backend\scripts\backtest.py`.

- Usa os candles gravados pelo próprio app (pelo menos 150 candles por ativo, cerca de 12 h no nível 2).
- Aplica custos completos e divide os dados em ordem temporal: 60% treino, 20% validação e 20% teste.
- Estratégias que dependem do fluxo de compras e vendas não entram, porque os candles não trazem esse dado.
- A calibração "nota → probabilidade" só aparece com pelo menos 200 resultados no conjunto de teste. Até lá, toda recomendação mostra "Sem estimativa confiável".

## Teste prolongado (31/10/2026)

App rodando com provedores reais por 75 min (14:44–15:59 UTC), com uma checagem a cada 5 min.

| Item | Resultado |
|---|---|
| Estado do sistema | OPERANDO em todas as 15 checagens |
| Erros do agendador | 0 |
| Linhas ERROR/CRITICAL no log | 0 |
| Avisos (WARNING) | 39, sendo 18 por HTTP 429 do GeckoTerminal e o restante sobre falta de dados de segurança |
| Ciclos completos de análise | 1 por hora, sem sobreposição; ciclos rápidos a cada 2 min |
| Tokens no nível 1 / nível 2 | 236 / 20 |
| Recomendações emitidas | 0 |

Os avisos de 429 são esperados: a API gratuita do GeckoTerminal às vezes recusa chamadas mesmo abaixo de 6/min. O app espera o tempo de backoff e tenta de novo. Nenhum preço ficou desatualizado a ponto de bloquear o sistema.

O resultado de zero recomendações também é esperado. As estratégias dispararam, mas todos os sinais foram vetados por nota abaixo de 80 ou porque os custos de operar US$ 5–10 (taxa mínima de US$ 0,50 por lado) exigem alvos fora do alcance. O dashboard mostra o alvo mínimo que vale a pena com o capital configurado.
