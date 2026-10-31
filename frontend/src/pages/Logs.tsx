import { useState } from "react";
import { api, Json } from "../api";
import { Badge, Card, DataTable, ErrorBox, Loading } from "../components/ui";
import { formatDateTime } from "../format";
import { useApi } from "../live";

export default function Logs() {
  const [level, setLevel] = useState("");
  const { data, error, loading } = useApi<Json>(`/logs?limit=300${level ? `&level=${level}` : ""}`, 15000, ["cycle"]);
  const notes = useApi<Json[]>("/notifications?limit=100", 15000, ["notification"]);
  const scan = async () => {
    await api.post("/control/scan");
  };
  if (loading && !data) return <Loading />;
  if (!data) return <ErrorBox error={error} />;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-sm">
        <span>Estado do motor: <Badge tone={data.engine_state === "OPERANDO" ? "up" : data.engine_state === "BLOQUEADO" ? "down" : "warn"}>{data.engine_state}</Badge></span>
        <span>Erros nas tarefas periódicas: <span className="num">{data.scheduler_errors}</span></span>
        <div className="flex-1" />
        <button className="btn" onClick={scan}>Rodar varredura completa agora</button>
      </div>
      <Card title="Ciclos de análise">
        <DataTable rows={data.cycles} columns={[
          { key: "id", label: "#", render: (c: Json) => <span className="num text-xs">{c.id}</span> },
          { key: "k", label: "Tipo", render: (c: Json) => <Badge tone={c.kind === "full" ? "info" : "mute"}>{c.kind === "full" ? "completo" : "rápido"}</Badge> },
          { key: "tr", label: "Origem", render: (c: Json) => <span className="text-xs">{c.trigger}</span> },
          { key: "st", label: "Início", render: (c: Json) => <span className="text-xs">{formatDateTime(c.started_at)}</span> },
          { key: "d", label: "Duração", render: (c: Json) => <span className="num text-xs">{c.finished_at ? `${((new Date(c.finished_at).getTime() - new Date(c.started_at).getTime()) / 1000).toFixed(1)} s` : "em andamento"}</span> },
          { key: "a", label: "Analisados", render: (c: Json) => <span className="num">{c.analyzed}</span> },
          { key: "r", label: "Recomendações", render: (c: Json) => <span className="num">{c.recommendations}</span> },
          { key: "m", label: "Resultado", className: "text-xs text-mute", render: (c: Json) => c.message },
        ]} />
      </Card>
      <Card title="Eventos do sistema" right={
        <select className="input !w-auto normal-case" value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="">Todos</option><option value="info">info</option><option value="warn">avisos</option><option value="error">erros</option>
        </select>}>
        <DataTable rows={data.events} filterText={(e: Json) => `${e.kind} ${e.message}`} columns={[
          { key: "t", label: "Horário", render: (e: Json) => <span className="text-xs">{formatDateTime(e.created_at)}</span> },
          { key: "l", label: "Nível", render: (e: Json) => <Badge tone={e.level === "error" ? "down" : e.level === "warn" ? "warn" : "mute"}>{e.level}</Badge> },
          { key: "k", label: "Tipo", render: (e: Json) => <span className="text-xs">{e.kind}</span> },
          { key: "m", label: "Mensagem", className: "text-xs", render: (e: Json) => e.message },
        ]} />
      </Card>
      <Card title="Notificações" right={<button className="btn normal-case" onClick={async () => { await api.post("/notifications/read"); notes.reload(); }}>Marcar como lidas</button>}>
        <DataTable rows={notes.data ?? []} columns={[
          { key: "t", label: "Horário", render: (n: Json) => <span className="text-xs">{formatDateTime(n.created_at)}</span> },
          { key: "s", label: "Gravidade", render: (n: Json) => <Badge tone={n.severity === "critica" ? "down" : n.severity === "alta" ? "warn" : "mute"}>{n.severity}</Badge> },
          { key: "ti", label: "Título", render: (n: Json) => <span className={n.read ? "text-mute" : ""}>{n.title}</span> },
          { key: "b", label: "Detalhe", className: "text-xs text-mute", render: (n: Json) => n.body },
        ]} />
      </Card>
    </div>
  );
}
