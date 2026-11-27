import { useState } from "react";

export interface Serie {
  nombre: string;
  valores: (number | null)[];
  color: string;
  discontinua?: boolean;
  grosor?: number;
}

export interface Marcador {
  indice: number;
  valor: number;
  tipo: "compra" | "venta";
  texto: string;
}

interface Props {
  etiquetas: string[];
  series: Serie[];
  marcadores?: Marcador[];
  alto?: number;
  formato?: (v: number) => string;
  lineaBase?: number;
}

const ANCHO = 900;
const M = { izq: 70, der: 16, arr: 12, aba: 26 };

export function GraficaLineas({ etiquetas, series, marcadores = [], alto = 300, formato = (v) => v.toFixed(0), lineaBase }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const todos = series.flatMap((s) => s.valores.filter((v): v is number => v != null));
  marcadores.forEach((m) => todos.push(m.valor));
  if (lineaBase != null) todos.push(lineaBase);
  if (!todos.length || etiquetas.length < 2) return <div className="tenue">Sin datos suficientes para graficar.</div>;
  let min = Math.min(...todos), max = Math.max(...todos);
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * 0.06;
  min -= pad; max += pad;
  const n = etiquetas.length;
  const x = (i: number) => M.izq + (i / (n - 1)) * (ANCHO - M.izq - M.der);
  const y = (v: number) => M.arr + (1 - (v - min) / (max - min)) * (alto - M.arr - M.aba);
  const camino = (vals: (number | null)[]) => {
    let d = "", abierto = false;
    vals.forEach((v, i) => {
      if (v == null) { abierto = false; return; }
      d += `${abierto ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      abierto = true;
    });
    return d;
  };
  const ticksY = Array.from({ length: 5 }, (_, k) => min + ((max - min) * k) / 4);
  const pasoX = Math.max(1, Math.ceil(n / 8));

  const mover = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * ANCHO;
    const i = Math.round(((px - M.izq) / (ANCHO - M.izq - M.der)) * (n - 1));
    setHover(i >= 0 && i < n ? i : null);
  };

  return (
    <div>
      <svg className="grafica" viewBox={`0 0 ${ANCHO} ${alto}`} onMouseMove={mover} onMouseLeave={() => setHover(null)}>
        {ticksY.map((t, k) => (
          <g key={k}>
            <line x1={M.izq} x2={ANCHO - M.der} y1={y(t)} y2={y(t)} stroke="#1a2230" />
            <text x={M.izq - 8} y={y(t) + 4} textAnchor="end">{formato(t)}</text>
          </g>
        ))}
        {etiquetas.map((e, i) => (i % pasoX === 0 || i === n - 1) && (
          <text key={i} x={x(i)} y={alto - 6} textAnchor="middle">{e.slice(5)}</text>
        ))}
        {lineaBase != null && <line x1={M.izq} x2={ANCHO - M.der} y1={y(lineaBase)} y2={y(lineaBase)} stroke="#3a4558" strokeDasharray="3 4" />}
        {series.map((s) => (
          <path key={s.nombre} d={camino(s.valores)} fill="none" stroke={s.color} strokeWidth={s.grosor ?? 2}
            strokeDasharray={s.discontinua ? "6 5" : undefined} strokeLinejoin="round" />
        ))}
        {marcadores.map((m, k) => (
          <g key={k}>
            <path d={m.tipo === "compra"
              ? `M${x(m.indice)},${y(m.valor) + 4} l-6,10 h12 z`
              : `M${x(m.indice)},${y(m.valor) - 4} l-6,-10 h12 z`}
              fill={m.tipo === "compra" ? "var(--verde)" : "var(--rojo)"}><title>{m.texto}</title></path>
          </g>
        ))}
        {hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={M.arr} y2={alto - M.aba} stroke="#3a4558" />
            {series.map((s) => s.valores[hover] != null && (
              <circle key={s.nombre} cx={x(hover)} cy={y(s.valores[hover] as number)} r={3.5} fill={s.color} />
            ))}
          </g>
        )}
      </svg>
      <div className="leyenda">
        {series.map((s) => (
          <span key={s.nombre}><i style={{ background: s.color }} />{s.nombre}
            {hover != null && s.valores[hover] != null && <b className="mono" style={{ color: "var(--texto)", marginLeft: 6 }}>{formato(s.valores[hover] as number)}</b>}
          </span>
        ))}
        {hover != null && <span className="mono">{etiquetas[hover]}</span>}
      </div>
    </div>
  );
}

export function Sparkline({ valores, color = "var(--azul)", ancho = 120, alto = 30 }: { valores: number[]; color?: string; ancho?: number; alto?: number }) {
  if (valores.length < 2) return null;
  const min = Math.min(...valores), max = Math.max(...valores) || 1;
  const d = valores.map((v, i) => `${i ? "L" : "M"}${((i / (valores.length - 1)) * ancho).toFixed(1)},${(alto - 2 - ((v - min) / (max - min || 1)) * (alto - 4)).toFixed(1)}`).join("");
  return <svg width={ancho} height={alto}><path d={d} fill="none" stroke={color} strokeWidth={1.6} /></svg>;
}

/** v2.4 · Velas japonesas (OHLC diario) con líneas superpuestas (SMA20, SMA50, stop…) y lectura al pasar el cursor. */
export function GraficaVelas({ velas, lineas = [], alto = 360, formato = (v) => v.toFixed(2), marcadores = [] }: {
  velas: { fecha: string; open: number; high: number; low: number; close: number }[];
  lineas?: Serie[]; alto?: number; formato?: (v: number) => string; marcadores?: Marcador[];
}) {
  const [hover, setHover] = useState<number | null>(null);
  const n = velas.length;
  if (n < 2) return <div className="tenue">Sin datos suficientes para graficar.</div>;
  const todos = [...velas.flatMap((v) => [v.high, v.low]), ...lineas.flatMap((s) => s.valores.filter((v): v is number => v != null))];
  let min = Math.min(...todos), max = Math.max(...todos);
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * 0.05;
  min -= pad; max += pad;
  const paso = (ANCHO - M.izq - M.der) / n;
  const x = (i: number) => M.izq + paso * (i + 0.5);
  const y = (v: number) => M.arr + (1 - (v - min) / (max - min)) * (alto - M.arr - M.aba);
  const cuerpo = Math.max(1.5, paso * 0.62);
  const ticksY = Array.from({ length: 5 }, (_, k) => min + ((max - min) * k) / 4);
  const pasoX = Math.max(1, Math.ceil(n / 8));
  const camino = (vals: (number | null)[]) => {
    let d = "", abierto = false;
    vals.forEach((v, i) => { if (v == null) { abierto = false; return; } d += `${abierto ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; abierto = true; });
    return d;
  };
  const mover = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.floor((((e.clientX - r.left) / r.width) * ANCHO - M.izq) / paso);
    setHover(i >= 0 && i < n ? i : null);
  };
  const h = hover != null ? velas[hover] : null;
  return (
    <div>
      <svg className="grafica" viewBox={`0 0 ${ANCHO} ${alto}`} onMouseMove={mover} onMouseLeave={() => setHover(null)}>
        {ticksY.map((t, k) => (
          <g key={k}><line x1={M.izq} x2={ANCHO - M.der} y1={y(t)} y2={y(t)} stroke="#1a2230" />
            <text x={M.izq - 8} y={y(t) + 4} textAnchor="end">{formato(t)}</text></g>
        ))}
        {velas.map((v, i) => (i % pasoX === 0 || i === n - 1) && <text key={`f${i}`} x={x(i)} y={alto - 6} textAnchor="middle">{v.fecha.slice(5)}</text>)}
        {velas.map((v, i) => {
          const sube = v.close >= v.open, color = sube ? "var(--verde)" : "var(--rojo)";
          const y1 = y(Math.max(v.open, v.close)), y2 = y(Math.min(v.open, v.close));
          return (
            <g key={v.fecha}>
              <line x1={x(i)} x2={x(i)} y1={y(v.high)} y2={y(v.low)} stroke={color} strokeWidth={1} />
              <rect x={x(i) - cuerpo / 2} y={y1} width={cuerpo} height={Math.max(1, y2 - y1)} fill={sube ? "transparent" : color} stroke={color} strokeWidth={1} />
            </g>
          );
        })}
        {lineas.map((s) => (
          <path key={s.nombre} d={camino(s.valores)} fill="none" stroke={s.color} strokeWidth={s.grosor ?? 1.5}
            strokeDasharray={s.discontinua ? "6 5" : undefined} strokeLinejoin="round" />
        ))}
        {marcadores.map((m, k) => (
          <path key={`m${k}`} d={m.tipo === "compra" ? `M${x(m.indice)},${y(velas[m.indice].low) + 6} l-6,10 h12 z` : `M${x(m.indice)},${y(velas[m.indice].high) - 6} l-6,-10 h12 z`}
            fill={m.tipo === "compra" ? "var(--verde)" : "var(--rojo)"}><title>{m.texto}</title></path>
        ))}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={M.arr} y2={alto - M.aba} stroke="#3a4558" />}
      </svg>
      <div className="leyenda">
        <span><i style={{ background: "var(--verde)" }} />Vela alcista (hueca)</span>
        <span><i style={{ background: "var(--rojo)" }} />Vela bajista (rellena)</span>
        {lineas.map((s) => <span key={s.nombre}><i style={{ background: s.color }} />{s.nombre}
          {hover != null && s.valores[hover] != null && <b className="mono" style={{ color: "var(--texto)", marginLeft: 6 }}>{formato(s.valores[hover] as number)}</b>}</span>)}
        {h && <span className="mono">{h.fecha} · A {formato(h.open)} · Máx {formato(h.high)} · Mín {formato(h.low)} · C {formato(h.close)}</span>}
      </div>
    </div>
  );
}
