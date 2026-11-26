import { useConsulta } from "../api";
import { GraficaLineas } from "../componentes/Graficas";
import { MensajeError, Tarjeta } from "../componentes/Ui";
import { num, pct, usdt } from "../formato";
import { COLOR_CARTERA, NOMBRES_CARTERA, type Estado, type Metricas, type Modo } from "../tipos";

interface FilaPatrimonio { cartera: string; fecha_vela: string; patrimonio: number }

export default function Estrategia({ modo, estado }: { modo: Modo; estado: Estado | null }) {
  const met = useConsulta<Metricas>(`/api/metricas?modo=${modo}`, 30_000);
  const pat = useConsulta<FilaPatrimonio[]>(`/api/patrimonio?modo=${modo}`, 30_000);
  const m = met.datos;
  const fechas = Array.from(new Set((pat.datos ?? []).map((p) => p.fecha_vela))).sort();
  const series = Object.keys(NOMBRES_CARTERA).map((n) => {
    const mapa = new Map((pat.datos ?? []).filter((p) => p.cartera === n).map((p) => [p.fecha_vela, p.patrimonio]));
    return { nombre: NOMBRES_CARTERA[n], valores: fechas.map((f) => mapa.get(f) ?? null), color: COLOR_CARTERA[n], grosor: n === "con_llm" ? 2.6 : 2 };
  });
  const carteras = Object.keys(NOMBRES_CARTERA).filter((n) => m?.carteras[n]);
  const mejor = carteras.length ? carteras.reduce((a, b) => (m!.carteras[a].rendimiento_neto >= m!.carteras[b].rendimiento_neto ? a : b)) : null;
  const sin = m?.carteras.sin_llm, con = m?.carteras.con_llm;

  return (
    <>
      <MensajeError mensaje={met.error ?? pat.error} />
      <Tarjeta titulo={`${estado?.activo ?? ""} · patrimonio (${modo}) · capital inicial ${usdt(m?.capital_inicial ?? estado?.paper.capital_inicial ?? null, 0)} USDT`}
        extra={m?.periodo.desde ? <span className="chip mono">{m.periodo.desde} → {m.periodo.hasta} · {m.periodo.ciclos} ciclos</span> : null}>
        {fechas.length >= 2 ? <GraficaLineas etiquetas={fechas} series={series} alto={320} formato={(x) => usdt(x, 0)} lineaBase={m?.capital_inicial} />
          : <div className="tenue">Se necesitan al menos dos ciclos para la curva.</div>}
      </Tarjeta>

      <div className="seccion">Comparación con el mismo periodo, precios y costos</div>
      <Tarjeta>
        <table className="tabla">
          <thead><tr><th>Métrica</th>{carteras.map((n) => <th key={n} className="der" style={{ color: COLOR_CARTERA[n] }}>{NOMBRES_CARTERA[n]}</th>)}</tr></thead>
          <tbody>
            {[
              ["Rendimiento neto", (n: string) => pct(m!.carteras[n].rendimiento_neto)],
              ["Patrimonio final", (n: string) => usdt(m!.carteras[n].patrimonio_final)],
              ["Drawdown máximo", (n: string) => pct(m!.carteras[n].max_drawdown)],
              ["Win Rate (operaciones cerradas)", (n: string) => m!.carteras[n].win_rate == null ? "sin cerradas" : pct(m!.carteras[n].win_rate, 0, false)],
              ["Operaciones ejecutadas", (n: string) => String(m!.carteras[n].operaciones)],
              ["Operaciones cerradas", (n: string) => String(m!.carteras[n].operaciones_cerradas)],
              ["Acciones rechazadas o modificadas", (n: string) => String(m!.carteras[n].acciones_rechazadas)],
              ["Órdenes rechazadas (saldo/mínimo)", (n: string) => String(m!.carteras[n].ordenes_rechazadas)],
              ["Ciclos", (n: string) => String(m!.carteras[n].ciclos)],
            ].map(([etq, f]) => (
              <tr key={etq as string}><td className="tenue">{etq as string}</td>{carteras.map((n) => <td key={n} className="der mono">{(f as (n: string) => string)(n)}</td>)}</tr>
            ))}
            <tr><td className="tenue">Latencia LLM media / máxima</td>{carteras.map((n) => <td key={n} className="der mono">{n === "con_llm" ? `${num(m?.latencia_llm_s.media, 1)} / ${num(m?.latencia_llm_s.maxima, 1)} s` : "—"}</td>)}</tr>
            <tr><td className="tenue">Motivos de rechazo</td>{carteras.map((n) => <td key={n} className="der chico">{Object.entries(m!.carteras[n].motivos_rechazo).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—"}</td>)}</tr>
          </tbody>
        </table>
        {!carteras.length && <div className="tenue">Sin ciclos en este modo.</div>}
      </Tarjeta>

      {sin && con && (
        <div className={`aviso ${con.rendimiento_neto > sin.rendimiento_neto ? "azul" : ""}`} style={{ marginTop: 14 }}>
          <b>¿El LLM aporta valor?</b> En este periodo la cartera con LLM obtuvo {pct(con.rendimiento_neto)} frente a {pct(sin.rendimiento_neto)} de la
          estrategia sin LLM ({con.rendimiento_neto > sin.rendimiento_neto ? "mejor" : con.rendimiento_neto < sin.rendimiento_neto ? "peor" : "igual"}),
          con drawdown {pct(con.max_drawdown)} vs {pct(sin.max_drawdown)}. Mejor cartera: {mejor ? NOMBRES_CARTERA[mejor] : "—"}.
          Con pocos ciclos la diferencia no es estadísticamente concluyente.
        </div>
      )}

      <div className="seccion">Definición de las estrategias</div>
      <div className="rejilla r3">
        <Tarjeta titulo={NOMBRES_CARTERA.sin_llm}>
          {estado?.estrategia === "C" ? (
            <p className="justif">Compra o mantiene si el pronóstico del ensamble LSTM ({estado.modelo.neuronas} neuronas) supera δ = {pct(estado.modelo.delta, 4, false)};
              si no, efectivo. <b>Sin filtro de tendencia</b>: para {estado.activo} la validación (VA) eligió C sobre D. Pasa por el mismo motor de riesgo
              (stop móvil, pérdida diaria, exposición).</p>
          ) : (
            <p className="justif">Compra o mantiene si el pronóstico del ensamble LSTM supera δ = {pct(estado?.modelo.delta ?? null, 4, false)} <b>y</b> el cierre está por
              encima de la SMA20; si no, efectivo. Pasa por el mismo motor de riesgo (stop móvil, pérdida diaria, exposición).</p>
          )}
        </Tarjeta>
        <Tarjeta titulo="Con LLM · agente">
          <p className="justif">{estado?.llm.modelo ?? "Llama"} recibe los indicadores calculados por el backend, puede consultar herramientas de solo lectura y
            responde un JSON (acción, símbolo, fecha de vela, justificación) validado por esquema. Después pasa por el motor de riesgo, que puede rechazarlo.</p>
        </Tarjeta>
        <Tarjeta titulo="Comprar y mantener">
          <p className="justif">Referencia pasiva: compra con todo el capital en el primer ciclo y no vende. Sin controles de riesgo.</p>
        </Tarjeta>
      </div>
      <div className="tenue chico" style={{ marginTop: 12 }}>{estado?.paper.supuesto_ejecucion} Costo de compra {pct(estado?.paper.costo_compra ?? null, 2, false)},
        costo de venta {pct(estado?.paper.costo_venta ?? null, 2, false)}. Paso mínimo {estado?.reglas_par.paso_cantidad} {estado?.activo_base}, monto mínimo {estado?.reglas_par.monto_minimo} USDT
        ({estado?.reglas_par.fuente}).</div>
    </>
  );
}
