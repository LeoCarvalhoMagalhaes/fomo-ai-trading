# Fontes de dados

Pesquisa feita em 31/10/2026. Os identificadores de rede foram verificados ao vivo nas APIs.

## FOMO (fomo.family): nenhuma integração

- A FOMO não tem documentação para desenvolvedores nem API pública. O rodapé do site lista About, Blog,
  Release notes, FAQ, Affiliates, Careers, Brand, redes sociais, Privacy e Terms.
- Os Termos de Uso, atualizados em 26/10/2026:
  - Seção 4: ferramentas de terceiros que acessam a conta podem levar à revogação de credenciais e à
    suspensão da conta.
  - Seção 6: as conexões autorizadas são apenas as oferecidas pela própria FOMO.
  - Seção 16: proíbe bots, crawlers, data mining e coleta de dados de preço e transações. O texto literal
    desta seção não pôde ser lido, só um resumo dela; confira no site.
- Seção 7: a taxa depende do valor, do token e da rota, aparece antes da confirmação e pode mudar a
  qualquer momento.
- Fontes não oficiais (sites de indicação, out/2026) citam 0,5% por operação, com mínimo em ordens
  pequenas (até US$ 0,50 na Solana e cerca de US$ 0,95 em outras redes), e 0,05% em alguns tokens
  grandes. **Não verificado.** O app trata a taxa como configuração.
- Redes negociadas pela FOMO: Solana, Base, BNB Chain, Ethereum, Monad e Robinhood Chain.

**Consequência:** o app nunca acessa fomo.family. Os tokens da FOMO têm pools públicos em DEX. O app
analisa esses pools, e toda recomendação pede que você confirme o contrato no app da FOMO.

## Provedores usados

| Provedor | Endpoints | Limite usado | Termos |
|---|---|---|---|
| DexScreener `api.dexscreener.com` | `GET /tokens/v1/{chain}/{até 30 endereços}` | 60/min (documentado: 300/min nos endpoints de pares e tokens) | Uso comercial e não comercial permitido; proíbe revender o acesso ou repassar dados a terceiros. Uso pessoal local é compatível. Não tem candles. |
| GeckoTerminal `api.geckoterminal.com/api/v2` | `networks/{n}/new_pools`, `networks/{n}/trending_pools`, `networks/{n}/pools/{pool}/ohlcv/minute?aggregate=5`, `networks/{n}/tokens/{addr}/info` | **6/min** | Plano público com limite dinâmico. A documentação diz 10/min, mas o teste real deu HTTP 429 a 10/min. A chave Demo grátis aumenta o limite. Holders em beta. |
| GoPlus `api.gopluslabs.io/api/v1` | `token_security/{chain_id}` (EVM), `solana/token_security` | 20/min | Plano gratuito com cota; Solana em beta. Percentuais vêm como fração e o app converte. |

### Identificadores por rede

| Rede | GeckoTerminal | DexScreener | GoPlus |
|---|---|---|---|
| Solana | solana | solana | solana |
| Base | base | base | 8453 |
| BNB Chain | bsc | bsc | 56 |
| Ethereum | eth | ethereum | 1 |
| Monad | monad | monad | 143 |
| Robinhood Chain | robinhood | robinhood | 4663 |

## Avaliados e não usados

- **RugCheck:** `GET /v1/tokens/{mint}/report/summary` respondeu HTTP 400 "unable to generate report"
  para tokens válidos (BONK e um token em alta) em 31/10/2026. Os demais endpoints exigem chave. Ficou
  de fora; a segunda fonte para Solana é o GeckoTerminal.
- **Página de preços da FOMO:** proibida pelos termos.

## Confiabilidade de cada dado

- Todo snapshot guarda horário, origem e nota de 0 a 1.
- Preço com mais de 120 s é obsoleto e bloqueia recomendações.
- Divergência acima de 2% entre DexScreener e GeckoTerminal multiplica a nota por 0,6.
- Dado ausente nunca é inventado:
  - candles faltando → "Sem candles disponíveis";
  - segurança faltando → token novo bloqueado e estabelecido penalizado;
  - liquidez desconhecida → bloqueio.

## Orçamento de chamadas

O limite do GeckoTerminal é o gargalo do projeto. Por isso a análise acontece em dois níveis:

- **Nível 1:** os tokens descobertos nas últimas 6 h, até 240, são atualizados pela DexScreener a cada 60 s, em lotes.
- **Nível 2:** os 20 mais ativos que passam nos filtros mínimos recebem candles de 5 min (renovados a
  cada 5 min) e checagem de segurança no GoPlus. Tokens novos também passam pelo GeckoTerminal.

O app não analisa "todo o mercado" com profundidade, e a página Provedores mostra quantos ativos estão em cada nível.
