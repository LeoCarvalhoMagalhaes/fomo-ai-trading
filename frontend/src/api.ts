/* eslint-disable @typescript-eslint/no-explicit-any */
export type Json = any;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T = Json>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
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
