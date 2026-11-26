"""Exporta los registros del agente a CSV y calcula las métricas del informe.

Uso (desde la carpeta agente_dl):
    python agente/exportar_registros.py

Lee las bases SQLite de agente/datos/ en modo solo lectura (no modifica nada) y escribe en agente/registros/:
  - ciclos.csv, decisiones.csv, ordenes.csv, eventos.csv, patrimonio.csv  (las 15 bases juntas, con columna `simbolo`)
  - metricas_por_activo.csv   (una fila por activo, modo y cartera)
  - metricas_totales.csv      (suma de los 15 activos por cartera, solo ciclos en vivo)
  - serie_patrimonio_total.csv (patrimonio diario sumado de los 15 activos, en vivo)
  - llm_por_activo.csv        (propuestas del LLM, acuerdo con la señal del modelo, avisos y latencia)
  - operaciones_cerradas.csv  (cada compra con su venta y su resultado)

Definiciones:
  - Rendimiento neto: patrimonio al último cierre / 50,000 − 1 (costo 0 %, deslizamiento 0 %).
  - Drawdown máximo: mayor caída desde un máximo previo de la serie diaria de patrimonio (empieza en 50,000).
  - Win Rate: operaciones cerradas (compra → venta) con resultado > 0 / operaciones cerradas.
  - Acciones rechazadas: decisiones en que el motor de riesgo cambió la propuesta (aprobada = 0).
  - Total de 15 activos: cada activo vale 50,000 antes de su primer ciclo (capital sin usar).
Solo usa la biblioteca estándar de Python.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import statistics
from collections import Counter, defaultdict

RAIZ = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(RAIZ, "datos")
SALIDA = os.path.join(RAIZ, "registros")
CAPITAL = 50_000.0
CARTERAS = ("sin_llm", "con_llm", "comprar_y_mantener")
TABLAS = ("ciclos", "decisiones", "ordenes", "eventos", "patrimonio")


def simbolo_de(ruta: str) -> str:
    nombre = os.path.basename(ruta)
    return "BTCUSDT" if nombre == "agente.sqlite3" else nombre[len("agente_"):-len(".sqlite3")]


def conectar(ruta: str):
    import sqlite3
    c = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def escribir(nombre: str, filas: list[dict]) -> None:
    ruta = os.path.join(SALIDA, nombre)
    if not filas:
        open(ruta, "w").close()
        return
    campos = list(filas[0].keys())
    for f in filas:
        for k in f:
            if k not in campos:
                campos.append(k)
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


def drawdown_max(serie: list[float]) -> float:
    pico, dd = serie[0], 0.0
    for v in serie:
        pico = max(pico, v)
        dd = min(dd, v / pico - 1)
    return dd


def main() -> None:
    os.makedirs(SALIDA, exist_ok=True)
    bases = sorted(glob.glob(os.path.join(DATOS, "agente*.sqlite3")))
    crudos = {t: [] for t in TABLAS}
    metricas, llm_filas, cerradas_filas = [], [], []
    series_vivo: dict[str, dict[str, dict[str, float]]] = {}

    for ruta in bases:
        s = simbolo_de(ruta)
        c = conectar(ruta)
        for t in TABLAS:
            for r in c.execute(f"SELECT * FROM {t} ORDER BY rowid"):
                crudos[t].append({"simbolo": s, **dict(r)})

        modos = [m[0] for m in c.execute("SELECT DISTINCT modo FROM ciclos ORDER BY modo DESC")]
        for modo in modos:
            ciclos = c.execute("SELECT * FROM ciclos WHERE modo=? ORDER BY fecha_vela", (modo,)).fetchall()
            senal = {r["id"]: json.loads(r["observacion"]).get("senal") for r in ciclos}
            for cartera in CARTERAS:
                pat = c.execute("SELECT fecha_vela, patrimonio FROM patrimonio WHERE modo=? AND cartera=? "
                                "ORDER BY fecha_vela", (modo, cartera)).fetchall()
                serie = [CAPITAL] + [r["patrimonio"] for r in pat]
                if modo == "vivo":
                    series_vivo.setdefault(s, {})[cartera] = {r["fecha_vela"]: r["patrimonio"] for r in pat}
                ords = c.execute("SELECT * FROM ordenes WHERE modo=? AND cartera=? AND estado='ejecutada' "
                                 "ORDER BY id", (modo, cartera)).fetchall()
                abierta, cerradas = None, []
                for o in ords:
                    if o["lado"] == "COMPRAR":
                        abierta = o
                    elif o["lado"] == "VENDER" and abierta is not None:
                        res = o["monto"] - abierta["monto"] - (o["costo"] or 0) - (abierta["costo"] or 0)
                        cerradas.append(res)
                        motivo_venta = c.execute(
                            "SELECT motivos FROM decisiones WHERE ciclo_id=? AND cartera=?",
                            (o["ciclo_id"], cartera)).fetchone()
                        cerradas_filas.append({
                            "simbolo": s, "modo": modo, "cartera": cartera,
                            "fecha_compra": abierta["fecha_vela"], "precio_compra": abierta["precio"],
                            "fecha_venta": o["fecha_vela"], "precio_venta": o["precio"],
                            "resultado_usdt": round(res, 2),
                            "rendimiento": round(o["precio"] / abierta["precio"] - 1, 6),
                            "salida": ("stop_movil" if motivo_venta and "stop_movil" in (motivo_venta[0] or "")
                                       else "senal"),
                        })
                        abierta = None
                decs = c.execute("SELECT * FROM decisiones WHERE modo=? AND cartera=?", (modo, cartera)).fetchall()
                motivos = Counter()
                for d in decs:
                    if not d["aprobada"]:
                        for m in json.loads(d["motivos"] or "[]"):
                            motivos[m.split(":")[0]] += 1
                ganadas = sum(1 for x in cerradas if x > 0)
                metricas.append({
                    "simbolo": s, "modo": modo, "cartera": cartera,
                    "primera_vela": ciclos[0]["fecha_vela"], "ultima_vela": ciclos[-1]["fecha_vela"],
                    "ciclos": len(ciclos),
                    "patrimonio_final": round(serie[-1], 2),
                    "rendimiento_neto": round(serie[-1] / CAPITAL - 1, 6),
                    "drawdown_max": round(drawdown_max(serie), 6),
                    "ordenes": len(ords),
                    "compras": sum(1 for o in ords if o["lado"] == "COMPRAR"),
                    "ventas": sum(1 for o in ords if o["lado"] == "VENDER"),
                    "operaciones_cerradas": len(cerradas),
                    "ganadas": ganadas,
                    "win_rate": round(ganadas / len(cerradas), 4) if cerradas else "",
                    "posicion_abierta": "si" if abierta is not None else "no",
                    "acciones_rechazadas": sum(1 for d in decs if not d["aprobada"]),
                    "rechazos_por_motivo": "; ".join(f"{k}={v}" for k, v in sorted(motivos.items())),
                })

            # Resumen del LLM (cartera con_llm)
            props, contra, avisos, reintentos = Counter(), 0, 0, 0
            for d in c.execute("SELECT * FROM decisiones WHERE modo=? AND cartera='con_llm'", (modo,)):
                props[d["propuesta"]] += 1
                if d["propuesta"] == "COMPRAR" and senal.get(d["ciclo_id"]) != "comprar":
                    contra += 1
                det = json.loads(d["detalle_llm"]) if d["detalle_llm"] else {}
                avisos += 1 if det.get("avisos") else 0
                reintentos += 1 if (det.get("intentos") or 1) > 1 else 0
            lat = [r["latencia_llm_s"] for r in ciclos if r["latencia_llm_s"] is not None]
            tot = [r["latencia_total_s"] for r in ciclos if r["latencia_total_s"] is not None]
            llm_filas.append({
                "simbolo": s, "modo": modo, "ciclos": len(ciclos),
                "propone_comprar": props["COMPRAR"], "propone_mantener": props["MANTENER"],
                "propone_vender": props["VENDER"],
                "comprar_sin_senal_del_modelo": contra,
                "senales_comprar_del_modelo": sum(1 for v in senal.values() if v == "comprar"),
                "justificaciones_con_aviso": avisos, "ciclos_con_reintento": reintentos,
                "latencia_llm_media_s": round(statistics.mean(lat), 1) if lat else "",
                "latencia_llm_max_s": round(max(lat), 1) if lat else "",
                "latencia_ciclo_media_s": round(statistics.mean(tot), 1) if tot else "",
            })
        c.close()

    # Totales en vivo (15 activos; 50,000 por activo antes de su primer ciclo)
    fechas = sorted({f for s in series_vivo.values() for car in s.values() for f in car})
    serie_total, totales = [], []
    for cartera in CARTERAS:
        valores = []
        for f in fechas:
            v = 0.0
            for s, cars in series_vivo.items():
                previas = [x for x in cars[cartera] if x <= f]
                v += cars[cartera][max(previas)] if previas else CAPITAL
            valores.append(v)
        capital_total = CAPITAL * len(series_vivo)
        filas_m = [m for m in metricas if m["modo"] == "vivo" and m["cartera"] == cartera]
        ganadas = sum(m["ganadas"] for m in filas_m)
        cerr = sum(m["operaciones_cerradas"] for m in filas_m)
        totales.append({
            "cartera": cartera, "activos": len(series_vivo), "capital_inicial": capital_total,
            "patrimonio_final": round(valores[-1], 2),
            "rendimiento_neto": round(valores[-1] / capital_total - 1, 6),
            "drawdown_max": round(drawdown_max([capital_total] + valores), 6),
            "ordenes": sum(m["ordenes"] for m in filas_m),
            "operaciones_cerradas": cerr, "ganadas": ganadas,
            "win_rate": round(ganadas / cerr, 4) if cerr else "",
            "acciones_rechazadas": sum(m["acciones_rechazadas"] for m in filas_m),
        })
        for f, v in zip(fechas, valores):
            serie_total.append({"fecha_vela": f, "cartera": cartera, "patrimonio_total": round(v, 2)})

    for t in TABLAS:
        escribir(f"{t}.csv", crudos[t])
    escribir("metricas_por_activo.csv", metricas)
    escribir("metricas_totales.csv", totales)
    escribir("serie_patrimonio_total.csv", serie_total)
    escribir("llm_por_activo.csv", llm_filas)
    escribir("operaciones_cerradas.csv", cerradas_filas)
    print(f"{len(bases)} bases exportadas a {SALIDA}")
    for t in totales:
        print(f"  {t['cartera']:<20} {t['patrimonio_final']:>12,.2f}  {t['rendimiento_neto']:+.2%}  "
              f"DD {t['drawdown_max']:.2%}  órdenes {t['ordenes']}  WR {t['win_rate']}")


if __name__ == "__main__":
    main()
