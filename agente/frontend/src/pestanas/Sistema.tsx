import { useState } from "react";
import { useConsulta } from "../api";
import { Kpi, MensajeError, Tarjeta } from "../componentes/Ui";
import { duracion, horaLocal, num } from "../formato";
import type { Estado, Modo } from "../tipos";
import Cerebro from "./Cerebro";
import RedNeuronal from "./RedNeuronal";

const SUB = ["Salud", "Cerebro", "Red neuronal", "Ajustes"] as const;

interface DatosSistema {
  mexc: { estado: string; latencia_ms?: number; detalle?: string };
  llm: { estado: string; latencia_ms?: number; version?: string; detalle?: string; modelos_permitidos?: string[] };
  proceso: { memoria_max_mb: number; hilos: number; activo_desde_s: number; pid: number };
  programador: { vivo: boolean; revision_cada_s: number; proximo_ciclo_utc: string };
  base_datos: { ruta: string; tamano_kb: number };
  ciclos: { modo: string; n: number; lat_llm: number; lat_total: number }[];
  equipo: { sistema: string; procesador: string; python: string; cpus: number };
  modelo: Record<string, unknown>;
  simbolo?: string;
  activos?: Record<string, { estado: string; ciclos_vivo: number }>;
  config_sha256: string;
  medido_utc: string;
}

function Salud() {
  const { datos: s, error } = useConsulta<DatosSistema>("/api/sistema", 10_000);
  if (error) return <MensajeError mensaje={error} />;
  if (!s) return <div className="tenue">Midiendo…</div>;
  const llmOk = s.llm.estado === "disponible";
  return (
    <>
      <div className="rejilla r4">
        <Kpi valor={`${num(s.proceso.memoria_max_mb, 0)} MB`} etiqueta="Memoria del backend" sub="máximo del proceso (incluye TensorFlow)" />
        <Kpi valor={s.mexc.latencia_ms != null ? `${num(s.mexc.latencia_ms, 0)} ms` : "—"} etiqueta="Latencia MEXC"
          sub={s.mexc.estado === "conectado" ? "GET /api/v3/time" : s.mexc.detalle} clase={s.mexc.estado === "conectado" ? "" : "negativo"} />
        <Kpi valor={llmOk ? `${num(s.llm.latencia_ms, 0)} ms` : s.llm.estado} etiqueta="Gateway + Ollama"
          sub={llmOk ? `Ollama ${s.llm.version} · ${s.llm.modelos_permitidos?.join(", ")}` : s.llm.detalle} clase={llmOk ? "" : "negativo"} />
        <Kpi valor={`${num(s.base_datos.tamano_kb, 0)} KB`} etiqueta={`Base SQLite · ${s.simbolo ?? ""}`} sub={s.base_datos.ruta} />
      </div>
      <div className="rejilla r4" style={{ marginTop: 14 }}>
        <Kpi valor={s.programador.vivo ? "activo" : "detenido"} etiqueta="Programador del ciclo" clase={s.programador.vivo ? "positivo" : "negativo"}
          sub={`revisa cada ${s.programador.revision_cada_s} s · próximo ${horaLocal(s.programador.proximo_ciclo_utc)}`} />
        <Kpi valor={s.proceso.hilos} etiqueta="Hilos del proceso" sub={`PID ${s.proceso.pid}`} />
        <Kpi valor={duracion(s.proceso.activo_desde_s)} etiqueta="Backend activo" sub={`medido ${horaLocal(s.medido_utc)}`} />
        <Kpi valor={`${s.equipo.cpus} núcleos`} etiqueta={s.equipo.procesador} sub={`Python ${s.equipo.python}`} />
      </div>
      <div className="rejilla r2" style={{ marginTop: 14 }}>
        <Tarjeta titulo={`Ciclos registrados · ${s.simbolo ?? ""}`}>
          <table className="tabla">
            <thead><tr><th>Modo</th><th className="der">Ciclos</th><th className="der">Latencia LLM media</th><th className="der">Ciclo completo medio</th></tr></thead>
            <tbody>{s.ciclos.map((c) => (
              <tr key={c.modo}><td>{c.modo}</td><td className="der mono">{c.n}</td><td className="der mono">{num(c.lat_llm, 1)} s</td><td className="der mono">{num(c.lat_total, 1)} s</td></tr>))}
              {!s.ciclos.length && <tr><td colSpan={4} className="tenue">Sin ciclos.</td></tr>}</tbody>
          </table>
        </Tarjeta>
        <Tarjeta titulo="Equipo y modelo">
          <table className="tabla"><tbody>
            <tr><td className="tenue">Sistema</td><td className="chico">{s.equipo.sistema}</td></tr>
            <tr><td className="tenue">Inferencia LLM</td><td className="chico">local en esta computadora (sin nube) · gateway 127.0.0.1:8001</td></tr>
            <tr><td className="tenue">Modelo de pronóstico</td><td className="chico">{s.simbolo}: {String(s.modelo.modelo)} · LSTM {String(s.modelo.neuronas ?? "—")} ·
              estrategia {String(s.modelo.estrategia)} · {Number(s.modelo.parametros ?? 0).toLocaleString("es-MX")} parámetros · Keras {String(s.modelo.keras ?? "—")}
              {s.modelo.huellas_verificadas ? " · huellas SHA-256 verificadas al cargar" : ""}</td></tr>
            {s.activos && <tr><td className="tenue">Activos en este backend</td><td className="chico">
              {Object.entries(s.activos).map(([k, v]) => `${k} (${v.estado}, ${v.ciclos_vivo} ciclos en vivo)`).join(" · ")}</td></tr>}
            <tr><td className="tenue">SHA-256 configuración</td><td className="mono chico">{s.config_sha256.slice(0, 24)}…</td></tr>
          </tbody></table>
        </Tarjeta>
      </div>
    </>
  );
}

function Ajustes({ alSalir }: { alSalir: () => void }) {
  const { datos, error } = useConsulta<Record<string, unknown>>("/api/config");
  return (
    <>
      <MensajeError mensaje={error} />
      <div className="aviso azul">La configuración es de solo lectura desde la interfaz y el LLM no puede modificarla. Para cambiarla: apaga el backend,
        edita <span className="mono">agente/config/agente.json</span> y vuelve a arrancarlo. Su SHA-256 queda registrado en cada ciclo.</div>
      <div className="rejilla r2">
        <Tarjeta titulo="config/agente.json"><pre className="json">{datos ? JSON.stringify(datos, null, 2) : "…"}</pre></Tarjeta>
        <Tarjeta titulo="Sesión">
          <p className="tenue">La clave del backend solo vive en esta pestaña del navegador (sessionStorage). No está en el código de la interfaz ni en variables VITE.</p>
          <button className="boton rojo" onClick={alSalir}>Cerrar sesión</button>
        </Tarjeta>
      </div>
    </>
  );
}

export default function Sistema({ modo, estado, alSalir }: { modo: Modo; estado: Estado | null; alSalir: () => void }) {
  const [sub, setSub] = useState<(typeof SUB)[number]>("Salud");
  return (
    <>
      <nav className="pestanas sub">
        {SUB.map((s) => <button key={s} className={`pestana ${sub === s ? "activa" : ""}`} onClick={() => setSub(s)}>{s}</button>)}
      </nav>
      {sub === "Salud" && <Salud />}
      {sub === "Cerebro" && <Cerebro estado={estado} />}
      {sub === "Red neuronal" && <RedNeuronal modo={modo} />}
      {sub === "Ajustes" && <Ajustes alSalir={alSalir} />}
    </>
  );
}
