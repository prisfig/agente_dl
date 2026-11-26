import { useCallback, useEffect, useRef, useState } from "react";

// Dirección del backend local (no es un secreto). Si la interfaz se sirve desde el propio backend (/ui), usa el mismo origen.
export const BASE =
  window.location.port === "8000" ? window.location.origin : "http://127.0.0.1:8000";

const CLAVE_SESION = "agente_api_key";

export const sesion = {
  clave: () => sessionStorage.getItem(CLAVE_SESION) ?? "",
  guardar: (c: string) => sessionStorage.setItem(CLAVE_SESION, c),
  cerrar: () => sessionStorage.removeItem(CLAVE_SESION),
};

// Activo seleccionado en la interfaz (v1.3). Se agrega como ?simbolo= a las rutas del agente; sin él, el backend usa BTCUSDT.
const CLAVE_ACTIVO = "agente_activo";
export const activoSel = {
  obtener: () => sessionStorage.getItem(CLAVE_ACTIVO) ?? "",
  fijar: (s: string) => sessionStorage.setItem(CLAVE_ACTIVO, s),
};
export const activoBase = () => (activoSel.obtener() || "BTCUSDT").replace(/USDT$/, "");

const SIN_ACTIVO = ["/api/salud", "/api/activos", "/api/escaner", "/api/config", "/api/operaciones", "/api/riesgo/rearmar_todos",
  "/api/senales", "/api/notificaciones"];
export function conActivo(ruta: string) {
  const s = activoSel.obtener();
  if (!s || !ruta.startsWith("/api/") || SIN_ACTIVO.some((r) => ruta.startsWith(r)) || /[?&]simbolo=/.test(ruta)) return ruta;
  return `${ruta}${ruta.includes("?") ? "&" : "?"}simbolo=${encodeURIComponent(s)}`;
}

export class ErrorApi extends Error {
  constructor(public estado: number, mensaje: string) {
    super(mensaje);
  }
}

let alNoAutorizado: () => void = () => {};
export const registrarNoAutorizado = (f: () => void) => {
  alNoAutorizado = f;
};

export async function llamar<T>(ruta: string, opciones: RequestInit = {}, clave = sesion.clave()): Promise<T> {
  let r: Response;
  try {
    r = await fetch(BASE + conActivo(ruta), {
      ...opciones,
      headers: { "X-API-Key": clave, "Content-Type": "application/json", ...(opciones.headers ?? {}) },
    });
  } catch {
    throw new ErrorApi(0, "No hay conexión con el backend (¿está corriendo en 127.0.0.1:8000?).");
  }
  if (r.status === 401) {
    alNoAutorizado();
    throw new ErrorApi(401, "Clave incorrecta o sesión cerrada.");
  }
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new ErrorApi(r.status, (cuerpo as { detail?: string }).detail ?? `HTTP ${r.status}`);
  return cuerpo as T;
}

export const enviar = <T,>(ruta: string, cuerpo?: unknown) =>
  llamar<T>(ruta, { method: "POST", body: cuerpo ? JSON.stringify(cuerpo) : undefined });

export function useConsulta<T>(ruta: string | null, cadaMs = 0) {
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const rutaRef = useRef(ruta);
  rutaRef.current = ruta;

  const recargar = useCallback(async () => {
    if (!rutaRef.current) return;
    setCargando(true);
    try {
      const d = await llamar<T>(rutaRef.current);
      setDatos(d);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    if (!ruta) return;
    setDatos(null);
    recargar();
    if (!cadaMs) return;
    const id = setInterval(recargar, cadaMs);
    return () => clearInterval(id);
  }, [ruta, cadaMs, recargar]);

  return { datos, error, cargando, recargar };
}
