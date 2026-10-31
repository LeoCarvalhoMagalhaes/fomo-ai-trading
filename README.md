# FOMO AI Trading Intelligence

Ferramenta **local e consultiva** para Windows. Ela monitora tokens negociados no ecossistema da FOMO
(fomo.family), procura poucas oportunidades de curto prazo (horizonte de cerca de 60 min), explica cada
uma com evidências verificáveis e registra o que aconteceu depois.

> **O que ela não faz:** não executa ordens, não controla o navegador, não acessa a FOMO e não guarda
> nenhuma credencial. A FOMO não publica API, e os Termos de Uso dela (atualizados em 26/10/2026)
> proíbem bots, crawlers e coleta automatizada. Os dados vêm de provedores públicos de DEX on-chain
> (DexScreener, GeckoTerminal, GoPlus). Toda execução é manual, feita por você no app da FOMO.
>
> Nada aqui garante lucro. A pontuação ordena as oportunidades e **não é probabilidade**. "Sem operação
> recomendada" é um resultado normal e frequente.

## Iniciar

Requisitos: Python 3.12 ou mais recente e Node.js 20 ou mais recente (o Node só é necessário na primeira vez, para compilar a interface).

1. Dê dois cliques em **`iniciar.bat`**.
2. O navegador abre em <http://127.0.0.1:8765>.
3. Para encerrar, feche a janela do terminal.

Na primeira execução são criados o ambiente Python (`backend\.venv`), a interface compilada
(`frontend\dist`) e o banco local (`data\fomo_ai.db`). O primeiro ciclo completo leva alguns minutos,
porque a API pública do GeckoTerminal permite poucas chamadas por minuto.

Para rodar todos os testes, use **`testes.bat`**.

## O que você precisa saber antes de usar dinheiro real

- **Os custos dominam operações pequenas.** Fontes não oficiais citam uma taxa de 0,5% na FOMO com
  **mínimo por ordem** (até US$ 0,50 na Solana e cerca de US$ 0,95 em outras redes). Com US$ 5 a 10,
  isso significa 5% a 19% por lado. O app usa por padrão máx(0,5%, US$ 0,50) por lado e mostra no
  dashboard o custo de ida e volta por rede. **Confira a taxa real na tela de confirmação da FOMO** e
  ajuste em *Risco → Custos*.
- Com esses custos, uma recomendação exige movimentos grandes em 60 min. Na maior parte do tempo o
  sistema não vai recomendar nada, e isso é o filtro funcionando.
- Comece no **modo SIM** e deixe o livro de simulação acumular pelo menos 50 operações e 14 dias
  (período de observação). Depois avalie *Estatísticas*: expectativa, profit factor e eficácia dos filtros.
- Passar nos filtros de segurança **não** significa que o contrato é seguro, só que as fontes
  consultadas não mostraram sinais críticos.

## Uso diário

1. **Dashboard:** capital, saldo, posições, melhor oportunidade, notas, novos tokens, regime de mercado,
   status dos provedores e alertas.
2. Quando surgir uma recomendação, leia a justificativa, os riscos e o cenário negativo. Se decidir
   operar, **confirme na FOMO que o contrato é o mesmo**, execute lá e clique em **"Executei na FOMO"**,
   informando o preço, o valor e a taxa reais. Uma nova varredura começa na hora.
3. A posição passa a ser monitorada, e você recebe alertas de alvo, stop e fim do horizonte. Quando
   vender na FOMO, registre o encerramento em *Portfólio*.
4. Se não executou, clique em **"Ignorar"**. A recomendação também expira sozinha em 10 min, se o preço
   sair da zona de entrada ou se os dados ficarem desatualizados.

Documentação completa:

- [docs/uso.md](docs/uso.md): páginas, fluxo, configurações e resultado do teste prolongado.
- [docs/publicacao.md](docs/publicacao.md): versão online (GitHub Pages + Render + Supabase), senha e limites gratuitos.
- [docs/arquitetura.md](docs/arquitetura.md): módulos, fluxo de dados, banco e decisões de engenharia.
- [docs/fontes-de-dados.md](docs/fontes-de-dados.md): provedores, termos, limites e o que ficou de fora.
- [docs/superpowers/specs/](docs/superpowers/specs/): especificação de design.
- [docs/superpowers/plans/](docs/superpowers/plans/): plano de implementação.

## Configuração opcional (`.env`)

Copie `.env.example` para `.env`. Nada é obrigatório. A chave **Demo gratuita da CoinGecko** aumenta o
limite do GeckoTerminal. Com ela, defina `FOMOAI_GECKO_RPM=25` e aumente *Ativos no nível 2* em *Risco*.
