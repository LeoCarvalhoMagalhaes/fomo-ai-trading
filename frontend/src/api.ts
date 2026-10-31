/* eslint-disable @typescript-eslint/no-explicit-any */
export type Json = any;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Vazio no uso local (mesmo endereço); no GitHub Pages, a URL do servidor online, definida no build. */
export const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? "";
const TOKEN_KEY = "fomo-token";
export const LOGIN_REQUIRED = "fomo:login-required";

export function buildApiUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, "")}/api${path}`;
}

export function buildWsUrl(base: string, loc: { protocol: string; host: string }, token: string | null): string {
  let origin: string;
  if (base) {
    origin = base.replace(/\/+$/, "").replace(/^http/, "ws");
  } else {
    origin = `${loc.protocol === "https:" ? "wss" : "ws"}://${loc.host}`;
  }
  return `${origin}/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* armazenamento indisponível: o login vale só até recarregar */
  }
}

async function request<T = Json>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(buildApiUrl(API_BASE, path), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && path !== "/login") {
    setToken(null);
    window.dispatchEvent(new Event(LOGIN_REQUIRED));
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* resposta sem JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export const api = {
  get: <T = Json>(p: string) => request<T>("GET", p),
  post: <T = Json>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  put: <T = Json>(p: string, b: unknown) => request<T>("PUT", p, b),
};
