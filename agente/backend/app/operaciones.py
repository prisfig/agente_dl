"""Vista de operaciones de todas las carteras Paper (v1.8): posiciones abiertas, historial de operaciones cerradas,
saldo total y estado de los límites de riesgo, sumando los activos del backend.

Solo lee lo que ya guardó cada agente (órdenes ejecutadas, decisiones, carteras y patrimonio); no cambia ninguna
decisión. Los precios "actuales" de MEXC son informativos: el patrimonio oficial se valúa al último cierre diario,
que es el precio con el que decide y ejecuta el agente."""
from __future__ import annotations

import json
from datetime import date

from .paper import COMPRAR, VENDER

CARTERAS = ("sin_llm", "con_llm", "comprar_y_mantener")


def _motivo_salida(cartera: str, orden: dict, decision: dict | None) -> str:
    if orden.get("motivo") == "liquidacion_manual":
        return "liquidación manual"
    motivos = json.loads((decision or {}).get("motivos") or "[]")
    if any(m.startswith("stop_movil") for m in motivos):
        return "stop móvil"
    if cartera == "sin_llm":
        return "señal del modelo: efectivo"
    return "el LLM propuso VENDER"


def _motivo_entrada(cartera: str) -> str:
    return {"sin_llm": "señal del modelo: comprar", "con_llm": "el LLM propuso COMPRAR (aprobado por riesgo)",
            "comprar_y_mantener": "referencia pasiva: compra en el primer ciclo"}.get(cartera, "")


def operaciones_activo(agente, modo: str, cartera: str, capital: float, precio_actual: float | None) -> dict:
    db, simbolo = agente.db, agente.simbolo
    ordenes = db.consultar("SELECT fecha_vela, lado, cantidad, precio, monto, costo, motivo, ts_utc FROM ordenes "
                           "WHERE modo=? AND cartera=? AND estado='ejecutada' ORDER BY id", (modo, cartera))
    decisiones = {d["fecha_vela"]: d for d in db.consultar(
        "SELECT fecha_vela, propuesta, accion_final, motivos FROM decisiones WHERE modo=? AND cartera=?", (modo, cartera))}
    ultimo = db.ultimo_ciclo(modo)
    cierre = ultimo["observacion"]["cierre"] if ultimo else None
    fecha_ultima = ultimo["fecha_vela"] if ultimo else None
    senal_hoy = (ultimo["observacion"].get("senal") or ultimo["observacion"].get("senal_d")) if ultimo else None

    cerradas, compra = [], None
    for o in ordenes:
        if o["lado"] == COMPRAR:
            compra = o
        elif o["lado"] == VENDER and compra is not None:
            invertido = compra["monto"] + compra["costo"]
            recibido = o["monto"] - o["costo"]
            cerradas.append({
                "simbolo": simbolo, "activo_base": agente.activo_base, "cartera": cartera,
                "fecha_compra": compra["fecha_vela"], "precio_compra": compra["precio"], "cantidad": compra["cantidad"],
                "fecha_venta": o["fecha_vela"], "precio_venta": o["precio"],
                "motivo_entrada": _motivo_entrada(cartera),
                "motivo_salida": _motivo_salida(cartera, o, decisiones.get(o["fecha_vela"])),
                "dias": (date.fromisoformat(o["fecha_vela"]) - date.fromisoformat(compra["fecha_vela"])).days,
                "pnl": recibido - invertido, "pnl_pct": recibido / invertido - 1 if invertido else None,
                "comisiones": compra["costo"] + o["costo"],
            })
            compra = None

    c = db.carteras(modo).get(cartera)
    abierta = None
    if c is not None and c.en_posicion:
        invertido = (compra["monto"] + compra["costo"]) if compra else c.btc * (c.precio_entrada or 0)
        valor_cierre = c.btc * cierre if cierre else None
        valor_actual = c.btc * precio_actual if precio_actual else None
        abierta = {
            "simbolo": simbolo, "activo_base": agente.activo_base, "cartera": cartera, "lado": "LONG",
            "cantidad": c.btc, "precio_entrada": c.precio_entrada,
            "fecha_compra": compra["fecha_vela"] if compra else None,
            "motivo_entrada": _motivo_entrada(cartera),
            "invertido": invertido,
            "ultimo_cierre": cierre, "fecha_ultimo_cierre": fecha_ultima,
            "precio_actual": precio_actual,
            "stop": c.stop, "distancia_stop": (cierre / c.stop - 1) if (c.stop and cierre) else None,
            "pnl": (valor_cierre - invertido) if valor_cierre is not None else None,
            "pnl_pct": (valor_cierre / invertido - 1) if (valor_cierre is not None and invertido) else None,
            "pnl_actual": (valor_actual - invertido) if valor_actual is not None else None,
            "pnl_actual_pct": (valor_actual / invertido - 1) if (valor_actual is not None and invertido) else None,
            "dias": ((date.fromisoformat(fecha_ultima) - date.fromisoformat(compra["fecha_vela"])).days
                     if (compra and fecha_ultima) else None),
            "senal_hoy": senal_hoy,
        }

    serie = db.consultar("SELECT fecha_vela, patrimonio FROM patrimonio WHERE modo=? AND cartera=? ORDER BY fecha_vela",
                         (modo, cartera))
    var_dia = (serie[-1]["patrimonio"] / serie[-2]["patrimonio"] - 1) if len(serie) >= 2 else None
    patrimonio = c.patrimonio(cierre) if (c is not None and cierre) else (c.efectivo if c is not None else capital)
    estado = db.estado()
    return {
        "simbolo": simbolo, "activo_base": agente.activo_base, "estrategia": agente.modelo.estrategia,
        "estado_agente": estado["estado"], "errores_consecutivos": estado["errores_consecutivos"],
        "ultima_vela": fecha_ultima, "ultimo_cierre": cierre, "senal_hoy": senal_hoy,
        "patrimonio": patrimonio, "efectivo": c.efectivo if c is not None else capital,
        "invertido": (c.btc * cierre) if (c is not None and c.en_posicion and cierre) else 0.0,
        "patrimonio_actual": ((c.efectivo + c.btc * precio_actual) if (c is not None and precio_actual) else patrimonio),
        "variacion_dia": var_dia, "bloqueo_perdida": bool(c.bloqueo_perdida) if c is not None else False,
        "comisiones": sum(o["costo"] for o in ordenes),
        "abierta": abierta, "cerradas": cerradas,
        "serie": {s["fecha_vela"]: s["patrimonio"] for s in serie},
    }


def resumen_operaciones(agentes: dict, modo: str, cartera: str, capital: float, precios: dict, limites) -> dict:
    activos = [operaciones_activo(a, modo, cartera, capital, precios.get(s)) for s, a in agentes.items()]
    n = len(activos)
    capital_total = n * capital
    saldo = sum(x["patrimonio"] for x in activos)
    abiertas = [x["abierta"] for x in activos if x["abierta"]]
    cerradas = sorted((t for x in activos for t in x["cerradas"]), key=lambda t: (t["fecha_venta"], t["simbolo"]), reverse=True)
    ganancias = sum(t["pnl"] for t in cerradas if t["pnl"] > 0)
    perdidas = -sum(t["pnl"] for t in cerradas if t["pnl"] < 0)

    # Serie del saldo total: por fecha, último patrimonio conocido de cada activo (capital antes de su primer ciclo).
    fechas = sorted({f for x in activos for f in x["serie"]})
    total_serie, ultimo = [], {x["simbolo"]: capital for x in activos}
    for f in fechas:
        for x in activos:
            if f in x["serie"]:
                ultimo[x["simbolo"]] = x["serie"][f]
        total_serie.append({"fecha_vela": f, "saldo": sum(ultimo.values())})
    pico, dd = capital_total, 0.0
    for p in total_serie:
        pico = max(pico, p["saldo"])
        dd = min(dd, p["saldo"] / pico - 1)

    variaciones = [x["variacion_dia"] for x in activos if x["variacion_dia"] is not None]
    peor = min(activos, key=lambda x: x["variacion_dia"] if x["variacion_dia"] is not None else 0) if variaciones else None
    con_precio_actual = [a for a in abiertas if a["pnl_actual"] is not None]
    return {
        "modo": modo, "cartera": cartera, "n_activos": n, "capital_por_activo": capital,
        "capital_inicial_total": capital_total,
        "saldo_total": saldo,
        "pnl_total": saldo - capital_total, "rendimiento": saldo / capital_total - 1 if capital_total else None,
        "efectivo_total": sum(x["efectivo"] for x in activos),
        "invertido_total": sum(x["invertido"] for x in activos),
        "pnl_realizado": sum(t["pnl"] for t in cerradas),
        "pnl_no_realizado": sum(a["pnl"] or 0 for a in abiertas),
        "saldo_total_actual": sum(x["patrimonio_actual"] for x in activos),
        "pnl_no_realizado_actual": (sum(a["pnl_actual"] for a in con_precio_actual) if con_precio_actual
                                    else (0.0 if precios and not abiertas else None)),
        "precios_actuales_disponibles": bool(precios),
        "max_drawdown": dd,
        "operaciones_cerradas": len(cerradas),
        "ganadoras": sum(1 for t in cerradas if t["pnl"] > 0),
        "acierto": (sum(1 for t in cerradas if t["pnl"] > 0) / len(cerradas)) if cerradas else None,
        "profit_factor": (ganancias / perdidas) if perdidas else None,
        "sin_perdidas": bool(cerradas) and not perdidas,
        "comisiones": sum(x["comisiones"] for x in activos),
        "riesgo": {
            "perdida_diaria_maxima": limites.perdida_diaria_maxima,
            "peor_variacion_dia": peor["variacion_dia"] if peor else None,
            "peor_activo_dia": peor["simbolo"] if peor else None,
            "exposicion": (sum(x["invertido"] for x in activos) / saldo) if saldo else 0.0,
            "exposicion_maxima": limites.exposicion_maxima,
            "activos_con_bloqueo": [x["simbolo"] for x in activos if x["bloqueo_perdida"]],
            "bloqueados_todas_carteras": bloqueos_vivo(agentes) if modo == "vivo" else {},
            "activos_pausados": [x["simbolo"] for x in activos if x["estado_agente"] != "corriendo"],
            "stops_cercanos": [a["simbolo"] for a in abiertas if a["distancia_stop"] is not None and a["distancia_stop"] < 0.02],
            "stop_movil_k_vol": limites.stop_movil_k_vol,
        },
        "abiertas": sorted(abiertas, key=lambda a: a["simbolo"]),
        "cerradas": cerradas,
        "por_activo": [{k: v for k, v in x.items() if k not in ("abierta", "cerradas", "serie")} for x in activos],
        "serie_saldo": total_serie,
    }


def comparacion_carteras(agentes: dict, modo: str, capital: float) -> dict:
    """Saldo total de las tres carteras con el mismo periodo y activos (para la cabecera de Operaciones)."""
    salida = {}
    for cartera in CARTERAS:
        saldo, abiertas = 0.0, 0
        for a in agentes.values():
            c = a.db.carteras(modo).get(cartera)
            ultimo = a.db.ultimo_ciclo(modo)
            cierre = ultimo["observacion"]["cierre"] if ultimo else None
            saldo += c.patrimonio(cierre) if (c is not None and cierre) else capital
            abiertas += int(c is not None and c.en_posicion)
        total = capital * len(agentes)
        salida[cartera] = {"saldo_total": saldo, "pnl_total": saldo - total, "rendimiento": saldo / total - 1 if total else None,
                           "posiciones_abiertas": abiertas}
    return salida


def bloqueos_vivo(agentes: dict) -> dict[str, list[str]]:
    """Activos con el control de pérdida diaria activo en alguna cartera en vivo: {simbolo: [carteras]}."""
    salida = {}
    for simbolo, a in agentes.items():
        carteras = [n for n, c in a.db.carteras("vivo").items() if c.bloqueo_perdida]
        if carteras:
            salida[simbolo] = sorted(carteras)
    return salida


def rearmar_bloqueados(agentes: dict) -> dict:
    """v1.9: rearma, con una sola acción del usuario, todos los activos que tienen el bloqueo activo.

    Es lo mismo que pulsar «Rearmar control de pérdida» en cada uno: quita el bloqueo de sus carteras y registra el
    evento de control en la base de ese activo. Los activos sin bloqueo no se tocan ni se registran.
    """
    bloqueados = bloqueos_vivo(agentes)
    for simbolo, carteras in bloqueados.items():
        agentes[simbolo].rearmar_riesgo("vivo", origen="rearmar_todos", carteras_bloqueadas=carteras)
    return {"ok": True, "rearmados": sorted(bloqueados), "detalle": bloqueados,
            "sin_bloqueo": sorted(set(agentes) - set(bloqueados))}
