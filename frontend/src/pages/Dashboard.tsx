import { Link } from "react-router-dom";
import { Json } from "../api";
import { RecommendationCard } from "../components/RecommendationCard";
import { Badge, Card, CATEGORY_LABEL, Empty, Loading, ScoreBar, Stat, STATUS_LABEL, toneForStatus } from "../components/ui";
import { formatAge, formatDateTime, formatIn, formatPct, formatPrice, formatUsd } from "../format";

export default function Dashboard({ dash, reload }: { dash: Json | null; reload: () => void }) {
  if (!dash) return <Loading />;
  const book = dash.books[dash.mode];
  const sim = dash.books.SIM;
  return (
    <div className="space-y-4">
      {dash.mode === "REAL" && !dash.observation.complete && (
        <div className="card border-warn/60 text-warn text-sm px-4 py-2">{dash.observation.message}</div>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        <Stat label="Capital de referência" value={formatUsd(dash.capital)} hint={`Livro ${dash.mode}`} />
        <Stat label="Saldo disponível" value={formatUsd(book.available)} hint={`Livre acima da reserva: ${formatUsd(book.free_for_trading)}`} />
        <Stat label="Posições abertas" value={book.positions.length} hint={`Exposição ${formatUsd(book.exposure)}`} />
        <Stat label="P&L realizado" value={formatUsd(book.realized_pnl)} tone={book.realized_pnl >= 0 ? "up" : "down"} hint={`Hoje: ${formatUsd(book.day_realized_pnl)}`} />
        <Stat label="Mercado (1 h)" value={dash.market_regime.label} tone={dash.market_regime.label === "alta" ? "up" : dash.market_regime.label === "baixa" ? "down" : undefined}
              hint={`${(dash.market_regime.up_fraction * 100).toFixed(0)}% da liquidez em alta`} />
        <Stat label="Próxima varredura completa" value={dash.next_full_at ? formatIn(dash.next_full_at) : "—"}
              hint={dash.last_cycle ? `Última: ${formatDateTime(dash.last_cycle.finished_at)}` : "Aguardando primeiro ciclo"} />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <Card title="Melhor oportunidade identificada">
            {dash.best_opportunity ? (
              <RecommendationCard rec={dash.best_opportunity} onChange={reload} compact />
            ) : (
              <div className="py-6 text-center">
                <div className="text-lg font-semibold">{dash.message}</div>
                <div className="text-xs text-mute mt-1">
                  {dash.last_cycle ? `${dash.last_cycle.analyzed} ativos analisados no último ciclo · ${dash.tiers.nivel1} no nível 1 · ${dash.tiers.nivel2} no nível 2` : "O primeiro ciclo completo pode levar alguns minutos (limite de 10 chamadas/min do GeckoTerminal)."}
                </div>
              </div>
            )}
          </Card>
          <Card title="Pontuação das melhores oportunidades (2 h)" right={<Link className="text-info normal-case" to="/oportunidades">ver todas</Link>}>
            {dash.top_scores.length === 0 ? <Empty>Nenhuma oportunidade pontuada ainda.</Empty> : (
              <table className="data">
                <thead><tr><th>Ativo</th><th>Estratégia</th><th>Pontuação</th><th>Decisão</th><th>Motivo</th></tr></thead>
                <tbody>
                  {dash.top_scores.map((e: Json) => (
                    <tr key={e.id}>
                      <td><Link className="hover:text-info" to={`/ativo/${e.token_id}`}>{e.token.symbol}</Link> <span className="text-xs text-mute">{e.token.chain_label}</span></td>
                      <td className="text-xs">{e.strategy}</td>
                      <td><ScoreBar score={e.score} /></td>
                      <td><Badge tone={toneForStatus(e.decision)}>{STATUS_LABEL[e.decision] ?? e.decision}</Badge></td>
                      <td className="text-xs text-mute max-w-[320px]">{(e.reasons ?? [])[0]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
          <Card title="Posições abertas">
            {book.positions.length === 0 ? <Empty>Sem posições abertas no livro {dash.mode}.</Empty> : (
              <table className="data">
                <thead><tr><th>Ativo</th><th>Valor</th><th>Entrada</th><th>Atual</th><th>P&L estimado</th><th>Aberta há</th></tr></thead>
                <tbody>
                  {book.positions.map((p: Json) => (
                    <tr key={p.id}>
                      <td>{p.token.symbol}</td><td className="num">{formatUsd(p.amount_usd)}</td><td className="num">{formatPrice(p.entry_price)}</td>
                      <td className="num">{formatPrice(p.current_price)}</td>
                      <td className={`num ${p.unrealized_pnl_usd >= 0 ? "text-up" : "text-down"}`}>{formatUsd(p.unrealized_pnl_usd)}</td>
                      <td className="text-xs">{formatAge(p.executed_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
        <div className="space-y-4">
          <Card title="Alertas de risco">
            {dash.alerts.length === 0 ? <Empty>Nenhum alerta nas últimas 24 h.</Empty> : (
              <ul className="space-y-2">
                {dash.alerts.map((a: Json) => (
                  <li key={a.id} className={`border-l-2 pl-2 ${a.severity === "critica" ? "border-down" : "border-warn"}`}>
                    <div className="text-sm">{a.title}</div>
                    <div className="text-xs text-mute">{a.body} · há {formatAge(a.created_at)}</div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Novos tokens relevantes" right={<Link className="text-info normal-case" to="/novos-tokens">ver todos</Link>}>
            {dash.new_tokens.length === 0 ? <Empty>Nenhum token novo classe A ou B na última hora.</Empty> : (
              <ul className="space-y-2">
                {dash.new_tokens.map((t: Json) => (
                  <li key={t.id} className="flex items-center justify-between gap-2 text-sm">
                    <Link className="hover:text-info" to={`/ativo/${t.id}`}>{t.symbol} <span className="text-xs text-mute">{t.chain_label}</span></Link>
                    <span className="flex items-center gap-2">
                      <span className="num text-xs text-mute">{formatUsd(t.liquidity_usd)}</span>
                      <Badge tone={toneForStatus(t.classification)}>{t.classification}</Badge>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Status dos provedores" right={<Link className="text-info normal-case" to="/provedores">detalhes</Link>}>
            <ul className="space-y-1.5 text-sm">
              {dash.providers.map((p: Json) => (
                <li key={p.name} className="flex justify-between">
                  <span>{p.name}</span>
                  <span className={p.ok ? "text-up" : "text-down"}>{p.ok ? "OK" : `Falha: ${p.last_error}`} <span className="text-mute text-xs">· {p.calls_last_minute}/min</span></span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Custos com US$ 10 por operação">
            <table className="data">
              <thead><tr><th>Rede</th><th>Ida e volta</th><th>Alvo 1 mínimo</th></tr></thead>
              <tbody>
                {Object.entries(dash.round_trip_example as Record<string, number>).map(([chain, pct]) => (
                  <tr key={chain}><td>{chain}</td><td className="num">{formatPct(pct).replace("+", "")}</td>
                    <td className="num text-warn">{formatPct(dash.min_target_example[chain]).replace("+", "")}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="text-[11px] text-mute mt-2">
              Custos: taxa estimada da FOMO (com mínimo por ordem), pool, slippage e gás. "Alvo 1 mínimo" é a menor alta em 60 min
              que passa nas regras de risco com esses custos — por isso "sem operação" é o resultado mais comum com valores pequenos.
              Se a FOMO mostrar outra taxa na confirmação, ajuste em Risco.
            </p>
          </Card>
          <Card title="Simulação (livro SIM)">
            <div className="text-sm space-y-1">
              <div className="flex justify-between"><span>Operações encerradas</span><span className="num">{sim.metrics.n}</span></div>
              <div className="flex justify-between"><span>Resultado</span><span className={`num ${sim.realized_pnl >= 0 ? "text-up" : "text-down"}`}>{formatUsd(sim.realized_pnl)}</span></div>
              <div className="flex justify-between"><span>Período de observação</span><span className="num">{dash.observation.closed_sim_trades}/50 · {dash.observation.days}/14 d</span></div>
              <div className="text-xs text-mute">Categorias: {Object.keys(sim.metrics.by_category ?? {}).map((c) => CATEGORY_LABEL[c] ?? c).join(", ") || "—"}</div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
