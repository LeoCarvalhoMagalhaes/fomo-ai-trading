import { useState } from "react";
import { Link } from "react-router-dom";
import { Json } from "../api";
import { Badge, Card, CATEGORY_LABEL, DataTable, ErrorBox, Loading, ScoreBar, STATUS_LABEL, toneForStatus } from "../components/ui";
import { formatDateTime, formatPct, formatPrice } from "../format";
import { useApi } from "../live";

export default function Opportunities() {
  const [hours, setHours] = useState(6);
  const [decision, setDecision] = useState("");
  const { data, error, loading } = useApi<Json[]>(`/opportunities?hours=${hours}${decision ? `&decision=${decision}` : ""}`, 30000, ["cycle"]);
  return (
    <Card title="Oportunidades identificadas e rejeitadas"
          right={
            <span className="flex gap-2 normal-case">
              <select className="input !w-auto" value={decision} onChange={(e) => setDecision(e.target.value)}>
                <option value="">Todas as decisões</option><option value="RECOMENDADA">Recomendadas</option><option value="REJEITADA">Rejeitadas</option>
              </select>
              <select className="input !w-auto" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
                {[1, 6, 24, 72].map((h) => <option key={h} value={h}>Últimas {h} h</option>)}
              </select>
            </span>
          }>
      <ErrorBox error={error} />
      <p className="text-xs text-mute mb-3">Toda avaliação fica registrada, inclusive as rejeitadas, com o resultado observado 60 min depois — é assim que se mede se os filtros funcionam.</p>
      {loading && !data ? <Loading /> : (
        <DataTable
          rows={data ?? []}
          filterText={(e: Json) => `${e.token.symbol} ${e.token.chain} ${e.strategy ?? ""} ${(e.reasons ?? []).join(" ")}`}
          initialSort={{ key: "when", desc: true }}
          columns={[
            { key: "when", label: "Horário", render: (e: Json) => <span className="text-xs">{formatDateTime(e.created_at)}</span>, sort: (e: Json) => e.created_at },
            { key: "token", label: "Ativo", render: (e: Json) => <Link className="hover:text-info" to={`/ativo/${e.token_id}`}>{e.token.symbol} <span className="text-xs text-mute">{e.token.chain_label}</span></Link>, sort: (e: Json) => e.token.symbol },
            { key: "cat", label: "Tipo", render: (e: Json) => <span className="text-xs">{CATEGORY_LABEL[e.category] ?? e.category}</span> },
            { key: "strategy", label: "Estratégia", render: (e: Json) => <span className="text-xs">{e.strategy ?? "—"}</span> },
            { key: "score", label: "Pontuação", render: (e: Json) => <ScoreBar score={e.score} />, sort: (e: Json) => e.score },
            { key: "price", label: "Preço", render: (e: Json) => <span className="num text-xs">{formatPrice(e.price)}</span> },
            { key: "decision", label: "Decisão", render: (e: Json) => <Badge tone={toneForStatus(e.decision)}>{STATUS_LABEL[e.decision] ?? e.decision}</Badge>, sort: (e: Json) => e.decision },
            { key: "reasons", label: "Motivos", className: "text-xs text-mute max-w-[380px]", render: (e: Json) => (e.reasons ?? []).join("; ") },
            { key: "outcome", label: "60 min depois", render: (e: Json) => e.outcome_hit ? <span className="text-xs"><Badge tone={toneForStatus(e.outcome_hit)}>{STATUS_LABEL[e.outcome_hit] ?? e.outcome_hit}</Badge> <span className="num">{formatPct(e.outcome_return_pct)}</span></span> : <span className="text-xs text-mute">aguardando</span> },
          ]}
        />
      )}
    </Card>
  );
}
