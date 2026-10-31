import { useState } from "react";
import { Json } from "../api";
import { RecommendationCard } from "../components/RecommendationCard";
import { Card, Empty, ErrorBox, Loading } from "../components/ui";
import { useApi } from "../live";

export default function Recommendations() {
  const active = useApi<Json[]>("/recommendations?status=ATIVA", 15000, ["recommendation", "cycle"]);
  const [status, setStatus] = useState("");
  const history = useApi<Json[]>(`/recommendations?limit=100${status ? `&status=${status}` : ""}`, 30000, ["recommendation"]);
  const reload = () => {
    active.reload();
    history.reload();
  };
  return (
    <div className="space-y-4">
      <Card title="Recomendações ativas">
        <ErrorBox error={active.error} />
        {active.loading && !active.data ? <Loading /> : active.data?.length ? (
          <div className="space-y-3">{active.data.map((r) => <RecommendationCard key={r.id} rec={r} onChange={reload} />)}</div>
        ) : (
          <Empty>SEM OPERAÇÃO RECOMENDADA — aguardando condições melhores.</Empty>
        )}
        <p className="text-xs text-mute mt-3">Receber uma recomendação não significa que você executou. Só clique em "Executei na FOMO" depois de executar, informando o preço e o valor reais.</p>
      </Card>
      <Card title="Histórico de recomendações" right={
        <select className="input !w-auto normal-case" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Todas</option><option value="EXECUTADA">Executadas</option><option value="IGNORADA">Ignoradas</option><option value="EXPIRADA">Expiradas</option>
        </select>}>
        {history.data?.filter((r) => r.status !== "ATIVA").length ? (
          <div className="space-y-3">{history.data.filter((r) => r.status !== "ATIVA").map((r) => <RecommendationCard key={r.id} rec={r} onChange={reload} compact />)}</div>
        ) : <Empty>Nenhuma recomendação encerrada ainda.</Empty>}
      </Card>
    </div>
  );
}
