import { FormEvent, ReactNode, useEffect, useState } from "react";
import { api, ApiError, getToken, LOGIN_REQUIRED, setToken } from "../api";
import { reconnectLive } from "../live";

type State = "verificando" | "acordando" | "login" | "ok";

/** Pede a senha quando o servidor online exige; no uso local (sem senha) mostra o app direto. */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>("verificando");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const check = async () => {
      try {
        const { required } = await api.get<{ required: boolean }>("/auth");
        if (alive) setState(required && !getToken() ? "login" : "ok");
      } catch {
        // Servidor gratuito dormindo: a primeira resposta pode levar cerca de 1 minuto
        if (alive) {
          setState("acordando");
          timer = setTimeout(check, 5000);
        }
      }
    };
    check();
    const onRequired = () => setState("login");
    window.addEventListener(LOGIN_REQUIRED, onRequired);
    return () => {
      alive = false;
      clearTimeout(timer);
      window.removeEventListener(LOGIN_REQUIRED, onRequired);
    };
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { token } = await api.post<{ token: string }>("/login", { password });
      setToken(token);
      setPassword("");
      reconnectLive();
      setState("ok");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Servidor indisponível. Tente de novo em instantes.");
    } finally {
      setBusy(false);
    }
  };

  if (state === "ok") return <>{children}</>;
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm border border-line bg-panel rounded p-6">
        <div className="font-semibold tracking-tight">FOMO AI</div>
        <div className="text-[11px] text-mute mb-4">Trading Intelligence · consultivo</div>
        {state === "verificando" && <div className="text-sm text-mute">Conectando ao servidor…</div>}
        {state === "acordando" && (
          <div className="text-sm text-mute">
            Acordando o servidor… O plano gratuito desliga o servidor quando fica parado, e ele pode levar cerca de 1 minuto para voltar.
          </div>
        )}
        {state === "login" && (
          <form onSubmit={submit} className="space-y-3">
            <label className="block text-sm">
              Senha de acesso
              <input type="password" className="input w-full mt-1" value={password} autoFocus autoComplete="current-password"
                     onChange={(e) => setPassword(e.target.value)} />
            </label>
            {error && <div className="text-sm text-down">{error}</div>}
            <button className="btn w-full" disabled={busy || !password}>{busy ? "Entrando…" : "Entrar"}</button>
          </form>
        )}
      </div>
    </div>
  );
}
