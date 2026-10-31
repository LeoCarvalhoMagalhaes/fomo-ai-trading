import { Link } from "react-router-dom";
import { Json } from "../api";
import { Badge, Card, DataTable, ErrorBox, Loading, toneForStatus } from "../components/ui";
import { formatAge, formatNumber, formatPct, formatPrice, formatUsd, shortAddress } from "../format";
import { useApi } from "../live";

const CLASS_TEXT: Record<string, string> = { A: "Oportunidade potencialmente interessante", B: "Acompanhamento, aguardando confirmação", C: "Risco elevado, evitar" };

export default function NewTokens() {
  const { data, error, loading } = useApi<Json[]>("/new-tokens", 30000, ["cycle"]);
  return (
    <div className="space-y-4">
      <div className="grid sm:grid-cols-3 gap-3">
        {(["A", "B", "C"] as const).map((c) => (
          <div key={c} className="card px-4 py-3">
            <Badge tone={toneForStatus(c)}>Classe {c}</Badge>
            <div className="num text-xl mt-1">{(data ?? []).filter((t) => t.classification === c).length}</div>
            <div className="text-xs text-mute">{CLASS_TEXT[c]}</div>
          </div>
        ))}
      </div>
      <Card title="Tokens criados nas últimas 72 h">
        <ErrorBox error={error} />
        <p className="text-xs text-mute mb-3">
          Token novo não é sinônimo de oportunidade. Qualquer sinal crítico (honeypot, venda bloqueada, congelamento, mint ativo, concentração acima de 60%, queda de liquidez) leva à classe C.
          A falta de dados de segurança impede a classe A. Valor máximo em tokens novos: US$ 5.
        </p>
        {loading && !data ? <Loading /> : (
          <DataTable
            rows={data ?? []}
            filterText={(t: Json) => `${t.symbol} ${t.name} ${t.chain} ${t.address}`}
            initialSort={{ key: "age", desc: false }}
            columns={[
              { key: "token", label: "Token", render: (t: Json) => <Link className="hover:text-info" to={`/ativo/${t.id}`}>{t.symbol} <span className="text-xs text-mute">{t.chain_label}</span></Link>, sort: (t: Json) => t.symbol },
              { key: "addr", label: "Contrato", render: (t: Json) => <span className="num text-xs" title={t.address}>{shortAddress(t.address)}</span> },
              { key: "age", label: "Idade", render: (t: Json) => formatAge(t.pair_created_at), sort: (t: Json) => -new Date(t.pair_created_at ?? 0).getTime() },
              { key: "price", label: "Preço", render: (t: Json) => <span className="num text-xs">{formatPrice(t.snapshot?.price_usd)}</span> },
              { key: "liq", label: "Liquidez", render: (t: Json) => <span className="num text-xs">{formatUsd(t.snapshot?.liquidity_usd)}</span>, sort: (t: Json) => t.snapshot?.liquidity_usd ?? null },
              { key: "ch", label: "1 h", render: (t: Json) => <span className="num text-xs">{formatPct(t.snapshot?.price_change?.h1)}</span>, sort: (t: Json) => t.snapshot?.price_change?.h1 ?? null },
              { key: "flow", label: "Compras/vendas 5 min", render: (t: Json) => <span className="num text-xs">{formatNumber(t.snapshot?.buys?.m5)} / {formatNumber(t.snapshot?.sells?.m5)}</span> },
              { key: "class", label: "Classe", render: (t: Json) => t.classification ? <Badge tone={toneForStatus(t.classification)}>{t.classification}</Badge> : <span className="text-xs text-mute">não avaliado</span>, sort: (t: Json) => t.classification ?? "Z" },
              { key: "why", label: "Motivos", className: "text-xs text-mute max-w-[360px]", render: (t: Json) => (t.class_reasons ?? []).join("; ") },
            ]}
          />
        )}
      </Card>
    </div>
  );
}
