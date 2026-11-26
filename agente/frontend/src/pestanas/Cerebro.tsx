import { useEffect, useMemo, useRef, useState } from "react";
import { useConsulta } from "../api";
import { hace, num } from "../formato";
import type { Estado, Evento } from "../tipos";

interface Nodo { id: string; x: number; y: number; t: string; s: string }

const NODOS: Nodo[] = [
  { id: "programador", x: 95, y: 75, t: "Programador diario", s: "cierre 00:00 UTC + 5 min" },
  { id: "mexc", x: 95, y: 255, t: "MEXC · datos públicos", s: "GET /klines 1d" },
  { id: "validador", x: 255, y: 160, t: "Validador de velas", s: "cerradas · antigüedad ≤ 26 h" },
  { id: "variables", x: 395, y: 265, t: "Variables", s: "20 rezagos · SMA20 · vol20" },
  { id: "lstm", x: 545, y: 165, t: "Ensamble LSTM ×3", s: "semillas 42 · 123 · 2024" },
  { id: "estrategia", x: 545, y: 375, t: "Estrategia D", s: "cartera sin LLM" },
  { id: "gateway", x: 690, y: 70, t: "Gateway con API key", s: "127.0.0.1:8001" },
  { id: "llm", x: 860, y: 95, t: "LLM local (Ollama)", s: "llama3.2:3b" },
  { id: "herramientas", x: 890, y: 235, t: "Herramientas", s: "solo lectura" },
  { id: "riesgo", x: 725, y: 295, t: "Motor de riesgo", s: "determinista" },
  { id: "paper", x: 880, y: 405, t: "Simulador Paper", s: "3 carteras" },
  { id: "registro", x: 690, y: 480, t: "SQLite · bitácora", s: "sin duplicados" },
  { id: "ui", x: 430, y: 480, t: "Interfaz React", s: "X-API-Key" },
  { id: "humano", x: 235, y: 410, t: "Control humano", s: "iniciar · pausar · detener" },
];

// Orden del flujo de un ciclo (las partículas del pulso recorren estas aristas en orden).
const FLUJO: [string, string][] = [
  ["programador", "mexc"], ["mexc", "validador"], ["validador", "variables"], ["variables", "lstm"], ["lstm", "estrategia"],
  ["lstm", "gateway"], ["gateway", "llm"], ["llm", "herramientas"], ["herramientas", "riesgo"], ["estrategia", "riesgo"],
  ["riesgo", "paper"], ["paper", "registro"], ["registro", "ui"],
];
const OTRAS: [string, string][] = [["ui", "humano"], ["humano", "programador"], ["humano", "riesgo"]];

const NODO_POR_TIPO: Record<string, string> = {
  sin_respuesta: "mexc", limite_solicitudes: "mexc", dato_invalido: "mexc", ruta_bloqueada: "mexc", dato_atrasado: "validador",
  llm_no_disponible: "llm", json_invalido: "llm", respuesta_invalida: "llm", saldo_insuficiente: "paper", orden_rechazada: "paper",
  limite_riesgo: "riesgo", evento_duplicado: "registro", programador: "programador",
};

const pos = Object.fromEntries(NODOS.map((n) => [n.id, n]));
const curva = (a: string, b: string, k = 0.18) => {
  const p = pos[a], q = pos[b];
  const mx = (p.x + q.x) / 2, my = (p.y + q.y) / 2, dx = q.x - p.x, dy = q.y - p.y;
  return `M${p.x},${p.y} Q${mx - dy * k},${my + dx * k} ${q.x},${q.y}`;
};

export default function Cerebro({ estado }: { estado: Estado | null }) {
  const ev = useConsulta<Evento[]>("/api/eventos?limite=80", 5000);
  const eventos = ev.datos ?? [];
  const ultimoCiclo = eventos.find((e) => e.tipo === "ciclo");
  const [pulso, setPulso] = useState(0);
  const visto = useRef<number | null>(null);
  const grupo = useRef<SVGGElement>(null);

  useEffect(() => {   // un ciclo nuevo dispara un pulso que recorre el flujo
    if (!ultimoCiclo) return;
    if (visto.current !== null && ultimoCiclo.id !== visto.current) setPulso(Date.now());
    visto.current = ultimoCiclo.id;
  }, [ultimoCiclo]);

  const latTotal = estado?.ultimo_ciclo?.latencia_total_s ?? 8;
  const paso = Math.min(Math.max(latTotal / FLUJO.length, 0.25), 1.2);   // ritmo proporcional a la latencia real del último ciclo

  const reproducir = () => setPulso(Date.now());
  useEffect(() => {
    if (!pulso || !grupo.current) return;
    grupo.current.querySelectorAll("circle").forEach((c, i) => {
      c.querySelectorAll("animateMotion, set").forEach((a) => (a as unknown as SVGAnimationElement).beginElementAt(i * paso));
    });
  }, [pulso, paso]);

  const estadoNodos = useMemo(() => {
    const r: Record<string, "error" | "aviso"> = {};
    const corte = ultimoCiclo ? ultimoCiclo.id : 0;
    for (const e of eventos) {
      const nodo = NODO_POR_TIPO[e.tipo] ?? (e.tipo === "clave_incorrecta" ? (e.modo ? "gateway" : "ui") : null);
      if (!nodo) continue;
      const reciente = Date.now() - new Date(e.ts_utc).getTime() < 36 * 3600_000;
      if (e.nivel === "error" && e.id > corte) r[nodo] = "error";
      else if (e.nivel !== "info" && reciente && !r[nodo]) r[nodo] = "aviso";
    }
    return r;
  }, [eventos, ultimoCiclo]);

  const ag = estado?.agente.estado ?? "detenido";
  const nodos = NODOS.map((n) => n.id === "estrategia" ? { ...n, t: `Estrategia ${estado?.estrategia ?? "D"}` }
    : n.id === "mexc" ? { ...n, s: `GET /klines 1d · ${estado?.activo ?? "BTCUSDT"}` } : n);
  const fluye = ag === "corriendo";
  const color = (id: string) => estadoNodos[id] === "error" ? "var(--rojo)" : estadoNodos[id] === "aviso" ? "var(--ambar)" : "var(--azul)";

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <b className="tenue chico" style={{ letterSpacing: 1.2 }}>CEREBRO · CONSTELACIÓN DE MÓDULOS</b>
        <span className="separa" style={{ flex: 1 }} />
        <span className="tenue chico">cada estrella es un módulo; las partículas recorren el flujo al ritmo real de los ciclos</span>
        <button className="boton" onClick={reproducir}>Reproducir último ciclo</button>
      </div>
      <svg className="grafica lienzo" viewBox="0 0 1000 540">
        <defs>
          <filter id="brillo"><feGaussianBlur stdDeviation="3.5" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
          {[...FLUJO, ...OTRAS].map(([a, b]) => <path key={`p${a}${b}`} id={`a-${a}-${b}`} d={curva(a, b)} />)}
        </defs>
        {Array.from({ length: 70 }, (_, i) => <circle key={i} cx={(i * 137) % 1000} cy={(i * 89) % 540} r={i % 7 ? 0.7 : 1.2} fill="#3d4d6e" />)}
        {[...FLUJO, ...OTRAS].map(([a, b]) => (
          <use key={`u${a}${b}`} href={`#a-${a}-${b}`} fill="none" stroke={OTRAS.some(([x, y]) => x === a && y === b) ? "#26304a" : "#2b3b63"}
            strokeWidth={1.4} strokeDasharray={OTRAS.some(([x, y]) => x === a && y === b) ? "3 5" : undefined} />
        ))}
        {fluye && FLUJO.map(([a, b], i) => (
          <circle key={`f${a}${b}`} r={2.2} fill="#7fb0ff" opacity={0.7}>
            <animateMotion dur={`${2.6 + (i % 3) * 0.4}s`} repeatCount="indefinite" begin={`${(i * 0.37) % 2}s`}><mpath href={`#a-${a}-${b}`} /></animateMotion>
          </circle>
        ))}
        <g ref={grupo} key={pulso}>
          {pulso > 0 && FLUJO.map(([a, b]) => (
            <circle key={`p${a}${b}`} r={4.5} fill="#e9f1ff" filter="url(#brillo)" opacity={0}>
              <animateMotion dur={`${paso}s`} begin="indefinite" fill="remove"><mpath href={`#a-${a}-${b}`} /></animateMotion>
              <set attributeName="opacity" to="1" begin="indefinite" dur={`${paso}s`} />
            </circle>
          ))}
        </g>
        {nodos.map((n) => (
          <g key={n.id}>
            <circle cx={n.x} cy={n.y} r={14} fill={color(n.id)} opacity={0.14} className={fluye ? "latido" : undefined} />
            <circle cx={n.x} cy={n.y} r={6.5} fill={color(n.id)} filter="url(#brillo)" />
            <circle cx={n.x} cy={n.y} r={2.5} fill="#fff" />
            <text className="nodo-etiqueta" x={n.x} y={n.y + 26} textAnchor="middle">{n.t}</text>
            <text className="nodo-sub" x={n.x} y={n.y + 40} textAnchor="middle">{n.s}</text>
          </g>
        ))}
      </svg>
      <div className="rejilla r4" style={{ marginTop: 12 }}>
        <div className="tarjeta kpi"><div className={`valor ${fluye ? "positivo" : ""}`} style={{ fontSize: 20 }}>{ag}</div><div className="etiqueta">Régimen del agente</div>
          <div className="sub">{estado?.agente.motivo}</div></div>
        <div className="tarjeta kpi"><div className="valor" style={{ fontSize: 20 }}>{num(estado?.ultimo_ciclo?.latencia_llm_s, 1)} s</div>
          <div className="etiqueta">Latencia LLM (último ciclo)</div><div className="sub">ciclo completo {num(estado?.ultimo_ciclo?.latencia_total_s, 1)} s</div></div>
        <div className="tarjeta kpi"><div className="valor" style={{ fontSize: 20 }}>{Object.values(estadoNodos).filter((x) => x === "error").length}</div>
          <div className="etiqueta">Módulos en error</div><div className="sub">{Object.values(estadoNodos).filter((x) => x === "aviso").length} con avisos recientes</div></div>
        <div className="tarjeta kpi"><div className="valor" style={{ fontSize: 16 }}>{eventos[0]?.tipo ?? "—"}</div><div className="etiqueta">Último evento</div>
          <div className="sub">{eventos[0] ? `${hace(eventos[0].ts_utc)} · ${eventos[0].mensaje.slice(0, 60)}` : ""}</div></div>
      </div>
      <div className="leyenda"><span><i style={{ background: "var(--azul)" }} />operando</span><span><i style={{ background: "var(--ambar)" }} />aviso reciente</span>
        <span><i style={{ background: "var(--rojo)" }} />error desde el último ciclo</span><span><i style={{ background: "#2b3b63" }} />flujo del ciclo</span>
        <span><i style={{ background: "#26304a" }} />control humano</span></div>
    </div>
  );
}
