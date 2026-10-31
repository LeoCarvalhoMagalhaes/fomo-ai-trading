const MINUS = "−";

function br(n: number, digits: number): string {
  return n.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatUsd(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const s = `US$ ${br(Math.abs(v), 2)}`;
  return v < 0 ? `${MINUS}${s}` : s;
}

export function formatPrice(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  if (Math.abs(v) >= 1) return `US$ ${br(v, 4)}`;
  const s = v.toPrecision(4);
  const digits = s.includes("e") ? Number(s).toFixed(20).replace(/0+$/, "").split(".")[1]?.length ?? 4 : s.split(".")[1]?.length ?? 4;
  return `US$ ${br(Number(s), digits)}`;
}

export function formatPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const s = `${br(Math.abs(v), digits)}%`;
  return v < 0 ? `${MINUS}${s}` : `+${s}`;
}

export function formatNumber(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return br(v, digits);
}

export function formatAge(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  if (s < 86400) return `${Math.round(s / 3600)} h`;
  return `${Math.round(s / 86400)} d`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" });
}

export function shortAddress(a: string | null | undefined): string {
  if (!a) return "—";
  return a.length > 12 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a;
}

export function formatIn(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const ms = new Date(iso).getTime() - now;
  if (ms <= 0) return "agora";
  return formatAge(new Date(now - ms).toISOString(), now);
}
