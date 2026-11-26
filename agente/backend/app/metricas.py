"""Comparación con el mismo periodo y costos: sin LLM, con LLM y comprar y mantener."""
from __future__ import annotations

import json

from .db import Base


def metricas(db: Base, modo: str, capital_inicial: float) -> dict:
    salida = {}
    lat = db.consultar("SELECT AVG(latencia_llm_s) AS m, MAX(latencia_llm_s) AS x, COUNT(*) AS n, MIN(fecha_vela) AS d0, "
                       "MAX(fecha_vela) AS d1 FROM ciclos WHERE modo=?", (modo,))[0]
    for nombre in ("sin_llm", "con_llm", "comprar_y_mantener"):
        serie = db.consultar("SELECT fecha_vela, patrimonio FROM patrimonio WHERE modo=? AND cartera=? ORDER BY fecha_vela",
                             (modo, nombre))
        if not serie:
            continue
        valores = [s["patrimonio"] for s in serie]
        pico, dd = capital_inicial, 0.0
        for v in valores:
            pico = max(pico, v)
            dd = min(dd, v / pico - 1)
        ordenes = db.consultar("SELECT lado, monto, costo, estado FROM ordenes WHERE modo=? AND cartera=? ORDER BY id",
                               (modo, nombre))
        ejecutadas = [o for o in ordenes if o["estado"] == "ejecutada"]
        ganadoras = cerradas = 0
        compra = None
        for o in ejecutadas:
            if o["lado"] == "COMPRAR":
                compra = o
            elif o["lado"] == "VENDER" and compra is not None:
                cerradas += 1
                if (o["monto"] - o["costo"]) - (compra["monto"] + compra["costo"]) > 0:
                    ganadoras += 1
                compra = None
        dec = db.consultar("SELECT aprobada, motivos FROM decisiones WHERE modo=? AND cartera=?", (modo, nombre))
        rechazadas = sum(1 for d in dec if not d["aprobada"])
        salida[nombre] = {
            "ciclos": len(serie),
            "patrimonio_final": round(valores[-1], 2),
            "rendimiento_neto": valores[-1] / capital_inicial - 1,
            "max_drawdown": dd,
            "operaciones": len(ejecutadas),
            "operaciones_cerradas": cerradas,
            "win_rate": (ganadoras / cerradas) if cerradas else None,
            "acciones_rechazadas": rechazadas,
            "ordenes_rechazadas": sum(1 for o in ordenes if o["estado"] == "rechazada"),
            "motivos_rechazo": _contar_motivos(dec),
        }
    return {"modo": modo, "periodo": {"desde": lat["d0"], "hasta": lat["d1"], "ciclos": lat["n"]},
            "latencia_llm_s": {"media": lat["m"], "maxima": lat["x"]},
            "capital_inicial": capital_inicial, "carteras": salida}


def _contar_motivos(decisiones: list[dict]) -> dict:
    conteo: dict[str, int] = {}
    for d in decisiones:
        for m in json.loads(d["motivos"] or "[]"):
            clave = m.split(":")[0]
            conteo[clave] = conteo.get(clave, 0) + 1
    return conteo
