import { ReactNode, useMemo, useState } from "react";

export function Card({ title, right, children, className = "" }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {title !== undefined && (
        <header className="card-h">
          <span>{title}</span>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "up" | "down" | "warn" | "info" }) {
  const color = tone ? { up: "text-up", down: "text-down", warn: "text-warn", info: "text-info" }[tone] : "text-ink";
  return (
    <div className="card px-4 py-3">
      <div className="text-xs uppercase tracking-wider text-mute">{label}</div>
      <div className={`num text-xl mt-1 ${color}`}>{value}</div>
      {hint && <div className="text-xs text-mute mt-1">{hint}</div>}
    </div>
  );
}

const BADGE: Record<string, string> = {
  up: "bg-up/15 text-up border-up/30",
  down: "bg-down/15 text-down border-down/30",
  warn: "bg-warn/15 text-warn border-warn/30",
  info: "bg-info/15 text-info border-info/30",
  mute: "bg-panel2 text-mute border-line",
};

export function Badge({ tone = "mute", children }: { tone?: keyof typeof BADGE; children: ReactNode }) {
  return <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[11px] font-medium whitespace-nowrap ${BADGE[tone]}`}>{children}</span>;
}

export function toneForStatus(s: string): keyof typeof BADGE {
  return (
    ({ ATIVA: "info", EXECUTADA: "up", IGNORADA: "mute", EXPIRADA: "warn", RECOMENDADA: "up", REJEITADA: "mute", OPEN: "info", CLOSED: "mute",
       A: "up", B: "warn", C: "down", alvo1: "up", stop: "down", tempo: "mute" } as Record<string, keyof typeof BADGE>)[s] ?? "mute"
  );
}

export const STATUS_LABEL: Record<string, string> = {
  ATIVA: "Ativa", EXECUTADA: "Executada", IGNORADA: "Ignorada", EXPIRADA: "Expirada", RECOMENDADA: "Recomendada",
  REJEITADA: "Rejeitada", OPEN: "Aberta", CLOSED: "Encerrada", alvo1: "Alvo 1", stop: "Stop", tempo: "Tempo", sem_dados: "Sem dados",
};

export const CATEGORY_LABEL: Record<string, string> = { established: "Estabelecido", intermediate: "Intermediário", new: "Novo" };

export function ScoreBar({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) return <span className="text-mute">—</span>;
  const tone = score >= 90 ? "bg-up" : score >= 80 ? "bg-info" : score >= 70 ? "bg-warn" : "bg-mute";
  return (
    <div className="flex items-center gap-2 min-w-[110px]">
      <div className="h-1.5 flex-1 bg-panel2 rounded">
        <div className={`h-1.5 rounded ${tone}`} style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </div>
      <span className="num text-xs w-8 text-right">{score.toFixed(0)}</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="text-sm text-mute py-6 text-center">{children}</div>;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="card border-down/50 text-down text-sm px-4 py-2 mb-3">Erro ao carregar: {error}</div>;
}

export function Loading() {
  return <div className="text-sm text-mute py-6 text-center">Carregando…</div>;
}

export interface Column<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  sort?: (row: T) => number | string | null;
  className?: string;
}

/** Tabela com filtro de texto e ordenação por coluna. */
export function DataTable<T>({ rows, columns, filterText, empty = "Nenhum registro.", initialSort }: {
  rows: T[]; columns: Column<T>[]; filterText?: (row: T) => string; empty?: string; initialSort?: { key: string; desc: boolean };
}) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState(initialSort ?? null);
  const shown = useMemo(() => {
    let r = rows;
    if (q && filterText) r = r.filter((row) => filterText(row).toLowerCase().includes(q.toLowerCase()));
    const col = sort && columns.find((c) => c.key === sort.key);
    if (col?.sort) {
      const f = col.sort;
      r = [...r].sort((a, b) => {
        const va = f(a), vb = f(b);
        if (va === vb) return 0;
        if (va === null) return 1;
        if (vb === null) return -1;
        return (va < vb ? -1 : 1) * (sort!.desc ? -1 : 1);
      });
    }
    return r;
  }, [rows, q, sort, columns, filterText]);
  return (
    <div>
      {filterText && (
        <div className="mb-3 max-w-xs">
          <input className="input" placeholder="Filtrar…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="data">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={c.sort ? "cursor-pointer select-none" : ""}
                    onClick={() => c.sort && setSort((s) => ({ key: c.key, desc: s?.key === c.key ? !s.desc : true }))}>
                  {c.label}
                  {sort?.key === c.key ? (sort.desc ? " ↓" : " ↑") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, i) => (
              <tr key={i}>
                {columns.map((c) => (
                  <td key={c.key} className={c.className}>{c.render(row)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && <Empty>{empty}</Empty>}
      </div>
    </div>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <header className="card-h">
          <span>{title}</span>
          <button className="text-mute hover:text-ink" onClick={onClose} aria-label="Fechar">✕</button>
        </header>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block mb-3">
      <span className="text-xs text-mute">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="text-[11px] text-mute">{hint}</span>}
    </label>
  );
}
