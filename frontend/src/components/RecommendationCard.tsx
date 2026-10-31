import { useState } from "react";
import { Link } from "react-router-dom";
import { api, Json } from "../api";
import { formatAge, formatIn, formatPct, formatPrice, formatUsd } from "../format";
import { Badge, Field, Modal, ScoreBar, STATUS_LABEL, toneForStatus } from "./ui";

export function ExecuteModal({ rec, onClose, onDone }: { rec: Json; onClose: () => void; onDone: () => void }) {
  const [price, setPrice] = useState(String(rec.price_observed));
  const [amount, setAmount] = useState(String(rec.amount_usd));
  const [fee, setFee] = useState("0");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.post(`/recommendations/${rec.id}/executed`, { price: Number(price), amount_usd: Number(amount), fee_usd: Number(fee) });
      onDone();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={`Registrar execução — ${rec.token?.symbol ?? ""}`} onClose={onClose}>
      <p className="text-xs text-mute mb-3">Informe os valores exatamente como a FOMO mostrou. A operação vai para o livro REAL e uma nova varredura começa na hora.</p>
      <Field label="Preço executado (US$)"><input className="input num" value={price} onChange={(e) => setPrice(e.target.value)} /></Field>
      <Field label="Valor investido (US$)"><input className="input num" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
      <Field label="Taxa cobrada pela FOMO (US$)"><input className="input num" value={fee} onChange={(e) => setFee(e.target.value)} /></Field>
      {err && <div className="text-down text-sm mb-2">{err}</div>}
      <div className="flex justify-end gap-2">
        <button className="btn" onClick={onClose}>Cancelar</button>
        <button className="btn-primary" disabled={busy} onClick={submit}>Registrar</button>
      </div>
    </Modal>
  );
}

export function RecommendationCard({ rec, onChange, compact = false }: { rec: Json; onChange: () => void; compact?: boolean }) {
  const [executing, setExecuting] = useState(false);
  const [showText, setShowText] = useState(false);
  const p = rec.payload ?? {};
  const ignore = async () => {
    await api.post(`/recommendations/${rec.id}/ignored`);
    onChange();
  };
  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex items-center gap-2">
          <Link to={`/ativo/${rec.token_id}`} className="text-lg font-semibold hover:text-info">{p.token ?? rec.token?.symbol}</Link>
          <Badge tone="info">{p.rede}</Badge>
          <Badge>{p.tipo}</Badge>
          <Badge tone={toneForStatus(rec.status)}>{STATUS_LABEL[rec.status] ?? rec.status}</Badge>
        </div>
        <div className="w-40"><ScoreBar score={rec.score} /></div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3 text-sm">
        <div><div className="text-xs text-mute">Preço observado</div><div className="num">{formatPrice(rec.price_observed)}</div></div>
        <div><div className="text-xs text-mute">Valor sugerido</div><div className="num">{formatUsd(rec.amount_usd)}</div></div>
        <div><div className="text-xs text-mute">Alvo 1 / Alvo 2</div><div className="num text-up">{formatPrice(rec.target1)} / {formatPrice(rec.target2)}</div></div>
        <div><div className="text-xs text-mute">Stop de referência</div><div className="num text-down">{formatPrice(rec.stop)} ({formatPct(p.stop_pct)})</div></div>
      </div>
      <div className="text-xs text-mute mt-2">
        {p.estrategia_nome} · R:R líquido {p.rr_liquido} · custo ida e volta {p.custos ? `${p.custos.round_trip_pct.toFixed(2)}%` : "—"} ·
        emitida há {formatAge(rec.created_at)} · expira {rec.status === "ATIVA" ? `em ${formatIn(rec.expires_at)}` : "—"}
      </div>
      {!compact && (
        <>
          <div className="mt-3 text-sm">
            <div className="text-xs uppercase tracking-wider text-mute mb-1">Justificativa</div>
            <ul className="list-disc pl-5 space-y-0.5">{(p.justificativa ?? []).map((j: string, i: number) => <li key={i}>{j}</li>)}</ul>
          </div>
          <div className="mt-3 text-sm">
            <div className="text-xs uppercase tracking-wider text-mute mb-1">Riscos</div>
            <ul className="list-disc pl-5 space-y-0.5 text-warn/90">{(p.riscos ?? []).map((j: string, i: number) => <li key={i}>{j}</li>)}</ul>
          </div>
          <div className="mt-3 text-sm"><span className="text-xs uppercase tracking-wider text-mute">Cenário negativo: </span>{p.cenario_negativo}</div>
          <div className="mt-1 text-sm"><span className="text-xs uppercase tracking-wider text-mute">Confiança estatística: </span>{p.confianca_estatistica}</div>
          {rec.status_reason && <div className="mt-1 text-sm text-mute">Situação: {rec.status_reason}</div>}
        </>
      )}
      <div className="flex flex-wrap gap-2 mt-3">
        {rec.status === "ATIVA" && <button className="btn-primary" onClick={() => setExecuting(true)}>Executei na FOMO</button>}
        {rec.status === "ATIVA" && <button className="btn" onClick={ignore}>Ignorar</button>}
        <button className="btn" onClick={() => setShowText((v) => !v)}>{showText ? "Ocultar texto" : "Texto completo"}</button>
        <button className="btn" onClick={() => navigator.clipboard?.writeText(rec.text)}>Copiar</button>
      </div>
      {showText && <pre className="mt-3 text-xs whitespace-pre-wrap bg-panel2 border border-line rounded p-3 num">{rec.text}</pre>}
      <p className="text-[11px] text-mute mt-2">{p.aviso}</p>
      {executing && <ExecuteModal rec={rec} onClose={() => setExecuting(false)} onDone={onChange} />}
    </div>
  );
}
