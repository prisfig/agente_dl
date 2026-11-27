// v2.4 · Pruebas de los indicadores financieros de la interfaz (node:test, sin dependencias extra).
// Se corren con `npm test`: compila src/indicadores.ts a .prueba/ y compara contra valores calculados a mano.
import assert from "node:assert/strict";
import test from "node:test";
import { atr, bollinger, correlacion, desviacion, maxCaida, rendimientos, resumenIndicadores, rsi, sma, variacion } from "../.prueba/indicadores.js";

const cerca = (a, b, tol = 1e-9) => assert.ok(Math.abs(a - b) <= tol, `${a} ≠ ${b}`);
const vela = (fecha, o, h, l, c, v = 10) => ({ fecha, open: o, high: h, low: l, close: c, volume: v, close_time: 0 });

test("SMA: promedio móvil simple y nulos al inicio", () => {
  assert.deepEqual(sma([1, 2, 3, 4, 5], 3), [null, null, 2, 3, 4]);
});

test("Bandas de Bollinger: media ± 2 desviaciones (poblacional)", () => {
  const x = Array.from({ length: 20 }, (_, i) => (i % 2 ? 12 : 8));   // media 10, desviación 2
  const b = bollinger(x, 20, 2);
  cerca(b.sup[19], 14); cerca(b.inf[19], 6);
  assert.equal(b.sup[18], null);
  const constante = bollinger(Array(25).fill(5));
  cerca(constante.sup[24], 5); cerca(constante.inf[24], 5);
});

test("RSI de Wilder: 100 si solo sube, 0 si solo baja, 50 si sube y baja lo mismo", () => {
  const sube = Array.from({ length: 30 }, (_, i) => 100 + i);
  const baja = Array.from({ length: 30 }, (_, i) => 100 - i);
  const zigzag = Array.from({ length: 30 }, (_, i) => (i % 2 ? 101 : 100));
  cerca(rsi(sube)[29], 100); cerca(rsi(baja)[29], 0);
  assert.equal(rsi(sube)[13], null);
  cerca(rsi(zigzag)[15], 50, 5);   // promedios suavizados casi iguales
});

test("ATR de Wilder: rango verdadero constante sin huecos", () => {
  const v = Array.from({ length: 30 }, (_, i) => vela(`d${i}`, 100, 101, 99, 100));
  cerca(atr(v, 14), 2);
  // un hueco entre cierre previo y máximo actual cuenta en el rango verdadero
  const h = [vela("a", 100, 101, 99, 100), vela("b", 104, 106, 104, 105)];
  cerca(atr([...h, ...h], 1), 6);   // |106 − 100| y |99 − 105|
});

test("Rendimientos, variación, caída máxima y desviación", () => {
  assert.deepEqual(rendimientos([100, 110, 99]).map((r) => +r.toFixed(10)), [0.1, -0.1]);
  cerca(variacion([100, 105, 120], 2), 0.2);
  assert.equal(variacion([100], 3), null);
  cerca(maxCaida([100, 120, 90, 110]), 90 / 120 - 1);
  cerca(desviacion([2, 4, 4, 4, 5, 5, 7, 9]), Math.sqrt(32 / 7));
});

test("Correlación de Pearson: +1, −1 y nula con pocos datos", () => {
  const x = [1, 2, 3, 4, 5, 6];
  cerca(correlacion(x, x.map((v) => 2 * v + 1)), 1);
  cerca(correlacion(x, x.map((v) => -v)), -1);
  assert.equal(correlacion([1, 2, 3], [1, 2, 3]), null);
});

test("Resumen de indicadores con 60 velas", () => {
  const v = Array.from({ length: 60 }, (_, i) => vela(`2026-01-${i}`, 100 + i, 101 + i, 99 + i, 100 + i));
  const r = resumenIndicadores(v);
  cerca(r.cierre, 159); cerca(r.sma20, (140 + 159) / 2); cerca(r.var1, 159 / 158 - 1);
  cerca(r.rsi14, 100); cerca(r.max30, 159); cerca(r.min30, 130); cerca(r.caidaMax, 0);
  assert.ok(r.pctB > 0.5);
});
