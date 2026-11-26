import { useState } from "react";
import { enviar } from "../api";
import { Acc, BotonConfirmar, BotonRearmarTodos, EstadoChip, Kpi, Tarjeta } from "../componentes/Ui";
import { hace, horaLocal, num, pct, precio } from "../formato";
import { REGLAS, senalDe, type Estado, type ListaActivos, type Modo } from "../tipos";

function TablaActivos({ lista, actual, alElegir }: { lista: ListaActivos; actual: string; alElegir: (s: string) => void }) {
  return (
    <Tarjeta titulo="Activos · cada uno tiene su propio modelo validado y control (v2.0: sin saldos a la vista)">
      <table className="tabla">
        <thead><tr><th>Activo</th><th>Estado</th><th>Modelo</th><th>Estrategia (VA)</th><th className="der">δ</th><th>Última vela</th>
          <th className="der">Pronóstico</th><th>Señal</th><th className="der">Ciclos</th></tr></thead>
        <tbody>
          {lista.activos.map((a) => (
            <tr key={a.simbolo} className={`fila-activo ${a.simbolo === actual ? "elegida" : ""}`} onClick={() => alElegir(a.simbolo)}>
              <td className="mono"><b>{a.simbolo}</b></td>
              <td><EstadoChip estado={a.estado.estado} /></td>
              <td className="chico">LSTM {a.neuronas} · 3 semillas</td>
              <td className="chico" title={REGLAS[a.estrategia]}>{a.estrategia} · {a.estrategia === "D" ? "con filtro SMA20" : "sin filtro"}</td>
              <td className="der mono">{pct(a.delta, 4, false)}</td>
              <td className="mono">{a.ultima_vela ?? <span className="tenue">sin ciclos</span>}</td>
              <td className="der mono">{pct(a.pronostico, 3)}</td>
              <td>{a.senal ? <span className={`accion ${a.senal === "comprar" ? "COMPRAR" : "MANTENER"}`}>{a.senal}</span> : <span className="tenue">—</span>}</td>
              <td className="der mono">{a.ciclos}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="tenue chico" style={{ marginTop: 8 }}>Pulsa una fila (o el selector de arriba) para ver ese activo en todas las pestañas.
        Los ciclos de todos los activos corren uno tras otro después del cierre diario (BTC primero).</div>
    </Tarjeta>
  );
}

export default function Resumen({ estado, modo, recargar, activos, alElegir }: {
  estado: Estado | null; modo: Modo; recargar: () => void; activos: ListaActivos | null; alElegir: (s: string) => void }) {
  const [mensaje, setMensaje] = useState<{ texto: string; tipo: "azul" | "rojo" } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  if (!estado) return <div className="tenue">Cargando…</div>;

  const ag = estado.agente.estado;
  const c = estado.ultimo_ciclo;
  const o = c?.observacion;
  const decLlm = estado.decisiones.find((d) => d.cartera === "con_llm");

  const ejecutar = async (ruta: string, etiqueta: string) => {
    setOcupado(true);
    try {
      const r = await enviar<Record<string, unknown>>(ruta);
      const res = r.resultado as string | undefined;
      const texto = res === "error" ? `Error: ${r.mensaje}` : res === "omitido" ? `${r.motivo}` : res === "duplicado"
        ? `La vela ${r.fecha_vela} ya estaba procesada: no se repitió ninguna operación.` : res === "completo"
        ? `Ciclo ${estado.activo} ${r.fecha_vela} completo. LLM propuso ${r.propuesta_llm}.` : `${etiqueta} (${estado.activo}): listo.`;
      setMensaje({ texto, tipo: res === "error" ? "rojo" : "azul" });
    } catch (e) {
      setMensaje({ texto: (e as Error).message, tipo: "rojo" });
    } finally {
      setOcupado(false);
      recargar();
    }
  };

  return (
    <>
      {activos && activos.activos.length > 1 && <TablaActivos lista={activos} actual={estado.activo} alElegir={alElegir} />}
      {modo === "vivo" && (
        <Tarjeta titulo={`Control humano · ${estado.activo}`} extra={<EstadoChip estado={ag} />} estilo={activos && activos.activos.length > 1 ? { marginTop: 14 } : undefined}>
          <div className="botones">
            <button className="boton verde" disabled={ocupado || ag === "corriendo"} onClick={() => ejecutar("/api/agente/iniciar", "Iniciar")}>▶ Iniciar</button>
            <button className="boton ambar" disabled={ocupado || ag !== "corriendo"} onClick={() => ejecutar("/api/agente/pausar", "Pausar")}>❚❚ Pausar</button>
            <BotonConfirmar texto="■ Detener" clase="rojo" deshabilitado={ocupado || ag === "detenido"}
              pregunta="¿Detener? Se bloquean nuevas órdenes; las posiciones se conservan." alConfirmar={() => ejecutar("/api/agente/detener", "Detener")} />
            <button className="boton azul" disabled={ocupado || ag !== "corriendo"} onClick={() => ejecutar("/api/ciclo", "Ciclo")}>⟳ Ejecutar ciclo ahora</button>
            <BotonConfirmar texto="Liquidar posiciones" deshabilitado={ocupado || ag === "corriendo"}
              pregunta="¿Vender todas las posiciones Paper al último cierre?" alConfirmar={() => ejecutar("/api/agente/liquidar", "Liquidar")} />
            <BotonConfirmar texto="Rearmar control de pérdida" deshabilitado={ocupado}
              pregunta="¿Quitar el bloqueo de compras por pérdida diaria?" alConfirmar={() => ejecutar("/api/riesgo/rearmar", "Rearmar")} />
            {activos && activos.activos.length > 1 && <BotonRearmarTodos alTerminar={recargar} />}
          </div>
          <div className="tenue chico" style={{ marginTop: 10 }}>
            Motivo: {estado.agente.motivo} · actualizado {hace(estado.agente.actualizado_utc)} · errores consecutivos: {estado.agente.errores_consecutivos} ·
            próximo ciclo automático: <span className="mono">{horaLocal(estado.proximo_ciclo_utc)}</span> (cierre diario 00:00 UTC + 5 min)
          </div>
          {mensaje && <div className={`aviso ${mensaje.tipo}`} style={{ marginTop: 12, marginBottom: 0 }}>{mensaje.texto}</div>}
        </Tarjeta>
      )}

      {!c ? (
        <div className="aviso azul" style={{ marginTop: 14 }}>
          {modo === "vivo" ? "Todavía no hay ciclos en vivo. Pulsa Iniciar: el agente procesará la última vela cerrada en el siguiente minuto y después una vez al día."
            : "No hay ciclos de replay."}
        </div>
      ) : (
        <>
          <div className="seccion">Observación · vela {c.fecha_vela}</div>
          <div className="rejilla r6">
            <Kpi valor={precio(o!.cierre)} etiqueta={`Cierre ${estado.activo}`} sub={`vela ${c.fecha_vela} (UTC)`} />
            <Kpi valor={pct(o!.pronostico, 3)} etiqueta="Pronóstico LSTM t+1" sub={`umbral δ ${pct(o!.delta, 4, false)}`}
              clase={o!.pronostico > o!.delta ? "positivo" : ""} />
            <Kpi valor={precio(o!.sma20)} etiqueta="SMA20" sub={o!.cierre_sobre_sma20 ? "cierre por encima" : `cierre por debajo (${pct(o!.dist_sma20)})`}
              clase={o!.cierre_sobre_sma20 ? "positivo" : "negativo"} />
            <Kpi valor={pct(o!.vol20, 2, false)} etiqueta="Volatilidad 20 d" sub="desv. est. de 20 rendimientos" />
            <Kpi valor={<span className={`accion ${senalDe(o!) === "comprar" ? "COMPRAR" : "MANTENER"}`} style={{ fontSize: 16 }}>{senalDe(o!)}</span>}
              etiqueta={`Señal estrategia ${o!.estrategia ?? estado.estrategia}`} sub={REGLAS[o!.estrategia ?? estado.estrategia]} />
            <Kpi valor={`${num(c.latencia_llm_s, 1)} s`} etiqueta="Latencia LLM" sub={`ciclo total ${num(c.latencia_total_s, 1)} s · ${c.modelo_llm}`} />
          </div>

          {decLlm && (
            <>
              <div className="seccion">Propuesta del LLM y controles de riesgo</div>
              <Tarjeta>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span className="tenue">Llama propuso</span><Acc a={decLlm.propuesta} />
                  <span className="flecha">→ motor de riesgo →</span><Acc a={decLlm.accion_final} />
                  <span className={`chip ${decLlm.aprobada ? "verde" : "ambar"}`}>{decLlm.aprobada ? "aprobada" : "modificada por riesgo"}</span>
                  {decLlm.detalle_llm?.herramientas?.map((h) => <span key={h.herramienta} className={`chip ${h.permitida ? "" : "rojo"}`}>herramienta: {h.herramienta}</span>)}
                </div>
                <p className="justif">“{decLlm.justificacion}”</p>
                {decLlm.motivos.length > 0 && <ul className="motivos">{decLlm.motivos.map((m) => <li key={m}>{m}</li>)}</ul>}
                {decLlm.detalle_llm?.avisos?.length ? <div className="aviso" style={{ marginTop: 10, marginBottom: 0 }}>Avisos de validación: {decLlm.detalle_llm.avisos.join(" · ")}</div> : null}
              </Tarjeta>
            </>
          )}
        </>
      )}

      <div className="seccion">Límites de riesgo (configuración; el LLM no puede cambiarlos)</div>
      <div className="rejilla r4">
        <Kpi valor={pct(estado.riesgo.exposicion_maxima, 0, false)} etiqueta="Exposición máxima" sub={`del patrimonio en ${estado.activo_base} · sin apalancamiento`} />
        <Kpi valor={`−${pct(estado.riesgo.perdida_diaria_maxima, 0, false)}`} etiqueta="Pérdida diaria máxima" sub="bloquea compras hasta rearme manual" />
        <Kpi valor={`${estado.riesgo.stop_movil_k_vol} × vol20`} etiqueta="Stop móvil" sub="solo sube; venta forzada al perforarlo" />
        <Kpi valor={`${estado.riesgo.antiguedad_maxima_horas} h`} etiqueta="Antigüedad máxima del dato" sub="si se supera, el agente se pausa" />
      </div>
    </>
  );
}
