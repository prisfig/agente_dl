/** v2.2 · Indicadores financieros calculados en la interfaz a partir de las velas diarias de MEXC.
 *  El modelo usa solo los 20 rezagos del rendimiento, la SMA20 (filtro de la estrategia D) y la volatilidad de 20 días
 *  (stop móvil). Los demás indicadores son de referencia para quien decide si compra a mano: no cambian ninguna señal. */
import type { Vela } from "./tipos";

type N = number | null;

export function sma(x: number[], n: number): N[] {
  return x.map((_, i) => (i < n - 1 ? null : x.slice(i - n + 1, i + 1).reduce((a, b) => a + b, 0) / n));
}

export function desviacion(x: number[]): number {
  const m = x.reduce((a, b) => a + b, 0) / x.length;
  return Math.sqrt(x.reduce((a, b) => a + (b - m) ** 2, 0) / Math.max(1, x.length - 1));
}

/** Bandas de Bollinger (n, k): media móvil ± k desviaciones estándar. */
export function bollinger(x: number[], n = 20, k = 2): { sup: N[]; inf: N[] } {
  const sup: N[] = [], inf: N[] = [];
  x.forEach((_, i) => {
    if (i < n - 1) { sup.push(null); inf.push(null); return; }
    const v = x.slice(i - n + 1, i + 1);
    const m = v.reduce((a, b) => a + b, 0) / n;
    const d = Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / n);
    sup.push(m + k * d); inf.push(m - k * d);
  });
  return { sup, inf };
}

/** RSI de Wilder (n = 14). */
export function rsi(x: number[], n = 14): N[] {
  const r: N[] = x.map(() => null);
  if (x.length <= n) return r;
  let g = 0, p = 0;
  for (let i = 1; i <= n; i++) { const d = x[i] - x[i - 1]; if (d > 0) g += d; else p -= d; }
  g /= n; p /= n;
  r[n] = p === 0 ? 100 : 100 - 100 / (1 + g / p);
  for (let i = n + 1; i < x.length; i++) {
    const d = x[i] - x[i - 1];
    g = (g * (n - 1) + Math.max(d, 0)) / n;
    p = (p * (n - 1) + Math.max(-d, 0)) / n;
    r[i] = p === 0 ? 100 : 100 - 100 / (1 + g / p);
  }
  return r;
}

/** ATR de Wilder (n = 14), en unidades de precio. */
export function atr(v: Vela[], n = 14): N {
  if (v.length <= n) return null;
  const tr = v.slice(1).map((x, i) => Math.max(x.high - x.low, Math.abs(x.high - v[i].close), Math.abs(x.low - v[i].close)));
  let a = tr.slice(0, n).reduce((s, t) => s + t, 0) / n;
  for (let i = n; i < tr.length; i++) a = (a * (n - 1) + tr[i]) / n;
  return a;
}

export const rendimientos = (x: number[]) => x.slice(1).map((c, i) => c / x[i] - 1);

/** Variación entre el último cierre y el de hace d velas. */
export const variacion = (x: number[], d: number): N => (x.length > d ? x[x.length - 1] / x[x.length - 1 - d] - 1 : null);

/** Caída máxima desde un máximo previo (≤ 0). */
export function maxCaida(x: number[]): number {
  let pico = -Infinity, peor = 0;
  for (const c of x) { pico = Math.max(pico, c); peor = Math.min(peor, c / pico - 1); }
  return peor;
}

export function correlacion(a: number[], b: number[]): N {
  const n = Math.min(a.length, b.length);
  if (n < 5) return null;
  const x = a.slice(-n), y = b.slice(-n);
  const mx = x.reduce((s, v) => s + v, 0) / n, my = y.reduce((s, v) => s + v, 0) / n;
  let sxy = 0, sx = 0, sy = 0;
  for (let i = 0; i < n; i++) { sxy += (x[i] - mx) * (y[i] - my); sx += (x[i] - mx) ** 2; sy += (y[i] - my) ** 2; }
  return sx && sy ? sxy / Math.sqrt(sx * sy) : null;
}

/** Resumen de indicadores de un activo a partir de sus velas (las últimas son las más recientes). */
export function resumenIndicadores(v: Vela[]) {
  const c = v.map((x) => x.close);
  const ult = c[c.length - 1];
  const s20 = sma(c, 20), s50 = sma(c, 50);
  const bb = bollinger(c);
  const r = rsi(c);
  const rend = rendimientos(c);
  const vol20 = rend.length >= 20 ? desviacion(rend.slice(-20)) : null;
  const a = atr(v);
  const ult30 = c.slice(-30);
  const volUsdt = v.map((x) => x.volume * x.close);
  const i = c.length - 1;
  const sup = bb.sup[i], inf = bb.inf[i];
  return {
    cierre: ult,
    var1: variacion(c, 1), var7: variacion(c, 7), var30: variacion(c, 30), varPeriodo: c.length > 1 ? ult / c[0] - 1 : null,
    sma20: s20[i], sma50: s50[i],
    dist20: s20[i] ? ult / (s20[i] as number) - 1 : null, dist50: s50[i] ? ult / (s50[i] as number) - 1 : null,
    bbSup: sup, bbInf: inf, pctB: sup != null && inf != null && sup !== inf ? (ult - inf) / (sup - inf) : null,
    rsi14: r[i], atr14: a, atrPct: a != null ? a / ult : null,
    vol20, volAnual: vol20 != null ? vol20 * Math.sqrt(365) : null,
    max30: Math.max(...ult30), min30: Math.min(...ult30), caidaMax: maxCaida(c),
    volUsdtUlt: volUsdt[volUsdt.length - 1], volUsdtProm20: volUsdt.length >= 20 ? volUsdt.slice(-20).reduce((s, x) => s + x, 0) / 20 : null,
    series: { s20, s50, bbSup: bb.sup, bbInf: bb.inf, rsi: r },
  };
}
