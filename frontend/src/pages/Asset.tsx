import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Json } from "../api";
import { PriceChart } from "../components/PriceChart";
import { Badge, Card, CATEGORY_LABEL, DataTable, Empty, ErrorBox, Loading, ScoreBar, STATUS_LABEL, toneForStatus } from "../components/ui";
import { formatAge, formatDateTime, formatNumber, formatPct, formatPrice, formatUsd } from "../format";
import { useApi } from "../live";

function Search() {
  const [q, setQ] = useState("");
  const { data } = useApi<Json[]>(`/tokens?q=${encodeURIComponent(q)}&limit=30`, 0);
  const nav = useNavigate();
  return (
    <Card title="Escolha um ativo">
      <input className="input max-w-sm mb-3" placeholder="Símbolo, nome ou endereço do contrato" value={q} onChange={(e) => setQ(e.target.value)} />
      <ul className="divide-y divide-line">
        {(data ?? []).map((t) => (
          <li key={t.id} className="py-2 flex justify-between cursor-pointer hover:text-info" onClick={() => nav(`/ativo/${t.id}`)}>
            <span>{t.symbol} <span className="text-xs text-mute">{t.name} · {t.chain_label}</span></span>
            <span className="text-xs text-mute">{CATEGORY_LABEL[t.category] ?? "—"} · visto há {formatAge(t.last_seen)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

const SECURITY_LABELS: Record<string, string> = {
  honeypot: "Honeypot", cannot_sell_all: "Impede vender tudo", cannot_buy: "Impede compras", selfdestruct: "Autodestruição",
  hidden_owner: "Owner oculto", can_take_back_ownership: "Retomar propriedade", honeypot_same_creator: "Criador com honeypots",
  transfer_pausable: "Pausar transferências", blacklist: "Lista negra", owner_change_balance: "Alterar saldos",
  slippage_modifiable: "Alterar taxas", trading_cooldown: "Intervalo entre negociações", mintable: "Mint ativo",
  freezable: "Congelamento", balance_mutable: "Saldo alterável", non_transferable: "Não transferível",
  transfer_hook: "Transfer hook", closable: "Conta fechável", open_source: "Código verificado", proxy: "Proxy",
};

function flagText(key: string, v: boolean | null) {
  if (v === null || v === undefined) return <span className="text-mute">desconhecido</span>;
  const good = key === "open_source" ? v : !v;
  return <span className={good ? "text-up" : "text-down"}>{v ? "sim" : "não"}</span>;
}

export default function Asset() {
  const { id } = useParams();
  const { data, error, loading } = useApi<Json>(id ? `/tokens/${id}` : null, 60000, ["cycle"]);
  const latestRec = useApi<Json[]>(id ? `/recommendations?limit=200` : null, 60000, ["recommendation"]);
  const levels = useMemo(() => {
    const r = (latestRec.data ?? []).find((x) => String(x.token_id) === id && x.status === "ATIVA");
    if (!r) return [];
    return [
      { price: r.target1, label: "Alvo 1", color: "#22c55e" },
      { price: r.target2, label: "Alvo 2", color: "#16a34a" },
      { price: r.stop, label: "Stop", color: "#ef4444" },
    ];
  }, [latestRec.data, id]);
  if (!id) return <Search />;
  if (loading && !data) return <Loading />;
  if (!data) return <ErrorBox error={error} />;
  const t = data.token;
  const s = data.snapshot;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">{t.symbol}</h1>
        <span className="text-mute">{t.name}</span>
        <Badge tone="info">{t.chain_label}</Badge>
        <Badge>{CATEGORY_LABEL[t.category] ?? "—"}</Badge>
        {t.classification && <Badge tone={toneForStatus(t.classification)}>Classe {t.classification}</Badge>}
        <span className="num text-xs text-mute break-all">{t.address}</span>
        <Link className="text-xs text-info" to="/ativo">trocar ativo</Link>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        {[
          ["Preço", formatPrice(s?.price_usd)],
          ["Liquidez", formatUsd(s?.liquidity_usd)],
          ["Volume 24 h", formatUsd(s?.volume?.h24)],
          ["Variação 1 h / 24 h", `${formatPct(s?.price_change?.h1)} / ${formatPct(s?.price_change?.h24)}`],
          ["Compras/vendas 1 h", `${formatNumber(s?.buys?.h1)} / ${formatNumber(s?.sells?.h1)}`],
          ["Idade do par", formatAge(t.pair_created_at)],
        ].map(([l, v]) => (
          <div key={l} className="card px-3 py-2"><div className="text-[11px] uppercase text-mute">{l}</div><div className="num text-sm mt-0.5">{v}</div></div>
        ))}
      </div>
      <Card title="Candles de 5 min · EMA20 (azul) · EMA50 (âmbar) · Bandas de Bollinger" right={<span className="normal-case">Fonte {s?.source ?? "—"} · {s ? `há ${formatAge(s.observed_at)}` : ""}</span>}>
        {data.candles.length ? <PriceChart candles={data.candles} levels={levels} /> : <Empty>Ainda sem candles gravados (o ativo precisa estar no nível 2).</Empty>}
      </Card>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title={`Segurança do contrato · cobertura ${(data.security.coverage * 100).toFixed(0)}%`}>
          {data.security.blocks.length > 0 && (
            <div className="mb-3"><div className="text-xs uppercase text-down mb-1">Bloqueios</div>
              <ul className="list-disc pl-5 text-sm text-down">{data.security.blocks.map((b: string) => <li key={b}>{b}</li>)}</ul></div>
          )}
          {data.security.penalties.length > 0 && (
            <div className="mb-3"><div className="text-xs uppercase text-warn mb-1">Penalidades</div>
              <ul className="list-disc pl-5 text-sm text-warn">{data.security.penalties.map((p: Json) => <li key={p.motivo}>{p.motivo}</li>)}</ul></div>
          )}
          {data.security.reports.length === 0 ? <Empty>Sem relatório de segurança ainda.</Empty> : data.security.reports.map((r: Json) => (
            <div key={r.source} className="mb-3">
              <div className="text-xs text-mute mb-1">{r.source} · {formatDateTime(r.observed_at)}</div>
              <div className="grid grid-cols-2 gap-x-4 text-sm">
                {Object.entries(r.flags as Record<string, boolean | null>).map(([k, v]) => (
                  <div key={k} className="flex justify-between"><span className="text-mute">{SECURITY_LABELS[k] ?? k}</span>{flagText(k, v)}</div>
                ))}
                {Object.entries(r.taxes as Record<string, number | null>).map(([k, v]) => (
                  <div key={k} className="flex justify-between"><span className="text-mute">Taxa {k}</span><span className="num">{v === null ? "?" : `${v.toFixed(1)}%`}</span></div>
                ))}
                <div className="flex justify-between"><span className="text-mute">Top 10 holders</span><span className="num">{r.top10_pct === null ? "?" : `${r.top10_pct.toFixed(1)}%`}</span></div>
                <div className="flex justify-between"><span className="text-mute">Holders</span><span className="num">{formatNumber(r.holder_count)}</span></div>
              </div>
            </div>
          ))}
          <p className="text-[11px] text-mute">{data.security.aviso}</p>
        </Card>
        <Card title="Histórico de análises deste ativo">
          <DataTable rows={data.evaluations} empty="Nenhuma análise registrada."
            columns={[
              { key: "t", label: "Horário", render: (e: Json) => <span className="text-xs">{formatDateTime(e.created_at)}</span> },
              { key: "s", label: "Estratégia", render: (e: Json) => <span className="text-xs">{e.strategy ?? "—"}</span> },
              { key: "sc", label: "Nota", render: (e: Json) => <ScoreBar score={e.score} /> },
              { key: "d", label: "Decisão", render: (e: Json) => <Badge tone={toneForStatus(e.decision)}>{STATUS_LABEL[e.decision] ?? e.decision}</Badge> },
              { key: "r", label: "Motivo", className: "text-xs text-mute", render: (e: Json) => (e.reasons ?? [])[0] },
            ]} />
        </Card>
      </div>
      {data.evaluations[0]?.components && (
        <Card title="Componentes da pontuação mais recente">
          <div className="grid md:grid-cols-2 gap-x-6 gap-y-2">
            {data.evaluations[0].components.map((c: Json) => (
              <div key={c.name}>
                <div className="flex justify-between text-sm"><span>{c.label}</span><span className="num">{c.value.toFixed(1)}/10 · peso {(c.weight * 100).toFixed(0)}%</span></div>
                <div className="text-xs text-mute">{c.reason}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
