import { useState } from "react";
import { useConsulta } from "../api";
import { Acc, BotonRearmarTodos, MensajeError, Tarjeta } from "../componentes/Ui";
import { hace, num, pct, precio, usdt } from "../formato";
import { NOMBRES_CARTERA, type Decision, type Estado, type Modo, type Orden } from "../tipos";

// ---------------------------------------------------------------- tipos de /api/operaciones (v1.8)
interface Abierta {
  simbolo: string; activo_base: string; cartera: string; lado: string; cantidad: number; precio_entrada: number | null;
  fecha_compra: string | null; motivo_entrada: string; invertido: number; ultimo_cierre: number | null; fecha_ultimo_cierre: string | null;
  precio_actual: number | null; stop: number | null; distancia_stop: number | null; pnl: number | null; pnl_pct: number | null;
  pnl_actual: number | null; pnl_actual_pct: number | null; dias: number | null; senal_hoy: string | null;
}
interface Cerrada {
  simbolo: string; activo_base: string; fecha_compra: string; precio_compra: number; cantidad: number; fecha_venta: string;
  precio_venta: number; motivo_entrada: string; motivo_salida: string; dias: number; pnl: number; pnl_pct: number | null; comisiones: number;
}
interface PorActivo {
  simbolo: string; activo_base: string; estrategia: string; estado_agente: string; errores_consecutivos: number; ultima_vela: string | null;
  ultimo_cierre: number | null; senal_hoy: string | null; patrimonio: number; efectivo: number; invertido: number;
  variacion_dia: number | null; bloqueo_perdida: boolean;
}
interface ResumenOps {
  modo: string; cartera: string; n_activos: number; capital_por_activo: number; capital_inicial_total: number; saldo_total: number;
  pnl_total: number; rendimiento: number | null; efectivo_total: number; invertido_total: number; pnl_realizado: number;
  pnl_no_realizado: number; saldo_total_actual: number; pnl_no_realizado_actual: number | null; precios_actuales_disponibles: boolean;
  precios_actuales_utc: string | null; max_drawdown: number; operaciones_cerradas: number; ganadoras: number; acierto: number | null;
  profit_factor: number | null; sin_perdidas: boolean; comisiones: number;
  riesgo: { perdida_diaria_maxima: number; peor_variacion_dia: number | null; peor_activo_dia: string | null; exposicion: number;
    exposicion_maxima: number; activos_con_bloqueo: string[]; bloqueados_todas_carteras: Record<string, string[]>; activos_pausados: string[]; stops_cercanos: string[]; stop_movil_k_vol: number };
  abiertas: Abierta[]; cerradas: Cerrada[]; por_activo: PorActivo[];
  comparacion: Record<string, { saldo_total: number; pnl_total: number; rendimiento: number | null; posiciones_abiertas: number }>;
  paper: { capital_inicial: number; costo_compra: number; costo_venta: number; deslizamiento: number };
}

const CARTERAS = ["sin_llm", "con_llm", "comprar_y_mantener"] as const;
// Nombres para la vista de todos los activos (cada activo usa su estrategia C o D).
const NOMBRE_TOTAL: Record<string, string> = { sin_llm: "Sin LLM · estrategia C/D", con_llm: "Con LLM · agente", comprar_y_mantener: "Comprar y mantener" };
const signo = (v: number | null | undefined) => (v == null ? "" : v > 0 ? "positivo" : v < 0 ? "negativo" : "");

function Barra({ etiqueta, valor, fraccion, detalle }: { etiqueta: string; valor: string; fraccion: number; detalle?: string }) {
  const f = Math.max(0, Math.min(1, fraccion));
  const color = f >= 0.85 ? "var(--rojo)" : f >= 0.6 ? "var(--ambar)" : "var(--verde)";
  return (
    <div className="barra-riesgo">
      <div className="fila"><span>{etiqueta}</span><span className="mono">{valor}</span></div>
      <div className="pista"><span style={{ width: `${f * 100}%`, background: color }} /></div>
      {detalle && <div className="tenue chico">{detalle}</div>}
    </div>
  );
}

function Dato({ valor, etiqueta, clase }: { valor: React.ReactNode; etiqueta: string; clase?: string }) {
  return <div className="dato"><div className={`v mono ${clase ?? ""}`}>{valor}</div><div className="e">{etiqueta}</div></div>;
}

function Reglas({ cartera, r }: { cartera: string; r: ResumenOps }) {
  const k = r.riesgo.stop_movil_k_vol;
  const entrada: Record<string, string> = {
    sin_llm: "Compra cuando la señal del modelo de ese activo es «comprar»: pronóstico > δ (estrategia C), y además cierre > SMA20 si el activo usa la estrategia D.",
    con_llm: "Compra cuando el LLM propone COMPRAR y el motor de riesgo lo aprueba (no hay posición abierta y no hay bloqueo por pérdida diaria).",
    comprar_y_mantener: "Compra en el primer ciclo de cada activo y no vuelve a operar. Es la referencia pasiva, sin controles de riesgo.",
  };
  const salida: Record<string, string> = {
    sin_llm: `Vende cuando la señal pasa a «efectivo», o antes si el cierre cae debajo del stop móvil (cierre × (1 − ${k} × vol20), solo sube).`,
    con_llm: `Vende cuando el LLM propone VENDER, o forzado por el stop móvil (cierre × (1 − ${k} × vol20), solo sube) aunque el LLM proponga mantener.`,
    comprar_y_mantener: "Nunca vende.",
  };
  return (
    <Tarjeta titulo={`Cómo opera esta cartera · ${NOMBRE_TOTAL[cartera]}`}>
      <table className="tabla reglas"><tbody>
        <tr><td className="tenue">Entrada</td><td>{entrada[cartera]}</td></tr>
        <tr><td className="tenue">Salida</td><td>{salida[cartera]}</td></tr>
        <tr><td className="tenue">Tamaño</td><td>Solo compras (LONG), sin apalancamiento: hasta {pct(r.riesgo.exposicion_maxima, 0, false)} del patrimonio de la cartera de ese activo
          ({usdt(r.capital_por_activo, 0)} USDT iniciales por activo, {r.n_activos} activos).</td></tr>
        <tr><td className="tenue">Cuándo</td><td>Una vez al día: la señal se calcula al cierre diario (00:00 UTC) y se ejecuta a ese precio, que en MEXC es la apertura del día siguiente.
          Costo por operación {pct(r.paper.costo_compra, 2, false)}; deslizamiento {pct(r.paper.deslizamiento, 2, false)}.</td></tr>
        {cartera !== "comprar_y_mantener" && <tr><td className="tenue">Límite diario</td><td>Si el patrimonio de un activo cae {pct(r.riesgo.perdida_diaria_maxima, 0, false)} o más entre dos cierres, se bloquean
          nuevas compras de ese activo hasta que el usuario lo rearme. Regla de operación (desde el 20 nov): después de cada ciclo se rearman
          todos los activos bloqueados con «Rearmar todos los bloqueados», así que el bloqueo frena las compras del día de la caída. Las ventas siguen permitidas.</td></tr>}
      </tbody></table>
    </Tarjeta>
  );
}

export default function Operaciones({ modo, estado }: { modo: Modo; estado: Estado | null }) {
  const [cartera, setCartera] = useState<string>("con_llm");
  const [filtro, setFiltro] = useState("todas");
  const op = useConsulta<ResumenOps>(`/api/operaciones?modo=${modo}&cartera=${cartera}`, 30_000);
  const dec = useConsulta<Decision[]>(`/api/decisiones?modo=${modo}&limite=300`, 15_000);
  const ord = useConsulta<Orden[]>(`/api/ordenes?modo=${modo}&limite=300`, 15_000);
  const decisiones = (dec.datos ?? []).filter((d) => filtro === "todas" || d.cartera === filtro);
  const ordenes = (ord.datos ?? []).filter((o) => filtro === "todas" || o.cartera === filtro);
  const r = op.datos;

  return (
    <>
      <MensajeError mensaje={op.error ?? dec.error ?? ord.error} />

      {/* ------------------------------------------------ modo y cartera */}
      <div className="tarjeta modo-trading">
        <div>
          <div className="tenue chico" style={{ letterSpacing: 1.2, fontWeight: 700 }}>MODO DE TRADING</div>
          <div className="titulo-modo">PAPER TRADING</div>
          <div className="chico tenue">Precios reales de MEXC · órdenes simuladas con saldo ficticio · {modo === "vivo" ? "conexión actual" : "replay histórico"}</div>
        </div>
        <span className="chip rojo">Órdenes reales bloqueadas · simulador Paper propio</span>
        <span className="separa" />
        <div className="selector-carteras">
          {CARTERAS.map((c) => {
            const k = r?.comparacion?.[c];
            return (
              <button key={c} className={cartera === c ? "activo" : ""} onClick={() => setCartera(c)}>
                <span className="n">{NOMBRE_TOTAL[c]}</span>
                {k && <span className="mono s">{usdt(k.saldo_total, 0)} <span className={signo(k.pnl_total)}>({pct(k.rendimiento, 2)})</span></span>}
                {k && <span className="tenue chico">{k.posiciones_abiertas} posiciones abiertas</span>}
              </button>
            );
          })}
        </div>
      </div>

      {r && (
        <>
          {/* ------------------------------------------------ rendimiento y riesgo */}
          <div className="rejilla ops-arriba">
            <Tarjeta titulo={`Rendimiento · ${NOMBRE_TOTAL[cartera]} · ${r.n_activos} activos`}>
              <div className="saldo-grande">
                <div className="mono v">{usdt(r.saldo_total, 2)} <span className="chico tenue">USDT</span></div>
                <div className="chico tenue">Saldo total al último cierre (capital inicial {usdt(r.capital_inicial_total, 0)} = {r.n_activos} × {usdt(r.capital_por_activo, 0)})</div>
                <div className={`mono ${signo(r.pnl_total)}`} style={{ fontSize: 18, marginTop: 4 }}>{r.pnl_total >= 0 ? "+" : ""}{usdt(r.pnl_total, 2)} USDT · {pct(r.rendimiento, 2)}</div>
              </div>
              <div className="datos">
                <Dato valor={usdt(r.efectivo_total, 0)} etiqueta="Efectivo disponible" />
                <Dato valor={usdt(r.invertido_total, 0)} etiqueta="Invertido (valor al cierre)" />
                <Dato valor={`${r.pnl_realizado >= 0 ? "+" : ""}${usdt(r.pnl_realizado, 2)}`} etiqueta="PnL realizado (cerradas)" clase={signo(r.pnl_realizado)} />
                <Dato valor={`${r.pnl_no_realizado >= 0 ? "+" : ""}${usdt(r.pnl_no_realizado, 2)}`} etiqueta="PnL no realizado (al cierre)" clase={signo(r.pnl_no_realizado)} />
                <Dato valor={r.pnl_no_realizado_actual == null ? "—" : `${r.pnl_no_realizado_actual >= 0 ? "+" : ""}${usdt(r.pnl_no_realizado_actual, 2)}`}
                  etiqueta={`No realizado a precio actual${r.precios_actuales_utc ? ` (${hace(r.precios_actuales_utc)})` : ""}`} clase={signo(r.pnl_no_realizado_actual)} />
                <Dato valor={pct(r.max_drawdown, 2)} etiqueta="Drawdown máximo" clase={r.max_drawdown < 0 ? "negativo" : ""} />
                <Dato valor={`${r.operaciones_cerradas} (${r.ganadoras} ganadoras)`} etiqueta="Operaciones cerradas" />
                <Dato valor={pct(r.acierto, 0, false)} etiqueta="Acierto (win rate)" />
                <Dato valor={r.profit_factor == null ? (r.sin_perdidas ? "sin pérdidas" : "—") : num(r.profit_factor, 2)} etiqueta="Profit factor" />
                <Dato valor={usdt(r.comisiones, 2)} etiqueta="Comisiones pagadas" />
              </div>
            </Tarjeta>

            <Tarjeta titulo="Riesgo (límites deterministas)">
              {cartera === "comprar_y_mantener" && <div className="aviso azul chico">Esta cartera es la referencia pasiva: no tiene stop ni límite diario. Los valores son solo informativos.</div>}
              <Barra etiqueta="Pérdida diaria (peor activo)" valor={`${r.riesgo.peor_variacion_dia == null ? "—" : pct(Math.min(0, r.riesgo.peor_variacion_dia), 2)} / −${pct(r.riesgo.perdida_diaria_maxima, 0, false)}`}
                fraccion={r.riesgo.peor_variacion_dia == null ? 0 : Math.max(0, -r.riesgo.peor_variacion_dia) / r.riesgo.perdida_diaria_maxima}
                detalle={r.riesgo.peor_activo_dia ? `${r.riesgo.peor_activo_dia}, último cierre. Al llegar al límite se bloquean sus compras.` : "Sin dos cierres todavía."} />
              <Barra etiqueta="Exposición (invertido / saldo)" valor={`${pct(r.riesgo.exposicion, 1, false)} / ${pct(r.riesgo.exposicion_maxima, 0, false)}`}
                fraccion={r.riesgo.exposicion / r.riesgo.exposicion_maxima} detalle="Máximo por activo: todo su patrimonio, sin apalancamiento." />
              <Barra etiqueta="Activos con compras bloqueadas" valor={`${r.riesgo.activos_con_bloqueo.length} / ${r.n_activos}`}
                fraccion={r.riesgo.activos_con_bloqueo.length / Math.max(1, r.n_activos)} detalle={r.riesgo.activos_con_bloqueo.join(", ") || "Ninguno."} />
              {modo === "vivo" && (
                <div className="botones" style={{ margin: "-4px 0 14px" }}>
                  <BotonRearmarTodos bloqueados={Object.keys(r.riesgo.bloqueados_todas_carteras ?? {})} alTerminar={op.recargar} />
                  <span className="tenue chico">
                    {Object.keys(r.riesgo.bloqueados_todas_carteras ?? {}).length
                      ? `Bloqueados en cualquier cartera: ${Object.entries(r.riesgo.bloqueados_todas_carteras).map(([k, v]) => `${k.replace(/USDT$/, "")} (${v.map((x) => x === "sin_llm" ? "sin LLM" : "con LLM").join(", ")})`).join(" · ")}`
                      : "Ningún activo tiene el bloqueo activo."}
                    {" "}Regla de operación: se rearman todos al día siguiente del bloqueo.
                  </span>
                </div>
              )}
              <Barra etiqueta="Agentes en pausa o detenidos" valor={`${r.riesgo.activos_pausados.length} / ${r.n_activos}`}
                fraccion={r.riesgo.activos_pausados.length / Math.max(1, r.n_activos)} detalle={r.riesgo.activos_pausados.join(", ") || "Todos corriendo."} />
              <Barra etiqueta="Posiciones a menos de 2 % del stop" valor={`${r.riesgo.stops_cercanos.length} / ${r.abiertas.length}`}
                fraccion={r.riesgo.stops_cercanos.length / Math.max(1, r.abiertas.length)} detalle={r.riesgo.stops_cercanos.join(", ") || "Ninguna."} />
            </Tarjeta>
          </div>

          {/* ------------------------------------------------ posiciones abiertas */}
          <div className="seccion">Posiciones abiertas · {NOMBRE_TOTAL[cartera]} ({r.abiertas.length})</div>
          <Tarjeta>
            <div className="desplaza">
              <table className="tabla ops">
                <thead><tr>
                  <th>Activo</th><th>Lado</th><th>Compra (vela)</th><th className="der">Cantidad</th><th className="der">Precio de entrada</th>
                  <th className="der">Invertido USDT</th><th className="der">Último cierre</th><th className="der">Precio actual MEXC</th>
                  <th className="der">Stop móvil</th><th className="der">Distancia al stop</th><th className="der">PnL al cierre</th>
                  <th className="der">PnL a precio actual</th><th className="der">Días</th><th>Señal hoy</th>
                </tr></thead>
                <tbody>
                  {r.abiertas.map((a) => (
                    <tr key={a.simbolo}>
                      <td className="mono"><b>{a.simbolo}</b></td>
                      <td><span className="chip verde">{a.lado}</span></td>
                      <td className="mono">{a.fecha_compra ?? "—"}</td>
                      <td className="der mono">{a.cantidad.toLocaleString("es-MX", { maximumFractionDigits: 6 })} {a.activo_base}</td>
                      <td className="der mono">{precio(a.precio_entrada)}</td>
                      <td className="der mono">{usdt(a.invertido, 2)}</td>
                      <td className="der mono">{precio(a.ultimo_cierre)}</td>
                      <td className="der mono">{precio(a.precio_actual)}</td>
                      <td className="der mono">{a.stop == null ? "—" : precio(a.stop)}</td>
                      <td className={`der mono ${a.distancia_stop != null && a.distancia_stop < 0.02 ? "negativo" : ""}`}>{pct(a.distancia_stop, 2, false)}</td>
                      <td className={`der mono ${signo(a.pnl)}`}>{a.pnl == null ? "—" : `${a.pnl >= 0 ? "+" : ""}${usdt(a.pnl, 2)}`}<div className="chico">{pct(a.pnl_pct, 2)}</div></td>
                      <td className={`der mono ${signo(a.pnl_actual)}`}>{a.pnl_actual == null ? "—" : `${a.pnl_actual >= 0 ? "+" : ""}${usdt(a.pnl_actual, 2)}`}<div className="chico">{pct(a.pnl_actual_pct, 2)}</div></td>
                      <td className="der mono">{a.dias ?? "—"}</td>
                      <td>{a.senal_hoy ? <span className={`accion ${a.senal_hoy === "comprar" ? "COMPRAR" : "MANTENER"}`}>{a.senal_hoy}</span> : "—"}</td>
                    </tr>
                  ))}
                  {!r.abiertas.length && <tr><td colSpan={14} className="tenue">Esta cartera no tiene posiciones abiertas: todo su saldo está en efectivo.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="tenue chico" style={{ marginTop: 8 }}>
              El patrimonio oficial se valúa al último cierre diario, que es el precio con el que decide y ejecuta el agente. El «precio actual» de MEXC
              {r.precios_actuales_disponibles ? ` (consultado ${hace(r.precios_actuales_utc)})` : " (no disponible ahora)"} solo es informativo.
              «Señal hoy» es la señal del modelo en el último ciclo; en la cartera con LLM la decisión final la propone el LLM.
            </div>
          </Tarjeta>

          {/* ------------------------------------------------ historial */}
          <div className="seccion">Historial de operaciones cerradas · {NOMBRE_TOTAL[cartera]} ({r.cerradas.length})</div>
          <Tarjeta>
            <div className="desplaza" style={{ maxHeight: 420 }}>
              <table className="tabla ops">
                <thead><tr>
                  <th>Activo</th><th>Compra (vela)</th><th className="der">Precio de compra</th><th>Venta (vela)</th><th className="der">Precio de venta</th>
                  <th className="der">Cantidad</th><th className="der">Días</th><th>Motivo de salida</th><th className="der">PnL USDT</th><th className="der">PnL %</th>
                </tr></thead>
                <tbody>
                  {r.cerradas.map((t, i) => (
                    <tr key={`${t.simbolo}${t.fecha_venta}${i}`}>
                      <td className="mono"><b>{t.simbolo}</b></td>
                      <td className="mono">{t.fecha_compra}</td><td className="der mono">{precio(t.precio_compra)}</td>
                      <td className="mono">{t.fecha_venta}</td><td className="der mono">{precio(t.precio_venta)}</td>
                      <td className="der mono">{t.cantidad.toLocaleString("es-MX", { maximumFractionDigits: 6 })} {t.activo_base}</td>
                      <td className="der mono">{t.dias}</td>
                      <td><span className={`chip ${t.motivo_salida === "stop móvil" ? "rojo" : t.motivo_salida === "liquidación manual" ? "ambar" : ""}`}>{t.motivo_salida}</span></td>
                      <td className={`der mono ${signo(t.pnl)}`}>{t.pnl >= 0 ? "+" : ""}{usdt(t.pnl, 2)}</td>
                      <td className={`der mono ${signo(t.pnl)}`}>{pct(t.pnl_pct, 2)}</td>
                    </tr>
                  ))}
                  {!r.cerradas.length && <tr><td colSpan={10} className="tenue">Todavía no hay operaciones cerradas (compra y venta) en esta cartera.</td></tr>}
                </tbody>
              </table>
            </div>
          </Tarjeta>

          {/* ------------------------------------------------ saldo por activo */}
          <div className="seccion">Saldo por activo · {NOMBRE_TOTAL[cartera]}</div>
          <Tarjeta>
            <div className="desplaza" style={{ maxHeight: 420 }}>
              <table className="tabla ops">
                <thead><tr>
                  <th>Activo</th><th>Agente</th><th>Estrategia</th><th>Última vela</th><th className="der">Cierre</th><th>Señal</th><th>Posición</th>
                  <th className="der">Efectivo</th><th className="der">Invertido</th><th className="der">Patrimonio</th><th className="der">Desde el inicio</th><th className="der">Último día</th><th>Bloqueo</th>
                </tr></thead>
                <tbody>
                  {r.por_activo.map((x) => (
                    <tr key={x.simbolo}>
                      <td className="mono"><b>{x.simbolo}</b></td>
                      <td><span className={`chip ${x.estado_agente === "corriendo" ? "verde" : x.estado_agente === "pausado" ? "ambar" : "rojo"}`}>{x.estado_agente}</span></td>
                      <td className="chico">{x.estrategia === "D" ? "D · con filtro SMA20" : "C · sin filtro"}</td>
                      <td className="mono">{x.ultima_vela ?? <span className="tenue">sin ciclos</span>}</td>
                      <td className="der mono">{precio(x.ultimo_cierre)}</td>
                      <td>{x.senal_hoy ?? "—"}</td>
                      <td>{x.invertido > 0 ? <span className="chip verde">LONG</span> : <span className="tenue">efectivo</span>}</td>
                      <td className="der mono">{usdt(x.efectivo, 2)}</td>
                      <td className="der mono">{usdt(x.invertido, 2)}</td>
                      <td className="der mono"><b>{usdt(x.patrimonio, 2)}</b></td>
                      <td className={`der mono ${signo(x.patrimonio - r.capital_por_activo)}`}>{pct(x.patrimonio / r.capital_por_activo - 1, 2)}</td>
                      <td className={`der mono ${signo(x.variacion_dia)}`}>{pct(x.variacion_dia, 2)}</td>
                      <td>{x.bloqueo_perdida ? <span className="chip rojo">compras bloqueadas</span> : <span className="tenue">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Tarjeta>

          <div className="seccion">Reglas</div>
          <Reglas cartera={cartera} r={r} />
        </>
      )}
      {!r && !op.error && <div className="tenue">Cargando…</div>}

      {/* ------------------------------------------------ detalle del activo seleccionado (como antes) */}
      <div className="seccion">Detalle por ciclo · {estado?.activo ?? ""}</div>
      <div className="botones" style={{ marginBottom: 14 }}>
        <span className="selector">
          {["todas", ...Object.keys(NOMBRES_CARTERA)].map((n) => (
            <button key={n} className={filtro === n ? "activo" : ""} onClick={() => setFiltro(n)}>{n === "todas" ? "Todas" : NOMBRES_CARTERA[n]}</button>
          ))}
        </span>
        <span className="chip">{decisiones.length} decisiones</span>
        <span className="chip ambar">{(dec.datos ?? []).filter((d) => !d.aprobada).length} modificadas por riesgo</span>
        <span className="chip">{ordenes.filter((o) => o.estado === "ejecutada").length} órdenes ejecutadas</span>
      </div>

      <Tarjeta titulo={`Decisiones por ciclo · ${estado?.activo ?? ""} (${modo})`}>
        <div className="desplaza" style={{ maxHeight: 460 }}>
          <table className="tabla">
            <thead><tr><th>Vela</th><th>Cartera</th><th>Propuesta → final</th><th>Motivos del motor de riesgo</th><th>Justificación</th><th className="der">LLM</th></tr></thead>
            <tbody>
              {decisiones.map((d) => (
                <tr key={d.id}>
                  <td className="mono">{d.fecha_vela}</td>
                  <td>{NOMBRES_CARTERA[d.cartera]}</td>
                  <td style={{ whiteSpace: "nowrap" }}><Acc a={d.propuesta} />{d.propuesta !== d.accion_final && <><span className="flecha">→</span><Acc a={d.accion_final} /></>}</td>
                  <td>{d.motivos.length ? <ul className="motivos" style={{ margin: 0 }}>{d.motivos.map((m) => <li key={m}>{m}</li>)}</ul> : <span className="tenue">—</span>}</td>
                  <td className="justif" style={{ maxWidth: 520 }}>{d.justificacion}
                    {d.detalle_llm?.avisos?.length ? <div className="chico" style={{ color: "var(--ambar)" }}>⚠ {d.detalle_llm.avisos.join(" · ")}</div> : null}</td>
                  <td className="der mono">{d.cartera === "con_llm" ? `${num(d.latencia_llm_s, 1)} s` : ""}</td>
                </tr>
              ))}
              {!decisiones.length && <tr><td colSpan={6} className="tenue">Sin decisiones registradas.</td></tr>}
            </tbody>
          </table>
        </div>
      </Tarjeta>

      <div className="seccion">Órdenes Paper · {estado?.activo ?? ""}</div>
      <Tarjeta>
        <div className="desplaza" style={{ maxHeight: 400 }}>
          <table className="tabla">
            <thead><tr><th>Vela</th><th>Cartera</th><th>Lado</th><th>Estado</th><th className="der">Cantidad {estado?.activo_base ?? ""}</th><th className="der">Precio</th><th className="der">Monto USDT</th><th className="der">Costo</th><th>Motivo</th></tr></thead>
            <tbody>
              {ordenes.map((o) => (
                <tr key={o.id}>
                  <td className="mono">{o.fecha_vela}</td><td>{NOMBRES_CARTERA[o.cartera]}</td><td><Acc a={o.lado} /></td>
                  <td><span className={`chip ${o.estado === "ejecutada" ? "verde" : "rojo"}`}>{o.estado}</span></td>
                  <td className="der mono">{o.cantidad?.toFixed(6)}</td><td className="der mono">{precio(o.precio)}</td>
                  <td className="der mono">{usdt(o.monto)}</td><td className="der mono">{usdt(o.costo)}</td><td className="chico">{o.motivo}</td>
                </tr>
              ))}
              {!ordenes.length && <tr><td colSpan={9} className="tenue">Sin órdenes.</td></tr>}
            </tbody>
          </table>
        </div>
      </Tarjeta>
    </>
  );
}
