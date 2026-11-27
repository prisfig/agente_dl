"""v2.3 · Niveles sugeridos para la compra MANUAL de cada señal: stop, take profit y tamaño de posición (Kelly fraccional).

No cambian la simulación del protocolo (exposición máx. 100 %, salida por señal o stop) ni ninguna decisión del agente:
solo se muestran en la pestaña Señales y en el correo, para quien decide comprar a mano en MEXC.

- Stop: el mismo stop móvil del motor de riesgo, cierre × (1 − k × vol20).
- Take profit: relación riesgo/beneficio fija R (1.5 por defecto) sobre la distancia al stop: cierre + R × (cierre − stop).
- Tiempo máximo: si en `dias_maximos` días (10 por defecto) el precio no tocó ni el stop ni el take profit, salir a mano:
  la tesis de corto plazo (pronóstico del día siguiente) ya no aplica. (v2.4)
- Tamaño: Kelly para una apuesta que gana R veces lo que arriesga, f* = W − (1 − W) / R, con W = acierto de la estrategia
  elegida de ese activo en VALIDACIÓN (VA; nunca en la prueba, TE). Se usa una fracción de Kelly (½) con tope (25 %) y solo
  si hubo un mínimo de operaciones en VA; si f* ≤ 0, el tamaño sugerido es 0 % (Kelly negativo: la ventaja no alcanza).
"""


def niveles_sugeridos(cfg_sug: dict | None, simbolo: str, cierre: float | None, vol20: float | None, k_stop: float) -> dict | None:
    if not cfg_sug or cierre is None or vol20 is None or cierre <= 0 or vol20 <= 0:
        return None
    r = float(cfg_sug.get("r_tp", 1.5))
    stop = cierre * (1 - k_stop * vol20)
    take_profit = cierre + r * (cierre - stop)
    va = (cfg_sug.get("va_por_activo") or {}).get(simbolo)
    fraccion, tope = float(cfg_sug.get("kelly_fraccion", 0.5)), float(cfg_sug.get("kelly_tope", 0.25))
    minimo = int(cfg_sug.get("kelly_min_operaciones", 15))
    salida = {"stop": stop, "take_profit": take_profit, "r": r, "dias_maximos": int(cfg_sug.get("dias_maximos", 10)), "riesgo_pct": k_stop * vol20, "beneficio_pct": r * k_stop * vol20,
              "kelly_completo": None, "tamano": None, "win_rate_va": None, "operaciones_va": None, "kelly_motivo": "sin datos de VA"}
    if va:
        w, n = float(va["win_rate"]), int(va["operaciones"])
        salida.update({"win_rate_va": w, "operaciones_va": n})
        if n < minimo:
            salida["kelly_motivo"] = f"solo {n} operaciones en VA (mínimo {minimo})"
        else:
            f = w - (1 - w) / r
            salida.update({"kelly_completo": f, "tamano": max(0.0, min(tope, f * fraccion)),
                           "kelly_motivo": "Kelly negativo: la ventaja medida en VA no alcanza" if f <= 0 else
                           f"{fraccion:g} × Kelly con tope de {tope:.0%}"})
    return salida
