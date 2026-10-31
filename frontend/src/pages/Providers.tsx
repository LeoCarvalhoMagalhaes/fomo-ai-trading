import { Json } from "../api";
import { Badge, Card, ErrorBox, Loading } from "../components/ui";
import { formatAge, formatDateTime } from "../format";
import { useApi } from "../live";

const INFO: Record<string, { uso: string; termos: string; url: string }> = {
  dexscreener: { uso: "Preço, liquidez, volume e compras/vendas em lote (nível 1)", termos: "API pública; uso pessoal; dados não repassados a terceiros", url: "https://docs.dexscreener.com/api/reference" },
  geckoterminal: { uso: "Descoberta (pools novos e em alta), candles de 5 min, holders e autoridades", termos: "API pública gratuita, ~10 chamadas/min; chave Demo opcional", url: "https://www.geckoterminal.com/dex-api" },
  goplus: { uso: "Segurança de contrato: honeypot, taxas, permissões, mint/freeze, holders", termos: "Plano gratuito com cota; Solana em beta", url: "https://docs.gopluslabs.io/" },
};

export default function Providers() {
  const { data, error, loading } = useApi<Json>("/providers", 10000);
  if (loading && !data) return <Loading />;
  if (!data) return <ErrorBox error={error} />;
  return (
    <div className="space-y-4">
      <div className="grid lg:grid-cols-3 gap-4">
        {data.providers.map((p: Json) => (
          <Card key={p.name} title={p.name} right={<Badge tone={p.ok ? "up" : "down"}>{p.ok ? "operando" : "com falha"}</Badge>}>
            <div className="text-sm space-y-1">
              <div className="flex justify-between"><span className="text-mute">Chamadas no último minuto</span><span className="num">{p.calls_last_minute} / {data.budgets[p.name]}</span></div>
              <div className="flex justify-between"><span className="text-mute">Último sucesso</span><span>{p.last_success ? `há ${formatAge(p.last_success)}` : "—"}</span></div>
              <div className="flex justify-between"><span className="text-mute">Falhas seguidas</span><span className="num">{p.consecutive_failures}</span></div>
              {p.last_error && <div className="text-down text-xs">Último erro: {p.last_error} ({formatDateTime(p.last_error_at)})</div>}
              {p.backoff_until && <div className="text-warn text-xs">Em espera até {formatDateTime(p.backoff_until)}</div>}
              <div className="text-xs text-mute pt-2">{INFO[p.name]?.uso}</div>
              <div className="text-xs text-mute">{INFO[p.name]?.termos} · <a className="text-info" href={INFO[p.name]?.url} target="_blank" rel="noreferrer">documentação</a></div>
            </div>
          </Card>
        ))}
      </div>
      <Card title="Cobertura e níveis de análise">
        <div className="text-sm space-y-1">
          <div>Nível 1 (monitoramento amplo): <span className="num">{data.tiers.nivel1}</span> ativos · Nível 2 (candles e segurança): <span className="num">{data.tiers.nivel2}</span> ativos</div>
          <div>Última descoberta: {formatDateTime(data.last_discovery)} · Última atualização do nível 1: {formatDateTime(data.last_tier1)}</div>
          <div>Chave Demo da CoinGecko: {data.demo_key_configured ? "configurada" : "não configurada (opcional, em .env)"} · Telegram: {data.telegram_configured ? "configurado" : "desligado"}</div>
        </div>
        <table className="data mt-3">
          <thead><tr><th>Rede</th><th>GeckoTerminal</th><th>DexScreener</th><th>GoPlus</th></tr></thead>
          <tbody>{data.chains.map((c: Json) => <tr key={c.id}><td>{c.label}</td><td className="num text-xs">{c.gecko}</td><td className="num text-xs">{c.dex}</td><td className="num text-xs">{c.goplus}</td></tr>)}</tbody>
        </table>
        <p className="text-xs text-mute mt-3">A FOMO não publica API e os termos dela proíbem bots e coleta automatizada; por isso o app não acessa a FOMO. O RugCheck foi avaliado e ficou de fora porque a API pública não gerou relatórios nos testes.</p>
      </Card>
    </div>
  );
}
