# Publicação

Site: <https://leocarvalhomagalhaes.github.io/fomo-ai-trading/>

## Modo atual: site no GitHub Pages, servidor no seu PC

O GitHub Pages só serve arquivos estáticos (HTML, JavaScript, imagens). Ele não roda Python, não fica coletando preços e não guarda banco de dados. Por isso o site fica no Pages e o servidor roda no seu computador.

| Peça | Onde |
| --- | --- |
| Interface (React) | GitHub Pages, workflow [`pages.yml`](../.github/workflows/pages.yml), compilada com `API_BASE_URL=http://127.0.0.1:8765` |
| Servidor e banco (FastAPI + SQLite) | Seu PC, aberto pelo `iniciar.bat` |

Como usar:

1. Rode o `iniciar.bat`. Ele sobe o servidor e abre o site do GitHub Pages no navegador.
2. Deixe a janela do `iniciar.bat` aberta. Sem ela, o site mostra "Servidor não encontrado neste computador" e reconecta sozinho quando o servidor volta.
3. Se o Chrome ou o Edge perguntar sobre **acesso à rede local**, permita. É o site do Pages pedindo para falar com o servidor em `127.0.0.1`.

Limites deste modo:

- Só funciona no computador onde o `iniciar.bat` está aberto. No celular ou em outro PC, o site abre mas não encontra o servidor.
- A coleta para quando o PC desliga ou a janela fecha.
- Os dados ficam só no seu PC (`data/fomo_ai.db`) e não há senha: o servidor só aceita conexões do próprio computador e só responde ao endereço local e ao site do GitHub Pages.
- O endereço local <http://127.0.0.1:8765> continua funcionando e mostra a mesma interface.

## Alternativa: servidor online (Render + Supabase)

Para usar de qualquer lugar, inclusive no celular, o servidor precisa rodar num serviço online. Tudo abaixo já está pronto no código, mas **não está em uso**. Para ativar, siga o passo a passo e troque a variável do repositório `API_BASE_URL` para o endereço do Render.

> Condições dos planos gratuitos consultadas em 31/10/2026. Elas mudam com frequência: confira as páginas oficiais.

A versão online tem três peças:

| Peça | Onde | Por quê |
| --- | --- | --- |
| Interface (React) | **GitHub Pages**, workflow [`pages.yml`](../.github/workflows/pages.yml) | O Pages só serve arquivos estáticos. |
| Servidor (FastAPI + coleta + análises) | **Render**, Web Service gratuito com Docker ([`Dockerfile`](../Dockerfile)) | Precisa ficar ligado para coletar preços a cada minuto. |
| Banco (Postgres) | **Supabase**, plano gratuito | Guarda carteira, recomendações e histórico entre reinícios do servidor. |



## Por que Supabase e não Neon

O app grava preços a cada minuto, então o banco nunca fica parado.

- **Neon Free:** 100 CU-horas por mês e suspensão após 5 min sem uso. Com o banco sempre ativo (0,25 CU), as horas acabam em cerca de 16 dias e o banco fica suspenso até o mês seguinte.
- **Supabase Free:** 500 MB e 5 GB de tráfego de saída por mês, sem limite de horas. Só pausa depois de 1 semana sem nenhuma atividade, o que não acontece com o servidor ligado.

## Limites e como o app se encaixa neles

| Limite | Valor | O que o app faz |
| --- | --- | --- |
| Render: horas gratuitas | 750 h/mês **por espaço de trabalho**, somadas entre todos os serviços gratuitos | Ligado o mês todo, o FOMO usa ~744 h. **Crie um espaço de trabalho só para ele**, senão os outros apps do mesmo espaço (DailyMusicBabuinos, FutebolBabuinico) esgotam as horas e tudo é suspenso no fim do mês. |
| Render: hibernação | Dorme após 15 min sem requisições; acorda em ~1 min | Um monitor externo chama `/api/ping` a cada 10 min (passo 5). Sem ele a coleta para quando ninguém está com o site aberto. |
| Render: disco | Apagado a cada reinício ou deploy | Tudo que importa fica no Supabase. Os arquivos de log e o último relatório de backtest se perdem num reinício (o backtest pode ser rodado de novo). |
| Supabase: espaço | 500 MB | Limpeza automática a cada hora: preços com mais de 48 h, candles com mais de 14 dias, eventos e notificações com mais de 30 dias. Ajustável em **Risco → Configurações** (`data.retention_*`). Avaliações, recomendações e operações nunca são apagadas. |
| Supabase: tráfego de saída | 5 GB/mês | Tokens recentes, os últimos 90 min de preços, os candles e os relatórios de segurança ficam na memória do servidor. O banco recebe todas as gravações, mas só é lido ao iniciar e para o que não está na memória. Medição abaixo. |
| Render: memória | 512 MB | ~250 MB com a memória cheia (90 min de preços de ~240 tokens ocupam ~76 MB). |

### Tráfego do banco medido

Medido em 31/10/2026 com ~240 tokens monitorados, contando os bytes que o Postgres enviou ao servidor (o que o Supabase cobra como tráfego de saída):

| Versão | Leitura do banco em ritmo normal | Projeção mensal |
| --- | --- | --- |
| Antes (tudo lido do banco) | 1,9 MB/min | ~82 GB |
| Só os preços na memória | 0,78 MB/min | ~34 GB |
| Preços, tokens, candles e segurança na memória (atual) | ~22 KB/min, com o painel aberto | ~1 GB |

Cada reinício do servidor lê de uma vez a última janela (~4 MB). Reinícios acontecem a cada deploy e, de vez em quando, por manutenção do Render.

A medição também revelou um erro que só acontecia no Postgres: o GeckoTerminal às vezes repete o horário de um candle, e o Postgres recusava o lote inteiro. Agora o último candle de cada horário é o que fica.

## Segurança

- O site pede uma **senha** (`FOMOAI_PASSWORD` no Render). O navegador guarda só um token derivado dela; trocar a senha desconecta todos.
- São no máximo 5 tentativas erradas por minuto por endereço.
- Sem senha, o servidor se recusa a iniciar em produção (`FOMOAI_ENV=production`).
- O servidor só aceita chamadas do próprio site no GitHub Pages (`FOMOAI_CORS_ORIGINS`).
- Continua sem nenhuma integração com a FOMO: nada de credenciais, sessões ou ordens.

## Passo a passo

### 1. Banco no Supabase

1. Entre em <https://supabase.com> com a conta do GitHub e crie um projeto (**New project**), plano Free.
   - Região: **East US (Ohio)**, a mesma do servidor no Render.
   - Anote a senha do banco.
2. Em **Connect**, copie a connection string do **Session pooler** (porta 5432, usuário `postgres.<id-do-projeto>`).
   - Não use a conexão direta (`db.<id>.supabase.co`): ela só funciona por IPv6, que o Render não usa.
3. Troque `[YOUR-PASSWORD]` pela senha do banco. As tabelas são criadas pelo app na primeira inicialização.

### 2. Servidor no Render

1. Em <https://dashboard.render.com>, crie um espaço de trabalho novo (menu do espaço de trabalho → **New workspace**), por exemplo `fomo-ai`.
2. **New → Web Service** → repositório `fomo-ai-trading`, branch `main`.
   - Language **Docker**, Root Directory vazio (o `Dockerfile` está na raiz).
   - Region **Ohio**, Instance Type **Free**.
   - Health Check Path `/api/health`.
3. Variáveis de ambiente:

| Variável | Valor |
| --- | --- |
| `FOMOAI_ENV` | `production` |
| `FOMOAI_PASSWORD` | a senha que você vai digitar no site (longa, só sua) |
| `FOMOAI_DB_URL` | connection string do Supabase (passo 1) |
| `FOMOAI_CORS_ORIGINS` | `https://leocarvalhomagalhaes.github.io` |
| `FOMOAI_COINGECKO_DEMO_KEY` | opcional: chave Demo gratuita da CoinGecko (com ela, `FOMOAI_GECKO_RPM=25`) |

4. Depois do deploy, confira `https://<serviço>.onrender.com/api/health` → `{"status":"ok","database":"ok"}`.

### 3. Site no GitHub Pages

```bash
gh variable set API_BASE_URL --body https://<serviço>.onrender.com
gh workflow run pages.yml
```

O Pages já está configurado para publicar pelo GitHub Actions.

### 4. Primeiro acesso

Abra o site, digite a senha e confira se aparece **● ao vivo** no topo. A primeira análise completa sai alguns minutos depois de o servidor iniciar.

### 5. Manter o servidor acordado

Crie um monitor gratuito que chame o servidor a cada 10 min, por exemplo no UptimeRobot:

- <https://uptimerobot.com> → **New monitor** → HTTP(s).
- URL `https://<serviço>.onrender.com/api/ping`, intervalo de 10 min.

Use `/api/ping`, que não consulta o banco. Sem o monitor, a coleta para 15 min depois que você fecha o site.

## Uso local continua igual

Sem `FOMOAI_DB_URL`, o app usa o SQLite em `data/`. Sem `FOMOAI_PASSWORD`, não pede senha. Os bancos local e online são independentes.

## Fontes

- [Render: Deploy for Free](https://render.com/docs/free)
- [Neon: limites do plano Free](https://neon.com/faqs/free-plan-limits-and-quotas)
- [Supabase: preços](https://supabase.com/pricing)
