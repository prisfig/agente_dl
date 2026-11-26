import { useState } from "react";
import { useConsulta } from "../api";
import { GraficaLineas, type Marcador } from "../componentes/Graficas";
import { MensajeError, Tarjeta } from "../componentes/Ui";
import { pct, precio } from "../formato";
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
      <Tarjeta titulo={`${datos.simbolo} diario · cierre, SMA20 y operaciones Paper`} extra={
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
