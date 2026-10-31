import { useState } from "react";
import { api, Json } from "../api";
import { Badge, Card, CATEGORY_LABEL, DataTable, Empty, ErrorBox, Field, Loading, Modal, Stat } from "../components/ui";
import { formatAge, formatPct, formatPrice, formatUsd, parseDecimal } from "../format";
import { useApi } from "../live";

const CHAINS = ["solana", "base", "bsc", "ethereum", "monad", "robinhood"];

function NewTradeModal({ ledger, onClose, onDone }: { ledger: string; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ chain: "solana", address: "", symbol: "", category: "established", amount_usd: "5", price: "", fee_usd: "0", note: "" });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = async () => {
    setErr(null);
    try {
      const a = parseDecimal(f.amount_usd), p = parseDecimal(f.price), fee = parseDecimal(f.fee_usd);
      if (a === null || p === null || fee === null) throw new Error("Valor, preço e taxa precisam ser números (vírgula ou ponto).");
      await api.post("/trades", { ledger, ...f, amount_usd: a, price: p, fee_usd: fee });
      onDone();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <Modal title={`Registrar operação manual (${ledger})`} onClose={onClose}>
      <Field label="Rede"><select className="input" value={f.chain} onChange={set("chain")}>{CHAINS.map((c) => <option key={c}>{c}</option>)}</select></Field>
      <Field label="Endereço do contrato"><input className="input num" value={f.address} onChange={set("address")} /></Field>
      <Field label="Símbolo"><input className="input" value={f.symbol} onChange={set("symbol")} /></Field>
      <Field label="Tipo"><select className="input" value={f.category} onChange={set("category")}>
        <option value="established">Estabelecido</option><option value="intermediate">Intermediário</option><option value="new">Novo</option></select></Field>
      <div className="grid grid-cols-3 gap-2">
        <Field label="Valor (US$)"><input className="input num" value={f.amount_usd} onChange={set("amount_usd")} /></Field>
        <Field label="Preço (US$)"><input className="input num" value={f.price} onChange={set("price")} /></Field>
        <Field label="Taxa (US$)"><input className="input num" value={f.fee_usd} onChange={set("fee_usd")} /></Field>
      </div>
      <Field label="Observação"><input className="input" value={f.note} onChange={set("note")} /></Field>
      {err && <div className="text-down text-sm mb-2">{err}</div>}
      <div className="flex justify-end gap-2"><button className="btn" onClick={onClose}>Cancelar</button><button className="btn-primary" onClick={submit}>Registrar</button></div>
    </Modal>
  );
}

function CloseModal({ trade, onClose, onDone }: { trade: Json; onClose: () => void; onDone: () => void }) {
  const [price, setPrice] = useState(String(trade.current_price ?? ""));
  const [fee, setFee] = useState("0");
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => {
    try {
      const p = parseDecimal(price), f = parseDecimal(fee);
      if (p === null || f === null) throw new Error("Preço e taxa precisam ser números (vírgula ou ponto).");
      await api.post(`/trades/${trade.id}/close`, { price: p, fee_usd: f });
      onDone();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <Modal title={`Encerrar ${trade.token.symbol}`} onClose={onClose}>
      <Field label="Preço de venda (US$)"><input className="input num" value={price} onChange={(e) => setPrice(e.target.value)} /></Field>
      <Field label="Taxa da venda (US$)"><input className="input num" value={fee} onChange={(e) => setFee(e.target.value)} /></Field>
      {err && <div className="text-down text-sm mb-2">{err}</div>}
      <div className="flex justify-end gap-2"><button className="btn" onClick={onClose}>Cancelar</button><button className="btn-primary" onClick={submit}>Encerrar</button></div>
    </Modal>
  );
}

export default function Portfolio() {
  const [ledger, setLedger] = useState("SIM");
  const { data: p, error, loading, reload } = useApi<Json>(`/portfolio/${ledger}`, 20000, ["portfolio"]);
  const [adding, setAdding] = useState(false);
  const [closing, setClosing] = useState<Json | null>(null);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {["SIM", "REAL"].map((l) => (
          <button key={l} className={ledger === l ? "btn-primary" : "btn"} onClick={() => setLedger(l)}>
            {l === "SIM" ? "Simulação" : "Acompanhamento manual (real)"}
          </button>
        ))}
        <div className="flex-1" />
        <button className="btn" onClick={() => setAdding(true)}>Registrar operação</button>
      </div>
      <p className="text-xs text-mute">
        {ledger === "SIM" ? "Livro de simulação: operações fictícias, abertas automaticamente a cada recomendação aprovada e encerradas no alvo 1, no stop ou em 60 min (avaliado a cada 60 s)."
          : "Livro real: só o que você informar que executou na FOMO. Os resultados nunca se misturam com a simulação."}
      </p>
      <ErrorBox error={error} />
      {loading && !p ? <Loading /> : p && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
            <Stat label="Capital inicial" value={formatUsd(p.capital_initial)} />
            <Stat label="Capital atual" value={formatUsd(p.capital_current)} tone={p.capital_current >= p.capital_initial ? "up" : "down"} hint={`Rentabilidade ${formatPct(p.return_pct)}`} />
            <Stat label="Disponível" value={formatUsd(p.available)} hint={`Reserva mínima ${formatUsd(p.reserve)}`} />
            <Stat label="Exposição" value={formatUsd(p.exposure)} hint={`Em tokens novos: ${formatUsd(p.new_exposure)}`} />
            <Stat label="P&L não realizado (est.)" value={formatUsd(p.unrealized_pnl)} tone={p.unrealized_pnl >= 0 ? "up" : "down"} />
            <Stat label="Taxas pagas" value={formatUsd(p.fees_total)} hint={`Drawdown máx. ${formatUsd(p.metrics.max_drawdown_usd)}`} />
          </div>
          <Card title="Posições abertas">
            {p.positions.length === 0 ? <Empty>Nenhuma posição aberta.</Empty> : (
              <DataTable rows={p.positions} columns={[
                { key: "t", label: "Ativo", render: (x: Json) => <span>{x.token.symbol} <span className="text-xs text-mute">{x.token.chain_label}</span></span> },
                { key: "c", label: "Tipo", render: (x: Json) => <span className="text-xs">{CATEGORY_LABEL[x.category] ?? "—"}</span> },
                { key: "a", label: "Valor", render: (x: Json) => <span className="num">{formatUsd(x.amount_usd)}</span> },
                { key: "e", label: "Entrada", render: (x: Json) => <span className="num">{formatPrice(x.entry_price)}</span> },
                { key: "n", label: "Atual", render: (x: Json) => <span className="num">{formatPrice(x.current_price)}</span> },
                { key: "s", label: "Stop / Alvo", render: (x: Json) => <span className="num text-xs">{formatPrice(x.stop)} / {formatPrice(x.target1)}</span> },
                { key: "u", label: "P&L est.", render: (x: Json) => <span className={`num ${x.unrealized_pnl_usd >= 0 ? "text-up" : "text-down"}`}>{formatUsd(x.unrealized_pnl_usd)}</span> },
                { key: "h", label: "Aberta há", render: (x: Json) => <span className="text-xs">{formatAge(x.executed_at)}</span> },
                { key: "f", label: "Alertas", className: "text-xs text-warn", render: (x: Json) => (x.limit_flags ?? []).join("; ") },
                { key: "x", label: "", render: (x: Json) => ledger === "REAL" ? <button className="btn text-xs" onClick={() => setClosing(x)}>Encerrar</button> : <Badge>automática</Badge> },
              ]} />
            )}
          </Card>
          <Card title="Exposição por ativo">
            {Object.keys(p.exposure_by_token).length === 0 ? <Empty>Sem exposição.</Empty> : (
              <ul className="text-sm space-y-1">{Object.entries(p.exposure_by_token as Record<string, number>).map(([k, v]) => (
                <li key={k} className="flex justify-between"><span>{k}</span><span className="num">{formatUsd(v)}</span></li>))}</ul>
            )}
          </Card>
        </>
      )}
      {adding && <NewTradeModal ledger={ledger} onClose={() => setAdding(false)} onDone={reload} />}
      {closing && <CloseModal trade={closing} onClose={() => setClosing(null)} onDone={reload} />}
    </div>
  );
}
