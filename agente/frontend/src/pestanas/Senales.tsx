/** v2.2 · Señales de UN activo (el elegido en la barra superior): su acción de hoy, gráficos, indicadores financieros,
 *  la historia de su señal y sus avisos. Sin saldos: el laboratorio no compra; la compra es manual y opcional, en MEXC.
 *  (v2.0–v2.1 mostraba una tabla con los 15 activos; el profesor pidió ver solo el activo con sus gráficos e indicadores.) */
import { useState } from "react";
import { enviar, useConsulta } from "../api";
import { GraficaLineas, type Marcador } from "../componentes/Graficas";
import { Acc, Kpi, MensajeError, Tarjeta } from "../componentes/Ui";
import { hace, horaLocal, pct, precio } from "../formato";
import { resumenIndicadores } from "../indicadores";
import type { Estado, Vela } from "../tipos";

interface Alerta { tipo: string; estado: string; ts_utc?: string }
interface FilaSenal {
  simbolo: string; estado: string; estrategia: string; delta: number; decimales: number;
  fecha_vela?: string; cierre?: number; pronostico?: number; senal?: string; cierre_sobre_sma20?: boolean; dist_sma20?: number;
  accion?: string; motivos?: string[]; senal_activa?: boolean; precio_entrada?: number | null; stop?: number | null; alerta?: Alerta | null;
}
interface EstadoAvisos { estado: string; canal?: string; proveedor?: string; destino?: string | null; avisar_ventas?: boolean; disparador?: string;
  secretos_requeridos?: string[] }
interface RespSenales { senales: FilaSenal[]; avisos: EstadoAvisos; proximo_ciclo_utc: string }
interface FilaAlerta { simbolo: string; fecha_vela: string; tipo: string; estado: string; intentos: number; detalle: string | null; ts_utc: string; texto: string }
interface FilaHist { fecha_vela: string; cierre: number; pronostico: number; delta: number; senal: string; sma20: number; dist_sma20: number;
  vol20: number; accion: string | null; motivos: string[]; aviso: Alerta | null }
interface RespHist { simbolo: string; estrategia: string; delta: number; decimales: number; filas: FilaHist[] }
interface DatosMercado { simbolo: string; velas: Vela[]; ordenes: { fecha_vela: string; cartera: string; lado: "COMPRAR" | "VENDER"; precio: number; motivo: string }[] }

const CLASE_ESTADO: Record<string, string> = { enviada: "verde", fallida: "rojo", sin_configurar: "ambar", deshabilitado: "", activo: "verde" };
const TEXTO_ESTADO: Record<string, string> = { activo: "activos", sin_configurar: "sin configurar", deshabilitado: "deshabilitados", enviada: "enviada", fallida: "falló" };
const signo = (v: number | null | undefined) => (v == null ? "" : v > 0 ? "positivo" : v < 0 ? "negativo" : "");
const lecturaRsi = (r: number | null) => (r == null ? "—" : r >= 70 ? "sobrecompra (≥ 70)" : r <= 30 ? "sobreventa (≤ 30)" : "zona neutral (30–70)");

export default function Senales({ estado }: { estado: Estado | null }) {
  const [dias, setDias] = useState(90);
  const [ocupado, setOcupado] = useState(false);
  const [mensaje, setMensaje] = useState<{ texto: string; tipo: "azul" | "rojo" } | null>(null);
  const s = useConsulta<RespSenales>("/api/senales", 15_000);
  const m = useConsulta<DatosMercado>(`/api/mercado?modo=vivo&limite=${dias + 50}`, 60_000);
  const h = useConsulta<RespHist>("/api/historial_senal?modo=vivo&limite=60", 30_000);
  const n = useConsulta<{ alertas: FilaAlerta[] }>("/api/notificaciones?limite=200", 30_000);

  const activo = estado?.activo ?? "";
  const f = s.datos?.senales.find((x) => x.simbolo === activo);
  const wa = s.datos?.avisos;
  const canal = wa?.canal === "correo" || !wa?.canal ? "correo" : "WhatsApp";
  const hist = h.datos?.filas ?? [];
  const ultimaH = hist[hist.length - 1];
  const avisos = (n.datos?.alertas ?? []).filter((a) => a.simbolo === activo);

  const probar = async () => {
    setOcupado(true);
    try {
      const r = await enviar<{ enviado: boolean; detalle: string }>("/api/notificaciones/prueba");
      setMensaje(r.enviado ? { texto: `Aviso de prueba enviado. Revisa tu ${canal}.`, tipo: "azul" } : { texto: `No se pudo enviar: ${r.detalle}`, tipo: "rojo" });
    } catch (e) {
      setMensaje({ texto: (e as Error).message, tipo: "rojo" });
    } finally {
      setOcupado(false);
    }
  };

  if (!estado || (!f && !s.error)) return <div className="tenue">Cargando la señal del activo…</div>;

  // ---------------- precio e indicadores
  const todas = m.datos?.velas ?? [];
  const ind = todas.length > 20 ? resumenIndicadores(todas) : null;
  const desde = Math.max(0, todas.length - dias);
  const v = todas.slice(desde);
  const etiquetas = v.map((x) => x.fecha);
  const corta = <T,>(a: T[]) => a.slice(desde);
  const idx = new Map(etiquetas.map((d, i) => [d, i]));
  const marcadores: Marcador[] = (m.datos?.ordenes ?? [])
    .filter((o) => o.cartera === "sin_llm" && idx.has(o.fecha_vela))
    .map((o) => ({ indice: idx.get(o.fecha_vela)!, valor: o.precio, tipo: o.lado === "COMPRAR" ? "compra" : "venta",
      texto: `${o.lado === "COMPRAR" ? "Señal de compra" : "Señal de venta"} ${o.fecha_vela} a ${precio(o.precio)} (${o.motivo})` }));
  const pronSup = f?.pronostico != null && f.pronostico > f.delta;
  const ganancia = f?.senal_activa && f.precio_entrada && f.cierre ? f.cierre / f.precio_entrada - 1 : null;
  const aStop = f?.senal_activa && f.stop && f.cierre ? f.stop / f.cierre - 1 : null;
  const usaD = f?.estrategia === "D";

  const filasInd: [string, React.ReactNode, React.ReactNode, string][] = ind ? [
    ["Pronóstico del modelo (día siguiente)", <span className={pronSup ? "positivo" : ""}>{pct(f?.pronostico, 3)}</span>,
      `umbral δ ${pct(f?.delta, 3, false)} · ${pronSup ? "lo supera" : "no lo supera"}`, "Modelo: dispara la señal"],
    ["SMA20", precio(ind.sma20), <span className={signo(ind.dist20)}>{pct(ind.dist20, 1)} del cierre</span>,
      usaD ? "Modelo: filtro de tendencia (estrategia D)" : "Contexto del modelo y del LLM"],
    ["Volatilidad 20 d (diaria)", pct(ultimaH?.vol20 ?? ind.vol20, 2, false), `anualizada ${pct(ind.volAnual, 0, false)}`, "Modelo: define el stop móvil"],
    ["Variación 1 d · 7 d · 30 d", <span><span className={signo(ind.var1)}>{pct(ind.var1, 1)}</span> · <span className={signo(ind.var7)}>{pct(ind.var7, 1)}</span> · <span className={signo(ind.var30)}>{pct(ind.var30, 1)}</span></span>, `en ${dias} d: ${pct(ind.varPeriodo, 1)}`, "Referencia"],
    ["SMA50", precio(ind.sma50), <span className={signo(ind.dist50)}>{pct(ind.dist50, 1)} del cierre</span>, "Referencia"],
    ["Bandas de Bollinger (20, 2)", `${precio(ind.bbInf)} – ${precio(ind.bbSup)}`,
      ind.pctB == null ? "—" : ind.pctB > 1 ? "cierre sobre la banda superior" : ind.pctB < 0 ? "cierre bajo la banda inferior" : `dentro de las bandas (%B ${(ind.pctB * 100).toFixed(0)})`, "Referencia"],
    ["RSI (14)", ind.rsi14 == null ? "—" : ind.rsi14.toFixed(1), lecturaRsi(ind.rsi14), "Referencia"],
    ["ATR (14)", precio(ind.atr14), `${pct(ind.atrPct, 2, false)} del precio por día`, "Referencia"],
    ["Rango 30 d", `${precio(ind.min30)} – ${precio(ind.max30)}`,
      ind.max30 > ind.min30 ? `cierre al ${(((ind.cierre - ind.min30) / (ind.max30 - ind.min30)) * 100).toFixed(0)} % del rango` : "—", "Referencia"],
    [`Caída máxima (${todas.length} d)`, <span className="negativo">{pct(ind.caidaMax, 1)}</span>, "desde el máximo previo", "Referencia"],
    ["Volumen (USDT, última vela)", precio(ind.volUsdtUlt),
      ind.volUsdtProm20 ? `${pct(ind.volUsdtUlt / ind.volUsdtProm20 - 1, 0)} frente al promedio de 20 d` : "—", "Referencia"],
  ] : [];

  return (
    <>
      <MensajeError mensaje={s.error ?? m.error ?? h.error} />
      <div className="aviso azul">
        <b>Señal de {activo}</b> · estrategia {f?.estrategia}. Cambia de activo en la barra superior. El laboratorio no compra: si la señal del modelo
        compra o vende y pasa los controles de riesgo, llega un aviso por {canal}, y la compra en MEXC es manual y opcional.
      </div>

      <div className="rejilla r6">
        <Kpi valor={f?.accion ? <Acc a={f.accion} /> : "—"} etiqueta="Acción de hoy" sub={`vela ${f?.fecha_vela ?? "—"} · próximo análisis ${horaLocal(s.datos?.proximo_ciclo_utc)}`} />
        <Kpi valor={precio(f?.cierre)} etiqueta="Cierre (USDT)" sub={<span className={signo(ind?.var1)}>{pct(ind?.var1)} vs día anterior</span>} />
        <Kpi valor={<span className={pronSup ? "positivo" : ""}>{pct(f?.pronostico, 3)}</span>} etiqueta="Pronóstico del modelo"
          sub={`δ = ${pct(f?.delta, 3, false)} · ${pronSup ? "supera el umbral" : "no supera el umbral"}`} />
        <Kpi valor={<span className={signo(f?.dist_sma20)}>{pct(f?.dist_sma20, 1)}</span>} etiqueta="Distancia a la SMA20"
          sub={`${f?.cierre_sobre_sma20 ? "sobre" : "bajo"} la SMA20${usaD ? " · filtro de la estrategia D" : ""}`} />
        <Kpi valor={pct(ultimaH?.vol20, 2, false)} etiqueta="Volatilidad 20 d" sub="stop = cierre × (1 − 2 × vol20)" />
        <Kpi valor={f?.senal_activa ? precio(f.precio_entrada) : "—"} etiqueta={f?.senal_activa ? "Señal activa · entrada" : "Sin señal activa"}
          sub={f?.senal_activa ? <span><span className={signo(ganancia)}>{pct(ganancia, 1)}</span> desde la entrada · stop {precio(f.stop)} ({pct(aStop, 1)})</span> : "esperando señal de compra"} />
      </div>

      <div className="seccion">Gráficos de {activo}</div>
      <Tarjeta titulo={`Precio diario · cierre, SMA20, SMA50 y Bandas de Bollinger`} extra={
        <span className="selector">{[60, 90, 180].map((d) => <button key={d} className={dias === d ? "activo" : ""} onClick={() => setDias(d)}>{d} d</button>)}</span>}>
        {ind ? (
          <GraficaLineas etiquetas={etiquetas} alto={360} formato={(x) => precio(x)} marcadores={marcadores}
            series={[
              { nombre: "Cierre", valores: v.map((x) => x.close), color: "var(--cian)", grosor: 2.2 },
              { nombre: "SMA20", valores: corta(ind.series.s20), color: "var(--ambar)", discontinua: true, grosor: 1.6 },
              { nombre: "SMA50", valores: corta(ind.series.s50), color: "var(--violeta)", discontinua: true, grosor: 1.4 },
              { nombre: "Bollinger sup.", valores: corta(ind.series.bbSup), color: "var(--gris)", grosor: 1 },
              { nombre: "Bollinger inf.", valores: corta(ind.series.bbInf), color: "var(--gris)", grosor: 1 },
              ...(f?.senal_activa && f.stop ? [{ nombre: "Stop sugerido", valores: v.map(() => f.stop as number), color: "var(--rojo)", discontinua: true, grosor: 1 }] : []),
            ]} />
        ) : <div className="tenue">Consultando velas de MEXC…</div>}
        <div className="tenue chico">▲ entrada · ▼ salida de la señal del modelo (simulación interna, no son compras reales). Pasa el cursor para ver valores.</div>
      </Tarjeta>

      <div className="rejilla r2" style={{ marginTop: 14 }}>
        <Tarjeta titulo="Pronóstico del modelo frente a su umbral δ (cada ciclo)">
          {hist.length >= 2 ? (
            <GraficaLineas etiquetas={hist.map((x) => x.fecha_vela)} alto={240} formato={(x) => `${x.toFixed(2)} %`} lineaBase={0}
              series={[
                { nombre: "Pronóstico", valores: hist.map((x) => x.pronostico * 100), color: "var(--azul)", grosor: 2.2 },
                { nombre: "Umbral δ", valores: hist.map((x) => x.delta * 100), color: "var(--ambar)", discontinua: true, grosor: 1.4 },
              ]} />
          ) : <div className="tenue">Hacen falta al menos dos ciclos en vivo.</div>}
          <div className="tenue chico">La señal de compra aparece cuando la línea azul supera a la ámbar{usaD ? " y el cierre está sobre la SMA20" : ""}.</div>
        </Tarjeta>
        <Tarjeta titulo="RSI (14) · fuerza relativa">
          {ind ? (
            <GraficaLineas etiquetas={etiquetas} alto={240} formato={(x) => x.toFixed(0)}
              series={[
                { nombre: "RSI 14", valores: corta(ind.series.rsi), color: "var(--violeta)", grosor: 2 },
                { nombre: "70", valores: v.map(() => 70), color: "var(--rojo)", discontinua: true, grosor: 1 },
                { nombre: "30", valores: v.map(() => 30), color: "var(--verde)", discontinua: true, grosor: 1 },
              ]} />
          ) : <div className="tenue">Consultando velas de MEXC…</div>}
          <div className="tenue chico">Referencia de mercado: sobre 70 suele leerse como sobrecompra y bajo 30 como sobreventa. No cambia la señal del modelo.</div>
        </Tarjeta>
      </div>

      <div className="seccion">Indicadores financieros</div>
      <Tarjeta>
        <table className="tabla">
          <thead><tr><th>Indicador</th><th className="der">Valor</th><th>Lectura</th><th>Uso</th></tr></thead>
          <tbody>
            {filasInd.map(([nom, val, lec, uso]) => (
              <tr key={nom}><td>{nom}</td><td className="der mono">{val}</td><td className="chico">{lec}</td>
                <td className="chico">{uso.startsWith("Modelo") ? <span className="chip azul">{uso}</span> : <span className="tenue">{uso}</span>}</td></tr>
            ))}
          </tbody>
        </table>
        <div className="tenue chico" style={{ marginTop: 8 }}>Calculados con las velas diarias cerradas de MEXC. El modelo usa el pronóstico, la SMA20 y la volatilidad de 20 días; el resto es referencia para decidir la compra manual.</div>
      </Tarjeta>

      <div className="seccion">Historial de la señal de {activo}</div>
      <Tarjeta>
        <div className="desplaza" style={{ maxHeight: 360 }}>
          <table className="tabla">
            <thead><tr><th>Vela</th><th className="der">Cierre</th><th className="der">Pronóstico</th><th className="der">δ</th><th>Tendencia</th>
              <th className="der">Vol. 20 d</th><th>Acción del modelo</th><th>Aviso</th></tr></thead>
            <tbody>
              {hist.slice().reverse().map((x) => (
                <tr key={x.fecha_vela} className={x.accion === "COMPRAR" ? "senal-compra" : ""}>
                  <td className="mono">{x.fecha_vela}</td><td className="der mono">{precio(x.cierre)}</td>
                  <td className={`der mono ${x.pronostico > x.delta ? "positivo" : ""}`}>{pct(x.pronostico, 3)}</td>
                  <td className="der mono tenue">{pct(x.delta, 3, false)}</td>
                  <td className="chico">{x.dist_sma20 >= 0 ? "sobre" : "bajo"} SMA20 ({pct(x.dist_sma20, 1)})</td>
                  <td className="der mono">{pct(x.vol20, 2, false)}</td>
                  <td>{x.accion ? <Acc a={x.accion} /> : "—"}</td>
                  <td>{x.aviso ? <span className={`chip ${CLASE_ESTADO[x.aviso.estado] ?? ""}`}>{x.aviso.tipo} · {TEXTO_ESTADO[x.aviso.estado] ?? x.aviso.estado}</span> : <span className="tenue">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Tarjeta>

      <div className="seccion">Avisos de {activo}</div>
      <Tarjeta titulo={`Avisos por ${canal}`} extra={
        <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className={`chip ${CLASE_ESTADO[wa?.estado ?? ""] ?? ""}`}>{TEXTO_ESTADO[wa?.estado ?? ""] ?? "—"}</span>
          <button className="boton azul" disabled={ocupado || wa?.estado !== "activo"} onClick={probar}>Enviar aviso de prueba</button>
        </span>}>
        {mensaje && <div className={`aviso ${mensaje.tipo}`}>{mensaje.texto}</div>}
        {avisos.length ? (
          <table className="tabla">
            <thead><tr><th>Enviado</th><th>Vela</th><th>Tipo</th><th>Estado</th><th className="der">Intentos</th><th>Detalle</th></tr></thead>
            <tbody>
              {avisos.map((a) => (
                <tr key={`${a.fecha_vela}-${a.tipo}`} title={a.texto}>
                  <td className="mono chico">{hace(a.ts_utc)}</td><td className="mono">{a.fecha_vela}</td><td>{a.tipo}</td>
                  <td><span className={`chip ${CLASE_ESTADO[a.estado] ?? ""}`}>{TEXTO_ESTADO[a.estado] ?? a.estado}</span></td>
                  <td className="der mono">{a.intentos}</td><td className="chico tenue">{a.detalle ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="tenue">Este activo todavía no ha tenido avisos: llegan cuando su señal compra o vende.</div>}
        <div className="tenue chico" style={{ marginTop: 8 }}>
          Disparador: {wa?.disparador ?? "estrategia del modelo tras el motor de riesgo"}{wa?.avisar_ventas ? " · también avisa las ventas" : ""}{wa?.destino ? ` · destino ${wa.destino}` : ""}.
        </div>
      </Tarjeta>
    </>
  );
}
