import { useCallback, useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api, Json } from "./api";
import { Badge } from "./components/ui";
import { formatAge } from "./format";
import { useApi, useConnection, useLiveEvents } from "./live";
import Asset from "./pages/Asset";
import Dashboard from "./pages/Dashboard";
import History from "./pages/History";
import Logs from "./pages/Logs";
import NewTokens from "./pages/NewTokens";
import Opportunities from "./pages/Opportunities";
import Portfolio from "./pages/Portfolio";
import Providers from "./pages/Providers";
import Recommendations from "./pages/Recommendations";
import RiskSettings from "./pages/RiskSettings";
import Stats from "./pages/Stats";

const NAV = [
  ["/", "Dashboard"],
  ["/oportunidades", "Oportunidades"],
  ["/novos-tokens", "Novos tokens"],
  ["/ativo", "Análise de ativo"],
  ["/recomendacoes", "Recomendações"],
  ["/portfolio", "Portfólio"],
  ["/historico", "Histórico"],
  ["/estatisticas", "Estatísticas"],
  ["/risco", "Risco"],
  ["/provedores", "Provedores"],
  ["/logs", "Logs e diagnóstico"],
] as const;

function useTheme() {
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem("tema") !== "claro";
    } catch {
      return true;
    }
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("tema", dark ? "escuro" : "claro");
    } catch {
      /* armazenamento indisponível */
    }
  }, [dark]);
  return [dark, setDark] as const;
}

function Toasts() {
  const [items, setItems] = useState<Json[]>([]);
  const onLive = useCallback((msg: Json) => {
    if (msg.type !== "notification") return;
    setItems((xs) => [msg.data, ...xs].slice(0, 4));
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== msg.data.id)), 12000);
  }, []);
  useLiveEvents(onLive);
  const tone: Record<string, string> = { critica: "border-down", alta: "border-warn", media: "border-info", info: "border-line" };
  return (
    <div className="fixed bottom-4 right-4 z-40 space-y-2 w-80">
      {items.map((n) => (
        <div key={n.id} className={`card p-3 border-l-4 ${tone[n.severity] ?? "border-line"} shadow-lg`}>
          <div className="text-sm font-medium">{n.title}</div>
          <div className="text-xs text-mute mt-0.5">{n.body}</div>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [dark, setDark] = useTheme();
  const online = useConnection();
  const { data: dash, reload } = useApi<Json>("/dashboard", 30000, ["cycle", "settings", "recommendation"]);
  const [menu, setMenu] = useState(false);
  const togglePause = async () => {
    await api.post(dash?.paused ? "/control/resume" : "/control/pause");
    reload();
  };
  const stateTone = { OPERANDO: "up", PAUSADO: "warn", BLOQUEADO: "down", INICIANDO: "info" }[dash?.state as string] ?? "mute";
  return (
    <div className="min-h-screen flex">
      <aside className={`${menu ? "block" : "hidden"} md:block w-56 shrink-0 border-r border-line bg-panel fixed md:static inset-y-0 z-30`}>
        <div className="px-4 py-4 border-b border-line">
          <div className="font-semibold tracking-tight">FOMO AI</div>
          <div className="text-[11px] text-mute">Trading Intelligence · consultivo</div>
        </div>
        <nav className="py-2">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} onClick={() => setMenu(false)}
                     className={({ isActive }) => `block px-4 py-2 text-sm ${isActive ? "bg-panel2 text-info border-l-2 border-info" : "text-mute hover:text-ink"}`}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 text-[11px] text-mute border-t border-line">
          Não executa ordens nem acessa a FOMO. Dados: DexScreener, GeckoTerminal, GoPlus.
        </div>
      </aside>
      <div className="flex-1 min-w-0">
        <header className="h-12 border-b border-line bg-panel flex items-center gap-3 px-4 sticky top-0 z-20">
          <button className="md:hidden btn" onClick={() => setMenu((m) => !m)}>☰</button>
          <Badge tone={stateTone as never}>{dash?.state ?? "…"}</Badge>
          <Badge tone={dash?.mode === "REAL" ? "warn" : "info"}>Modo {dash?.mode ?? "…"}</Badge>
          <span className="text-xs text-mute hidden sm:inline">
            Última análise: {dash?.last_cycle ? `há ${formatAge(dash.last_cycle.finished_at)}` : "—"}
          </span>
          <div className="flex-1" />
          <span className={`text-xs ${online ? "text-up" : "text-down"}`}>{online ? "● ao vivo" : "● desconectado"}</span>
          <button className="btn" onClick={togglePause}>{dash?.paused ? "Retomar" : "Pausar"} monitoramento</button>
          <button className="btn" onClick={() => setDark(!dark)} title="Alternar tema">{dark ? "☀" : "☾"}</button>
        </header>
        <main className="p-4 max-w-[1500px] mx-auto">
          <Routes>
            <Route path="/" element={<Dashboard dash={dash} reload={reload} />} />
            <Route path="/oportunidades" element={<Opportunities />} />
            <Route path="/novos-tokens" element={<NewTokens />} />
            <Route path="/ativo" element={<Asset />} />
            <Route path="/ativo/:id" element={<Asset />} />
            <Route path="/recomendacoes" element={<Recommendations />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/historico" element={<History />} />
            <Route path="/estatisticas" element={<Stats />} />
            <Route path="/risco" element={<RiskSettings />} />
            <Route path="/provedores" element={<Providers />} />
            <Route path="/logs" element={<Logs />} />
          </Routes>
        </main>
      </div>
      <Toasts />
    </div>
  );
}
