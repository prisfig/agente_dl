import { useState } from "react";
import { useConsulta } from "../api";
import { MensajeError, Tarjeta } from "../componentes/Ui";
import { pct } from "../formato";
import type { Modo } from "../tipos";

interface Capa { nombre: string; tipo: string; valores: number[] }
interface Red { semilla: number; capas: Capa[]; salida_escalada: number; salida: number }
interface DatosRed {
  origen: string; simbolo: string; fecha_vela: string; pronostico: number | null; delta: number | null; senal: string | null; estrategia: string;
  cierre_sobre_sma20: boolean | null;
  modelo: { modelo: string; semillas: number[]; neuronas?: number; parametros?: number };
  activaciones: { entrada_escalada: number[]; entrada_original: number[]; redes: Red[]; ensamble: number } | null;
}

const ANCHO = 1000, ALTO = 560;
const COLUMNAS = [150, 430, 680, 830];

function colorValor(v: number, max: number) {
  const a = Math.min(1, Math.abs(v) / (max || 1));
  return { fill: v >= 0 ? "#ffb547" : "#4c8dff", opacity: 0.18 + 0.82 * a };
}

export default function RedNeuronal({ modo }: { modo: Modo }) {
  const { datos, error } = useConsulta<DatosRed>(`/api/red?modo=${modo}`, 30_000);
  const [sel, setSel] = useState(0);
  if (error) return <MensajeError mensaje={error} />;
  if (!datos) return <div className="tenue">Calculando activaciones…</div>;
  const act = datos.activaciones;
  if (!act) return <div className="aviso">El backend usa un modelo simulado (pruebas): no hay activaciones reales que mostrar.</div>;

  const red = act.redes[sel];
  const capas = [act.entrada_escalada, ...red.capas.map((c) => c.valores)];
  const n = red.capas[0].valores.length;   // neuronas de este activo (BTC 20, ETH 10, SOL 20)
  const nombres = ["Entrada · 20 rendimientos (escalados)", `${red.capas[0].tipo} · estado final h (${n})`, `${red.capas[1].tipo} ReLU (${red.capas[1].valores.length})`, "Salida"];
  const yDe = (n: number, i: number) => (n === 1 ? ALTO / 2 : 46 + (i * (ALTO - 92)) / (n - 1));
  const clave = `${datos.fecha_vela}-${sel}`;
  const supera = act.ensamble > (datos.delta ?? 0);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
        <b className="tenue chico" style={{ letterSpacing: 1.2 }}>RED NEURONAL EN VIVO · {datos.simbolo} · {datos.origen.toUpperCase()} · VELA {datos.fecha_vela}</b>
        <span style={{ flex: 1 }} />
        <span className="selector">{act.redes.map((r, i) => (
          <button key={r.semilla} className={sel === i ? "activo" : ""} onClick={() => setSel(i)}>LSTM semilla {r.semilla}</button>))}</span>
      </div>

      <svg className="grafica lienzo" viewBox={`0 0 ${ANCHO} ${ALTO}`} key={clave}>
        {capas.slice(0, -1).map((origen, k) => {
          const destino = capas[k + 1];
          const maxO = Math.max(...origen.map(Math.abs)) || 1;
          return (
            <g key={`c${k}`} className="capa-red" style={{ animationDelay: `${k * 0.45 + 0.2}s` }}>
              {origen.map((u, i) => destino.map((_, j) => (
                // la intensidad de cada conexión refleja la señal que sale de la neurona de origen
                <line key={`${i}-${j}`} x1={COLUMNAS[k]} y1={yDe(origen.length, i)} x2={COLUMNAS[k + 1]} y2={yDe(destino.length, j)}
                  stroke={u >= 0 ? "#ffb547" : "#4c8dff"} strokeOpacity={0.02 + (destino.length === 1 ? 0.5 : 0.13) * (Math.abs(u) / maxO)} strokeWidth={0.8} />
              )))}
            </g>
          );
        })}
        {capas.map((valores, k) => {
          const max = Math.max(...valores.map(Math.abs));
          return (
            <g key={`n${k}`} className="capa-red" style={{ animationDelay: `${k * 0.45}s` }}>
              <text className="nodo-sub" x={COLUMNAS[k]} y={20} textAnchor="middle">{nombres[k]}</text>
              {valores.map((v, i) => {
                const c = colorValor(v, max);
                const y = yDe(valores.length, i);
                return (
                  <g key={i}>
                    <circle cx={COLUMNAS[k]} cy={y} r={k === 3 ? 16 : 8} fill={c.fill} opacity={c.opacity} />
                    <circle cx={COLUMNAS[k]} cy={y} r={k === 3 ? 16 : 8} fill="none" stroke="#2c3a58" />
                    <title>{`${nombres[k]} #${i + 1}: ${v.toFixed(4)}`}</title>
                    {k === 0 && (
                      <text className="nodo-sub" x={COLUMNAS[0] - 16} y={y + 4} textAnchor="end">
                        {`t−${19 - i}`.replace("t−0", "t  ")} {pct(act.entrada_original[i], 2)}
                      </text>
                    )}
                  </g>
                );
              })}
              {k === 3 && (
                <>
                  <text className="nodo-etiqueta" x={COLUMNAS[3] + 26} y={ALTO / 2 - 4}>{pct(red.salida, 4)}</text>
                  <text className="nodo-sub" x={COLUMNAS[3] + 26} y={ALTO / 2 + 12}>escalado {red.salida_escalada.toFixed(3)}</text>
                </>
              )}
            </g>
          );
        })}
      </svg>

      <div className="rejilla r4" style={{ marginTop: 12 }}>
        {act.redes.map((r, i) => (
          <div key={r.semilla} className="tarjeta kpi" style={{ borderColor: i === sel ? "#24406f" : undefined, cursor: "pointer" }} onClick={() => setSel(i)}>
            <div className="valor" style={{ fontSize: 20 }}>{pct(r.salida, 4)}</div>
            <div className="etiqueta">LSTM semilla {r.semilla}</div>
            <div className="sub">pronóstico de r(t+1)</div>
          </div>
        ))}
        <div className="tarjeta kpi">
          <div className={`valor ${supera ? "positivo" : ""}`} style={{ fontSize: 20 }}>{pct(act.ensamble, 4)}</div>
          <div className="etiqueta">Ensamble (promedio)</div>
          <div className="sub">{supera ? "supera" : "no supera"} δ {pct(datos.delta, 4, false)}
            {datos.estrategia === "D" ? <> · cierre {datos.cierre_sobre_sma20 ? "sobre" : "bajo"} SMA20</> : <> · estrategia C (sin filtro)</>} → <b>{datos.senal}</b></div>
        </div>
      </div>
      <Tarjeta estilo={{ marginTop: 12 }}>
        <div className="tenue chico">
          Lectura: cada círculo es una neurona; el color indica el signo (ámbar positivo, azul negativo) y la intensidad, la magnitud relativa dentro de su capa.
          La entrada son los 20 rendimientos diarios de t−19 a t (escalados con el escalador de TR, secuencia antigua → reciente). La red de {datos.simbolo} es LSTM({n}) → Dense({n}, ReLU) → Dense(1),{" "}
          {(datos.modelo.parametros ?? 0).toLocaleString("es-MX")} parámetros; la salida se desescala con el escalador de y. Son los valores reales calculados por el backend con los pesos congelados.
        </div>
      </Tarjeta>
    </div>
  );
}
