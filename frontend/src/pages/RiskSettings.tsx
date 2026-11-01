import { useEffect, useState } from "react";
import { api, Json } from "../api";
import { Card, ErrorBox, Loading } from "../components/ui";
import { formatDateTime, parseDecimal } from "../format";
import { useApi } from "../live";

const GROUPS: [string, [string, string, string?][]][] = [
  ["Modo de operação", [["mode", "Livro usado pelo Risk Manager (SIM ou REAL)"]]],
  ["Capital e valores", [
    ["risk.capital_usd", "Capital de referência (US$)"],
    ["risk.established_min_usd", "Mínimo por operação — estabelecidos (US$)"],
    ["risk.established_max_usd", "Máximo por operação — estabelecidos (US$)"],
    ["risk.new_min_usd", "Mínimo por operação — novos (US$)"],
    ["risk.new_max_usd", "Máximo por operação — novos (US$)"],
  ]],
  ["Exposição e perdas", [
    ["risk.max_exposure_usd", "Exposição máxima simultânea (US$)"],
    ["risk.max_new_exposure_usd", "Exposição máxima em tokens novos (US$)"],
    ["risk.min_reserve_usd", "Reserva mínima de capital (US$)"],
    ["risk.max_daily_loss_usd", "Limite de perda diária (US$)"],
    ["risk.loss_streak_pause", "Perdas seguidas que pausam recomendações"],
    ["risk.loss_streak_pause_hours", "Duração da pausa (h)"],
    ["risk.dedupe_minutes", "Janela contra recomendações duplicadas (min)"],
    ["risk.max_impact_pct", "Impacto máximo de preço por lado (%)"],
  ]],
  ["Critérios de recomendação", [
    ["rec.min_score", "Pontuação mínima (0–100)"],
    ["rec.min_net_rr", "R:R líquido mínimo"],
    ["rec.min_target_cost_multiple", "Alvo e stop mínimos em múltiplos do custo"],
    ["rec.ttl_minutes", "Validade da recomendação (min)"],
    ["rec.max_entry_run_pct", "Alta máxima após a recomendação antes de expirar (%)"],
    ["rec.horizon_minutes", "Horizonte da operação (min)"],
  ]],
  ["Custos (confira na tela de confirmação da FOMO)", [
    ["cost.fomo_fee_pct", "Taxa da FOMO por lado (%)"],
    ["cost.fomo_min_fee_usd", "Taxa mínima da FOMO por ordem (US$)"],
    ["cost.pool_fee_pct", "Taxa do pool por lado (%)"],
    ["cost.base_slippage_pct", "Slippage base por lado (%)"],
    ["cost.gas_usd.solana", "Gás Solana (US$)"], ["cost.gas_usd.base", "Gás Base (US$)"], ["cost.gas_usd.bsc", "Gás BNB Chain (US$)"],
    ["cost.gas_usd.ethereum", "Gás Ethereum (US$)"], ["cost.gas_usd.monad", "Gás Monad (US$)"], ["cost.gas_usd.robinhood", "Gás Robinhood Chain (US$)"],
  ]],
  ["Dados e filtros de mercado", [
    ["data.max_price_age_s", "Idade máxima do preço (s)"],
    ["data.tier2_max_assets", "Ativos no nível 2 (análise profunda)"],
    ["market.min_liquidity_established", "Liquidez mínima — estabelecidos (US$)"],
    ["market.min_liquidity_new", "Liquidez mínima — novos (US$)"],
  ]],
  ["Pesos da pontuação", [
    ["score.weight.momentum", "Momentum"], ["score.weight.volume", "Volume"], ["score.weight.liquidez", "Liquidez"],
    ["score.weight.estrutura_tecnica", "Estrutura técnica"], ["score.weight.confirmacao_tendencia", "Confirmação de tendência"],
    ["score.weight.qualidade_dados", "Qualidade dos dados"], ["score.weight.seguranca_contrato", "Segurança do contrato"],
    ["score.weight.risco_manipulacao", "Risco de manipulação"], ["score.weight.risco_retorno", "Relação risco/retorno"],
    ["score.weight.condicoes_mercado", "Condições de mercado"],
  ]],
  ["Notificações", [["notify.windows_toast", "Notificações do Windows"], ["notify.dedupe_minutes", "Silêncio entre avisos iguais (min)"]]],
];

export default function RiskSettings() {
  const { data, error, loading, reload } = useApi<Json>("/settings", 0);
  const audit = useApi<Json[]>("/audit", 0);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    if (data) setValues(data.values);
  }, [data]);
  if (loading && !data) return <Loading />;
  if (!data) return <ErrorBox error={error} />;
  const changes = Object.fromEntries(Object.entries(values).filter(([k, v]) => v !== data.values[k]));
  const save = async () => {
    try {
      await api.put("/settings", { changes });
      setMsg({ ok: true, text: `${Object.keys(changes).length} configuração(ões) salvas e auditadas.` });
      reload();
      audit.reload();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
  };
  const input = (key: string) => {
    const def = data.defaults[key];
    const v = values[key];
    if (typeof def === "boolean") return <input type="checkbox" checked={Boolean(v)} onChange={(e) => setValues({ ...values, [key]: e.target.checked })} />;
    if (key === "mode") return (
      <select className="input !w-32" value={String(v)} onChange={(e) => setValues({ ...values, mode: e.target.value })}>
        <option value="SIM">SIM</option><option value="REAL">REAL</option>
      </select>
    );
    return <input className="input num !w-32 text-right" value={String(v ?? "")}
                  onChange={(e) => setValues({ ...values, [key]: parseDecimal(e.target.value) ?? e.target.value })} />;
  };
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button className="btn-primary" disabled={!Object.keys(changes).length} onClick={save}>Salvar {Object.keys(changes).length || ""} alteração(ões)</button>
        <button className="btn" onClick={() => setValues(data.values)}>Descartar</button>
        {msg && <span className={`text-sm ${msg.ok ? "text-up" : "text-down"}`}>{msg.text}</span>}
      </div>
      <p className="text-xs text-mute">O Risk Manager aplica estes limites a toda recomendação; nenhuma pontuação os contorna. Alterações inválidas são recusadas e todas as válidas ficam na auditoria.</p>
      <div className="grid lg:grid-cols-2 gap-4">
        {GROUPS.map(([title, fields]) => (
          <Card key={title} title={title}>
            {fields.map(([key, label]) => (
              <div key={key} className="flex items-center justify-between gap-3 py-1.5 border-b border-line/50 last:border-0">
                <span className="text-sm">{label}{values[key] !== data.values[key] && <span className="text-warn"> •</span>}</span>
                {input(key)}
              </div>
            ))}
          </Card>
        ))}
      </div>
      <Card title="Auditoria de alterações">
        <table className="data">
          <thead><tr><th>Horário</th><th>Configuração</th><th>De</th><th>Para</th><th>Autor</th></tr></thead>
          <tbody>{(audit.data ?? []).map((a) => (
            <tr key={a.id}><td className="text-xs">{formatDateTime(a.at)}</td><td className="text-xs">{a.key}</td>
              <td className="num text-xs">{JSON.stringify(a.old_value)}</td><td className="num text-xs">{JSON.stringify(a.new_value)}</td><td className="text-xs">{a.actor}</td></tr>
          ))}</tbody>
        </table>
      </Card>
    </div>
  );
}
