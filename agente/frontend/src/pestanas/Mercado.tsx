import { useEffect, useState } from "react";
import { llamar, useConsulta } from "../api";
import { GraficaLineas, type Marcador } from "../componentes/Graficas";
import { MensajeError, Tarjeta } from "../componentes/Ui";
import { pct, precio } from "../formato";
import { correlacion, rendimientos, resumenIndicadores } from "../indicadores";
import { NOMBRES_CARTERA, type Cartera, type Estado, type Modo, type Vela } from "../tipos";

interface DatosMercado {
  simbolo: string;
  activo_base?: string;
  velas: Vela[];
  sma20: (number | null)[];
  ordenes: { fecha_vela: string; cartera: string; lado: "COMPRAR" | "VENDER"; precio: number; motivo: string }[];
  carteras: Record<string, Omit<Cartera, "en_posicion" | "patrimonio">>;
  ciclos: string[];
}

export default function Mercado({ modo, estado }: { modo: Modo; estado: Estado | null }) {
  const [limite, setLimite] = useState(90);
  const [cartera, setCartera] = useState("con_llm");
  const { datos, error } = useConsulta<DatosMercado>(`/api/mercado?modo=${modo}&limite=${limite}`, 60_000);
  if (error) return <MensajeError mensaje={error} />;
  if (!datos) return <div className="tenue">Consultando MEXC…</div>;

  const v = datos.velas;
  const etiquetas = v.map((x) => x.fecha);
  const idx = new Map(etiquetas.map((f, i) => [f, i]));
  const marcadores: Marcador[] = datos.ordenes
    .filter((o) => o.cartera === cartera && idx.has(o.fecha_vela))
    .map((o) => ({ indice: idx.get(o.fecha_vela)!, valor: o.precio, tipo: o.lado === "COMPRAR" ? "compra" : "venta",
      texto: `${o.lado} ${o.fecha_vela} a ${precio(o.precio)} (${o.motivo})` }));
  const stop = datos.carteras[cartera]?.stop;
  const ultima = v[v.length - 1];
  const previa = v[v.length - 2];
  const fechasCiclo = new Set(datos.ciclos);

  return (
    <>
      <div className="rejilla r4">
        <div className="tarjeta kpi"><div className="valor">{precio(ultima.close)}</div><div className="etiqueta">{datos.simbolo} · último cierre</div>
          <div className={`sub ${ultima.close >= previa.close ? "positivo" : "negativo"}`}>{pct(ultima.close / previa.close - 1)} vs día anterior</div></div>
        <div className="tarjeta kpi"><div className="valor">{precio(datos.sma20[datos.sma20.length - 1] ?? null)}</div><div className="etiqueta">SMA20</div>
          <div className="sub">{ultima.close > (datos.sma20[datos.sma20.length - 1] ?? 0) ? "cierre por encima" : "cierre por debajo"}</div></div>
        <div className="tarjeta kpi"><div className="valor mono">{ultima.fecha}</div><div className="etiqueta">Última vela cerrada (UTC)</div>
          <div className="sub">MEXC spot · 1d · {v.length} velas</div></div>
        <div className="tarjeta kpi"><div className="valor">{precio(stop ?? null)}</div><div className="etiqueta">Stop móvil · {NOMBRES_CARTERA[cartera]}</div>
          <div className="sub">{estado?.carteras[cartera]?.en_posicion ? "posición abierta" : "sin posición"}</div></div>
      </div>

      <div className="seccion">Precio y decisiones</div>
      <Tarjeta titulo={`${datos.simbolo} diario · cierre, SMA20 y señales (simulación interna)`} extra={
        <span style={{ display: "flex", gap: 8 }}>
          <span className="selector">{[60, 90, 180].map((n) => <button key={n} className={limite === n ? "activo" : ""} onClick={() => setLimite(n)}>{n} d</button>)}</span>
          <span className="selector">{Object.keys(NOMBRES_CARTERA).map((n) => <button key={n} className={cartera === n ? "activo" : ""} onClick={() => setCartera(n)}>{NOMBRES_CARTERA[n].split(" · ")[0]}</button>)}</span>
        </span>}>
        <GraficaLineas etiquetas={etiquetas} alto={360} formato={(x) => precio(x)} marcadores={marcadores}
          series={[
            { nombre: "Cierre", valores: v.map((x) => x.close), color: "var(--cian)" },
            { nombre: "SMA20", valores: datos.sma20, color: "var(--ambar)", discontinua: true, grosor: 1.5 },
            ...(stop ? [{ nombre: "Stop móvil actual", valores: v.map(() => stop), color: "var(--rojo)", discontinua: true, grosor: 1 }] : []),
          ]} />
        <div className="tenue chico">▲ compra · ▼ venta de la cartera seleccionada ({modo}). Pasa el cursor para ver valores.</div>
      </Tarjeta>

      {estado && <Comparativa activos={estado.activos} actual={datos.simbolo} />}

      <div className="seccion">Últimas velas</div>
      <Tarjeta>
        <div className="desplaza" style={{ maxHeight: 360 }}>
          <table className="tabla">
            <thead><tr><th>Fecha (UTC)</th><th className="der">Apertura</th><th className="der">Máximo</th><th className="der">Mínimo</th><th className="der">Cierre</th><th className="der">Var.</th><th className="der">Volumen {datos.activo_base ?? "BTC"}</th><th>Ciclo {modo}</th></tr></thead>
            <tbody>
              {v.slice().reverse().slice(0, 30).map((x, i, arr) => {
                const ant = arr[i + 1];
                return (
                  <tr key={x.fecha}>
                    <td className="mono">{x.fecha}</td><td className="der mono">{precio(x.open)}</td><td className="der mono">{precio(x.high)}</td>
                    <td className="der mono">{precio(x.low)}</td><td className="der mono">{precio(x.close)}</td>
                    <td className={`der mono ${ant && x.close >= ant.close ? "positivo" : "negativo"}`}>{ant ? pct(x.close / ant.close - 1) : "—"}</td>
                    <td className="der mono">{x.volume.toFixed(1)}</td>
                    <td>{fechasCiclo.has(x.fecha) ? <span className="chip azul">procesada</span> : <span className="tenue">—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Tarjeta>
    </>
  );
}

// ---------------------------------------------------------------- v2.2 · comparar los 15 pares
const COLORES = ["var(--cian)", "var(--ambar)", "var(--violeta)", "var(--verde)", "var(--rojo)", "#ff8fd0"];
const base = (s: string) => s.replace(/USDT$/, "");
const cls = (v: number | null | undefined) => (v == null ? "" : v > 0 ? "positivo" : v < 0 ? "negativo" : "");
interface FilaSen { simbolo: string; accion?: string; pronostico?: number; delta: number }
type Clave = "simbolo" | "var1" | "var7" | "var30" | "varPeriodo" | "vol20" | "caida" | "dist20" | "rsi14" | "volUsdt" | "corrBtc";

function Comparativa({ activos, actual }: { activos: string[]; actual: string }) {
  const [dias, setDias] = useState(90);
  const [velas, setVelas] = useState<Record<string, Vela[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [orden, setOrden] = useState<{ k: Clave; asc: boolean }>({ k: "varPeriodo", asc: false });
  const [elegidos, setElegidos] = useState<string[]>(() => Array.from(new Set([actual, "BTCUSDT", "ETHUSDT"])).filter((x) => activos.includes(x)));
  const sen = useConsulta<{ senales: FilaSen[] }>("/api/senales", 60_000);
  const clave = activos.join(",");

  useEffect(() => {
    let vigente = true;
    setError(null);
    Promise.all(activos.map((s) => llamar<{ velas: Vela[] }>(`/api/mercado?modo=vivo&limite=${dias + 50}&simbolo=${s}`).then((r) => [s, r.velas] as const)))
      .then((rs) => { if (vigente) setVelas(Object.fromEntries(rs)); })
      .catch((e) => { if (vigente) setError((e as Error).message); });
    return () => { vigente = false; };
  }, [clave, dias]); // eslint-disable-line react-hooks/exhaustive-deps

  const listos = activos.filter((s) => (velas[s]?.length ?? 0) > 25);
  const periodo = (s: string) => velas[s].slice(-(dias + 1));
  const rendBtc = velas.BTCUSDT ? rendimientos(periodo("BTCUSDT").map((x) => x.close)) : [];
  const filas = listos.map((s) => {
    const ind = resumenIndicadores(velas[s]);
    const p = periodo(s).map((x) => x.close);
    const sf = sen.datos?.senales.find((x) => x.simbolo === s);
    return { simbolo: s, ind, sen: sf, var1: ind.var1, var7: ind.var7, var30: ind.var30, varPeriodo: p[p.length - 1] / p[0] - 1,
      vol20: ind.vol20, caida: (() => { let pico = -Infinity, peor = 0; for (const c of p) { pico = Math.max(pico, c); peor = Math.min(peor, c / pico - 1); } return peor; })(),
      dist20: ind.dist20, rsi14: ind.rsi14, volUsdt: ind.volUsdtProm20,
      corrBtc: s === "BTCUSDT" ? 1 : correlacion(rendimientos(p), rendBtc) };
  });
  const ordenadas = filas.slice().sort((a, b) => {
    const x = a[orden.k], y = b[orden.k];
    const r = typeof x === "string" ? String(x).localeCompare(String(y)) : ((x as number | null) ?? -Infinity) - ((y as number | null) ?? -Infinity);
    return orden.asc ? r : -r;
  });
  const th = (k: Clave, t: string, der = true) => (
    <th className={der ? "der" : ""}><button className="orden" onClick={() => setOrden({ k, asc: orden.k === k ? !orden.asc : k === "simbolo" })}>
      {t}{orden.k === k ? (orden.asc ? " ▲" : " ▼") : ""}</button></th>);
  const alternar = (s: string) => setElegidos((e) => (e.includes(s) ? e.filter((x) => x !== s) : e.length >= 6 ? e : [...e, s]));

  // rendimiento relativo (base 100), alineado por fecha
  const ref = elegidos.find((s) => velas[s]);
  const fechas = ref ? periodo(ref).map((x) => x.fecha) : [];
  const series = elegidos.filter((s) => velas[s]).map((s, i) => {
    const mapa = new Map(periodo(s).map((x) => [x.fecha, x.close]));
    const c0 = mapa.get(fechas[0]) ?? periodo(s)[0].close;
    return { nombre: base(s), valores: fechas.map((d) => (mapa.has(d) ? ((mapa.get(d) as number) / c0) * 100 : null)), color: COLORES[i % COLORES.length], grosor: s === actual ? 2.6 : 1.8 };
  });
  const rendPer = Object.fromEntries(listos.map((s) => [s, rendimientos(periodo(s).map((x) => x.close))]));

  return (
    <>
      <div className="seccion">Comparar activos · los {activos.length} pares de MEXC</div>
      <MensajeError mensaje={error ?? sen.error} />
      <Tarjeta titulo={`Rendimiento relativo (base 100 al inicio de los ${dias} d)`} extra={
        <span className="selector">{[30, 90, 180].map((d) => <button key={d} className={dias === d ? "activo" : ""} onClick={() => setDias(d)}>{d} d</button>)}</span>}>
        <div className="chips-comparar">
          {activos.map((s) => {
            const i = elegidos.indexOf(s);
            return <button key={s} className={`chip ${i >= 0 ? "elegido" : ""}`} onClick={() => alternar(s)}
              style={i >= 0 ? { borderColor: COLORES[i % COLORES.length], color: COLORES[i % COLORES.length] } : undefined}>{base(s)}</button>;
          })}
          <span className="tenue chico">Elige hasta 6 activos.</span>
        </div>
        {series.length && fechas.length > 1 ? <GraficaLineas etiquetas={fechas} alto={320} formato={(x) => x.toFixed(0)} lineaBase={100} series={series} />
          : <div className="tenue">{listos.length ? "Elige al menos un activo." : "Consultando velas de MEXC de los 15 pares…"}</div>}
      </Tarjeta>

      <Tarjeta titulo="Tabla comparativa · haz clic en una columna para ordenar" estilo={{ marginTop: 14 }}>
        <div className="desplaza">
          <table className="tabla">
            <thead><tr>{th("simbolo", "Activo", false)}<th className="der">Cierre</th>{th("var1", "1 d")}{th("var7", "7 d")}{th("var30", "30 d")}{th("varPeriodo", `${dias} d`)}
              {th("vol20", "Vol. 20 d")}{th("caida", `Caída máx. ${dias} d`)}{th("dist20", "vs SMA20")}{th("rsi14", "RSI 14")}{th("volUsdt", "Vol. prom. 20 d (USDT)")}
              {th("corrBtc", "Correl. BTC")}<th>Señal hoy</th><th>Gráfica</th></tr></thead>
            <tbody>
              {ordenadas.map((f) => (
                <tr key={f.simbolo} className={f.simbolo === actual ? "senal-compra" : ""}>
                  <td className="mono"><b>{f.simbolo}</b></td><td className="der mono">{precio(f.ind.cierre)}</td>
                  {[f.var1, f.var7, f.var30, f.varPeriodo].map((x, i) => <td key={i} className={`der mono ${cls(x)}`}>{pct(x, 1)}</td>)}
                  <td className="der mono">{pct(f.vol20, 2, false)}</td><td className="der mono negativo">{pct(f.caida, 1)}</td>
                  <td className={`der mono ${cls(f.dist20)}`}>{pct(f.dist20, 1)}</td>
                  <td className="der mono">{f.rsi14 == null ? "—" : f.rsi14.toFixed(0)}</td>
                  <td className="der mono">{f.volUsdt == null ? "—" : f.volUsdt >= 1e6 ? `${(f.volUsdt / 1e6).toFixed(1)} M` : `${(f.volUsdt / 1e3).toFixed(0)} k`}</td>
                  <td className="der mono">{f.corrBtc == null ? "—" : f.corrBtc.toFixed(2)}</td>
                  <td>{f.sen?.accion ? <span className={`accion ${f.sen.accion}`}>{f.sen.accion}</span> : "—"}</td>
                  <td><input type="checkbox" aria-label={`Comparar ${f.simbolo}`} checked={elegidos.includes(f.simbolo)} onChange={() => alternar(f.simbolo)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="tenue chico" style={{ marginTop: 8 }}>Velas diarias cerradas de MEXC. Volatilidad = desviación estándar de los rendimientos diarios de 20 días.
          Correlación con BTC: rendimientos diarios del periodo elegido. Señal hoy: acción de la estrategia del modelo de cada activo en su último ciclo.</div>
      </Tarjeta>

      <Tarjeta titulo={`Correlación de rendimientos diarios (${dias} d)`} estilo={{ marginTop: 14 }}>
        <div className="desplaza">
          <table className="tabla correlacion">
            <thead><tr><th></th>{listos.map((s) => <th key={s} className="der">{base(s)}</th>)}</tr></thead>
            <tbody>
              {listos.map((a) => (
                <tr key={a}><td className="mono"><b>{base(a)}</b></td>
                  {listos.map((b) => {
                    const c = a === b ? 1 : correlacion(rendPer[a], rendPer[b]);
                    const fondo = c == null ? "transparent" : c >= 0 ? `rgba(76,141,255,${(c * 0.75).toFixed(2)})` : `rgba(255,93,108,${(-c * 0.75).toFixed(2)})`;
                    return <td key={b} className="der mono" style={{ background: fondo }} title={`${base(a)} – ${base(b)}`}>{c == null ? "—" : c.toFixed(2)}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="tenue chico" style={{ marginTop: 8 }}>Azul: se mueven juntos (1 = igual). Rojo: en sentido contrario. Útil para no concentrar avisos en activos que se mueven igual.</div>
      </Tarjeta>
    </>
  );
}
