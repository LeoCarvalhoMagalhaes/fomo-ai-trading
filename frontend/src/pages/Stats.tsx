import { useState } from "react";
import { api, Json } from "../api";
import { Card, Empty, ErrorBox, Loading, Stat } from "../components/ui";
import { formatNumber, formatPct, formatUsd } from "../format";
import { useApi } from "../live";

function pf(v: number | null) {
  if (v === null || v === undefined) return "—";
  return Number.isFinite(v) ? formatNumber(v, 2) : "∞";
}

function MetricsBlock({ m, title }: { m: Json; title: string }) {
  if (!m || m.n === 0) return <Card title={title}><Empty>Sem operações encerradas.</Empty></Card>;
  return (
    <Card title={title}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Operações" value={m.n} />
        <Stat label="Taxa de acerto" value={formatPct(m.win_rate * 100).replace("+", "")} />
        <Stat label="Expectativa" value={formatUsd(m.expectancy_usd)} tone={m.expectancy_usd >= 0 ? "up" : "down"} hint="média por operação" />
        <Stat label="Profit factor" value={pf(m.profit_factor)} />
        <Stat label="Retorno médio" value={formatPct(m.avg_return_pct)} />
        <Stat label="Resultado" value={formatUsd(m.pnl_usd)} tone={m.pnl_usd >= 0 ? "up" : "down"} />
        <Stat label="Drawdown máx." value={formatUsd(m.max_drawdown_usd)} tone="down" />
        <Stat label="Sequências" value={`${m.best_streak}+ / ${m.worst_streak}−`} />
      </div>
      {(["by_strategy", "by_category"] as const).map((k) => (
        <table key={k} className="data mt-4">
          <thead><tr><th>{k === "by_strategy" ? "Estratégia" : "Categoria"}</th><th>N</th><th>Acerto</th><th>Expectativa</th><th>Profit factor</th><th>Resultado</th></tr></thead>
          <tbody>{Object.entries(m[k] as Record<string, Json>).map(([g, x]) => (
            <tr key={g}><td>{g}</td><td className="num">{x.n}</td><td className="num">{formatPct(x.win_rate * 100).replace("+", "")}</td>
              <td className="num">{formatUsd(x.expectancy_usd)}</td><td className="num">{pf(x.profit_factor)}</td><td className="num">{formatUsd(x.pnl_usd)}</td></tr>
          ))}</tbody>
        </table>
      ))}
    </Card>
  );
}

export default function Stats() {
  const { data, error, loading, reload } = useApi<Json>("/stats", 60000, ["portfolio"]);
  const [running, setRunning] = useState(false);
  const run = async () => {
    setRunning(true);
    try {
      await api.post("/backtest/run");
      reload();
    } finally {
      setRunning(false);
    }
  };
  if (loading && !data) return <Loading />;
  if (!data) return <ErrorBox error={error} />;
  const bt = data.backtest?.backtest;
  const f = data.filtros;
  return (
    <div className="space-y-4">
      <p className="text-xs text-mute">A taxa de acerto sozinha não mede qualidade. Observe a expectativa (resultado médio por operação, já com custos) e o profit factor.</p>
      <MetricsBlock m={data.SIM} title="Desempenho — simulação" />
      <MetricsBlock m={data.REAL} title="Desempenho — operações reais informadas" />
      <Card title="Eficácia dos filtros (resultado 60 min após cada avaliação)">
        <table className="data">
          <thead><tr><th>Decisão</th><th>N</th><th>Retorno médio 60 min</th><th>Alvo 1</th><th>Stop</th><th>Tempo</th></tr></thead>
          <tbody>{(["recomendada", "rejeitada"] as const).map((k) => (
            <tr key={k}><td className="capitalize">{k}s</td><td className="num">{f[k].n}</td><td className="num">{formatPct(f[k].retorno_medio_60min_pct)}</td>
              <td className="num">{f[k].alvo1}</td><td className="num">{f[k].stop}</td><td className="num">{f[k].tempo}</td></tr>
          ))}</tbody>
        </table>
        <p className="text-sm mt-3">Calibração estatística: {f.calibracao.status === "ok" ? `modelo calibrado (Brier no teste ${f.calibracao.brier_teste.toFixed(3)}, ${f.calibracao.amostras_teste} amostras)` : f.calibracao.mensagem}</p>
      </Card>
      <Card title="Backtest (candles gravados, divisão temporal 60/20/20)" right={<button className="btn normal-case" disabled={running} onClick={run}>{running ? "Rodando…" : "Rodar backtest"}</button>}>
        {!bt ? <Empty>Nenhum backtest executado ainda.</Empty> : bt.status !== "ok" ? <Empty>{bt.mensagem}</Empty> : (
          <>
            <div className="text-xs text-mute mb-2">{bt.ativos} ativos · {bt.operacoes} operações · gerado em {new Date(bt.gerado_em).toLocaleString("pt-BR")}</div>
            <table className="data">
              <thead><tr><th>Conjunto</th><th>N</th><th>Acerto</th><th>Expectativa (US$ 10)</th><th>Profit factor</th><th>Drawdown</th></tr></thead>
              <tbody>{(["treino", "validacao", "teste", "total"] as const).map((k) => {
                const m = bt.resultado[k];
                return <tr key={k}><td className="capitalize">{k}</td><td className="num">{m.n}</td><td className="num">{m.win_rate === null ? "—" : formatPct(m.win_rate * 100).replace("+", "")}</td>
                  <td className="num">{formatUsd(m.expectancy_usd)}</td><td className="num">{pf(m.profit_factor)}</td><td className="num">{formatUsd(m.max_drawdown_usd)}</td></tr>;
              })}</tbody>
            </table>
            <ul className="list-disc pl-5 text-xs text-mute mt-3">{bt.limitacoes.map((l: string) => <li key={l}>{l}</li>)}</ul>
          </>
        )}
      </Card>
      <Card title="Estratégias">
        <div className="grid md:grid-cols-2 gap-4">
          {data.estrategias.map((s: Json) => (
            <div key={s.id} className="border border-line rounded p-3 text-sm">
              <div className="font-medium">{s.nome}</div>
              <div className="mt-1"><span className="text-mute">Entrada: </span>{s.entrada}</div>
              <div><span className="text-mute">Invalidação: </span>{s.invalidacao}</div>
              <div><span className="text-mute">Saída: </span>{s.saida}</div>
              <div><span className="text-mute">Horizonte: </span>{s.horizonte} · <span className="text-mute">Indicadores: </span>{s.indicadores}</div>
              <div className="text-warn/90"><span className="text-mute">Limitações: </span>{s.limitacoes}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
