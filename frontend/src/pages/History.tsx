import { useState } from "react";
import { Json } from "../api";
import { Badge, Card, CATEGORY_LABEL, DataTable, ErrorBox, Loading, STATUS_LABEL, toneForStatus } from "../components/ui";
import { formatDateTime, formatPrice, formatUsd } from "../format";
import { useApi } from "../live";

export default function History() {
  const [ledger, setLedger] = useState("");
  const { data, error, loading } = useApi<Json[]>(`/trades${ledger ? `?ledger=${ledger}` : ""}`, 30000, ["portfolio"]);
  return (
    <Card title="Histórico de operações" right={
      <select className="input !w-auto normal-case" value={ledger} onChange={(e) => setLedger(e.target.value)}>
        <option value="">Simulação e real</option><option value="SIM">Somente simulação</option><option value="REAL">Somente real</option>
      </select>}>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : (
        <DataTable rows={data ?? []} filterText={(t: Json) => `${t.token.symbol} ${t.strategy ?? ""} ${t.ledger} ${t.close_reason ?? ""}`}
          initialSort={{ key: "exec", desc: true }}
          columns={[
            { key: "ledger", label: "Livro", render: (t: Json) => <Badge tone={t.ledger === "REAL" ? "warn" : "info"}>{t.ledger}</Badge> },
            { key: "token", label: "Ativo", render: (t: Json) => <span>{t.token.symbol} <span className="text-xs text-mute">{t.token.chain_label}</span></span>, sort: (t: Json) => t.token.symbol },
            { key: "cat", label: "Tipo", render: (t: Json) => <span className="text-xs">{CATEGORY_LABEL[t.category] ?? "—"}</span> },
            { key: "strategy", label: "Estratégia", render: (t: Json) => <span className="text-xs">{t.strategy ?? "manual"}</span> },
            { key: "exec", label: "Execução", render: (t: Json) => <span className="text-xs">{formatDateTime(t.executed_at)}</span>, sort: (t: Json) => t.executed_at },
            { key: "amount", label: "Valor", render: (t: Json) => <span className="num">{formatUsd(t.amount_usd)}</span> },
            { key: "entry", label: "Entrada", render: (t: Json) => <span className="num text-xs">{formatPrice(t.entry_price)}</span> },
            { key: "exit", label: "Saída", render: (t: Json) => <span className="num text-xs">{formatPrice(t.exit_price)}</span> },
            { key: "closed", label: "Encerramento", render: (t: Json) => <span className="text-xs">{formatDateTime(t.closed_at)}</span> },
            { key: "reason", label: "Motivo", render: (t: Json) => t.close_reason ? <Badge tone={toneForStatus(t.close_reason)}>{STATUS_LABEL[t.close_reason] ?? t.close_reason}</Badge> : <Badge tone="info">aberta</Badge> },
            { key: "fees", label: "Taxas", render: (t: Json) => <span className="num text-xs">{formatUsd((t.entry_fee_usd ?? 0) + (t.exit_fee_usd ?? 0))}</span> },
            { key: "pnl", label: "Resultado", render: (t: Json) => <span className={`num ${(t.pnl_usd ?? 0) >= 0 ? "text-up" : "text-down"}`}>{formatUsd(t.pnl_usd)}</span>, sort: (t: Json) => t.pnl_usd },
          ]} />
      )}
    </Card>
  );
}
