import { useCallback, useEffect, useRef, useState } from "react";
import { api, API_BASE, buildWsUrl, getToken, Json } from "./api";

type Listener = (msg: Json) => void;
const listeners = new Set<Listener>();
let socket: WebSocket | null = null;
let connected = false;
const statusListeners = new Set<(c: boolean) => void>();

function connect() {
  socket = new WebSocket(buildWsUrl(API_BASE, location, getToken()));
  socket.onopen = () => {
    connected = true;
    statusListeners.forEach((l) => l(true));
  };
  socket.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      listeners.forEach((l) => l(msg));
    } catch {
      /* mensagem inválida ignorada */
    }
  };
  socket.onclose = () => {
    connected = false;
    statusListeners.forEach((l) => l(false));
    setTimeout(connect, 3000); // reconexão automática
  };
}

/** Reabre a conexão ao vivo com o token novo (depois do login). */
export function reconnectLive() {
  socket?.close(); // o onclose agenda a reconexão
}

export function useLiveEvents(listener: Listener) {
  useEffect(() => {
    if (!socket) connect();
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, [listener]);
}

export function useConnection(): boolean {
  const [c, setC] = useState(connected);
  useEffect(() => {
    if (!socket) connect();
    statusListeners.add(setC);
    return () => {
      statusListeners.delete(setC);
    };
  }, []);
  return c;
}

/** Busca dados, atualiza a cada `everyMs` e quando chega um evento ao vivo dos tipos indicados. */
export function useApi<T = Json>(path: string | null, everyMs = 30000, liveTypes: string[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const pathRef = useRef(path);
  pathRef.current = path;
  const typesKey = liveTypes.join(",");

  const reload = useCallback(async () => {
    if (!pathRef.current) return;
    try {
      const d = await api.get<T>(pathRef.current);
      setData(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    reload();
    if (!everyMs) return;
    const id = setInterval(reload, everyMs);
    return () => clearInterval(id);
  }, [path, everyMs, reload]);

  const onLive = useCallback(
    (msg: Json) => {
      if (typesKey && typesKey.split(",").includes(msg.type)) reload();
    },
    [typesKey, reload],
  );
  useLiveEvents(onLive);

  return { data, error, loading, reload };
}
