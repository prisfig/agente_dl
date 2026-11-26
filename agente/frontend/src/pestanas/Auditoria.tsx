import { useState } from "react";
import { useConsulta } from "../api";
import { MensajeError, Tarjeta } from "../componentes/Ui";
import { horaLocal } from "../formato";
import type { Decision, Estado, Evento, Modo } from "../tipos";

interface Evidencia {
  verificacion_modelo: { fecha_utc: string; equipo: Record<string, string>; versiones: Record<string, string>; orden_secuencia: string;
    TE: { n: number; coincide: boolean; [k: string]: unknown }; futuro: { fecha_corte: string; colab: number; local: number; coincide: boolean; latencia_s: number } } | null;
  archivos: string[];
}

const TIPOS_ERROR = ["sin_respuesta", "limite_solicitudes", "dato_atrasado", "llm_no_disponible", "json_invalido", "respuesta_invalida",
  "clave_incorrecta", "saldo_insuficiente", "evento_duplicado", "arranque", "control"];

export default function Auditoria({ modo, estado }: { modo: Modo; estado: Estado | null }) {
  const [nivel, setNivel] = useState<"" | "info" | "aviso" | "error">("");
  const [texto, setTexto] = useState("");
  const ev = useConsulta<Evento[]>(`/api/eventos?limite=500${nivel ? `&nivel=${nivel}` : ""}`, 10_000);
  const evi = useConsulta<Evidencia>("/api/evidencia");
  const dec = useConsulta<Decision[]>(`/api/decisiones?modo=${modo}&limite=1000`, 30_000);
  const eventos = (ev.datos ?? []).filter((e) => !texto || `${e.tipo} ${e.mensaje}`.toLowerCase().includes(texto.toLowerCase()));
  const conteo = (ev.datos ?? []).reduce<Record<string, number>>((a, e) => ({ ...a, [e.tipo]: (a[e.tipo] ?? 0) + 1 }), {});
  const llm = (dec.datos ?? []).filter((d) => d.cartera === "con_llm");
  const conAvisos = llm.filter((d) => d.detalle_llm?.avisos?.length).length;
  const v = evi.datos?.verificacion_modelo;

  return (
    <>
      <MensajeError mensaje={ev.error} />
      <div className="rejilla r3">
        <Tarjeta titulo="Verificación del modelo en esta computadora">
          {v ? (
            <table className="tabla"><tbody>
              <tr><td className="tenue">TE ({v.TE.n} pronósticos)</td><td className={v.TE.coincide ? "positivo" : "negativo"}>{v.TE.coincide ? "coinciden con Colab" : "NO coinciden"}</td></tr>
              <tr><td className="tenue">Pronóstico {v.futuro.fecha_corte}</td><td className="mono">{v.futuro.local.toFixed(8)} {v.futuro.coincide ? "✓" : "✗"}</td></tr>
              <tr><td className="tenue">Orden de la secuencia</td><td>{v.orden_secuencia}</td></tr>
              <tr><td className="tenue">Equipo</td><td className="chico">{v.equipo.plataforma}</td></tr>
              <tr><td className="tenue">Versiones</td><td className="chico mono">TF {v.versiones.tensorflow} · Keras {v.versiones.keras}</td></tr>
              <tr><td className="tenue">Fecha</td><td className="mono chico">{horaLocal(v.fecha_utc)}</td></tr>
            </tbody></table>
          ) : <span className="tenue">Sin archivo de verificación.</span>}
        </Tarjeta>
        <Tarjeta titulo="Trazabilidad">
          <table className="tabla"><tbody>
            <tr><td className="tenue">SHA-256 configuración</td><td className="mono chico">{estado?.config_sha256.slice(0, 16)}…</td></tr>
            <tr><td className="tenue">Modelo</td><td className="chico">{estado?.modelo.modelo} · semillas {estado?.modelo.semillas?.join(", ")}</td></tr>
            {Object.entries(estado?.modelo.checkpoints ?? {}).map(([k, h]) => <tr key={k}><td className="tenue chico">{k.split("/").pop()}</td><td className="mono chico">{h}</td></tr>)}
            <tr><td className="tenue">LLM</td><td className="chico">{estado?.llm.modelo} vía gateway {estado?.llm.gateway}</td></tr>
          </tbody></table>
        </Tarjeta>
        <Tarjeta titulo={`Calidad de las justificaciones del LLM (${modo})`}>
          <div className="kpi"><div className="valor">{conAvisos}/{llm.length}</div><div className="etiqueta">propuestas con avisos de validación</div>
            <div className="sub">p. ej., números citados que no están en los datos entregados</div></div>
          <div className="tenue chico" style={{ marginTop: 10 }}>Archivos de evidencia: {evi.datos?.archivos.join(", ") || "—"}</div>
        </Tarjeta>
      </div>

      <div className="seccion">Bitácora de eventos</div>
      <div className="botones" style={{ marginBottom: 10 }}>
        <span className="selector">{(["", "info", "aviso", "error"] as const).map((n) => (
          <button key={n} className={nivel === n ? "activo" : ""} onClick={() => setNivel(n)}>{n || "todos"}</button>))}</span>
        <input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Buscar tipo o mensaje…"
          style={{ background: "var(--panel-2)", border: "1px solid var(--borde)", color: "var(--texto)", borderRadius: 8, padding: "6px 10px", minWidth: 260 }} />
        {TIPOS_ERROR.filter((t) => conteo[t]).map((t) => <span key={t} className="chip" style={{ cursor: "pointer" }} onClick={() => setTexto(t)}>{t}: {conteo[t]}</span>)}
      </div>
      <Tarjeta>
        <div className="desplaza">
          <table className="tabla">
            <thead><tr><th>Hora</th><th>Nivel</th><th>Modo</th><th>Tipo</th><th>Mensaje</th><th>Detalle</th></tr></thead>
            <tbody>
              {eventos.map((e) => (
                <tr key={e.id}>
                  <td className="mono chico" style={{ whiteSpace: "nowrap" }}>{horaLocal(e.ts_utc)}</td>
                  <td><span className={`chip ${e.nivel === "error" ? "rojo" : e.nivel === "aviso" ? "ambar" : ""}`}>{e.nivel}</span></td>
                  <td className="chico">{e.modo ?? "—"}</td>
                  <td className="mono chico">{e.tipo}</td>
                  <td>{e.mensaje}</td>
                  <td>{e.detalle ? <details><summary className="tenue chico">ver</summary><pre className="json">{JSON.stringify(e.detalle, null, 2)}</pre></details> : null}</td>
                </tr>
              ))}
              {!eventos.length && <tr><td colSpan={6} className="tenue">Sin eventos.</td></tr>}
            </tbody>
          </table>
        </div>
      </Tarjeta>
    </>
  );
}
