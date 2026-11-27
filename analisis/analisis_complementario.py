"""Análisis complementario (v2.3, 27 nov 2026). SOLO LECTURA de resultados que ya existen: no reentrena, no cambia el modelo,
las reglas ni la simulación, y no vuelve a elegir nada con la prueba (TE). Responde a la rúbrica del profesor:

1. Métricas completas de la estrategia D de BTC en TE (Sharpe, Sortino, expectativa, profit factor, intervalo de Wilson).
2. Líneas base adicionales en el mismo TE: operar al azar con la misma exposición (prueba de permutación), regla técnica
   pura (cierre > SMA20) y cruce de medias (SMA20 > SMA50).
3. Sensibilidad a costos y deslizamiento, y costo de equilibrio.
4. Resultado por régimen de mercado (alcista / bajista según el cierre frente a su SMA50).
5. Deriva en vivo: error del pronóstico en los ciclos en vivo frente al error del TE, con la regla de reentrenamiento.

Uso:  python analisis/analisis_complementario.py      (desde la raíz del repositorio; requiere pandas y numpy)
Salidas: resultados/analisis_complementario/*.csv y Analisis_Complementario.md (raíz).
"""
import json
import math
import os

import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAL = os.path.join(RAIZ, "resultados", "analisis_complementario")
os.makedirs(SAL, exist_ok=True)
COSTO = 0.001                 # comisión del TE de la práctica: 0.10 % por operación
SEMILLA, N_PERM = 2024, 10_000


def wilson(g, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = g / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (c - m, c + m)


def simular(pos, ret, costo):
    """pos[t] = posición (0/1) que se mantiene de la ejecución t a la t+1; ret[t] = rendimiento de ese tramo."""
    cambios = np.abs(np.diff(np.concatenate([[0], pos])))
    eq = np.cumprod((1 + pos * ret) * (1 - costo) ** cambios)
    return eq


def metricas(eq, pos, ret, costo):
    diario = np.diff(np.concatenate([[1.0], eq])) / np.concatenate([[1.0], eq[:-1]])
    sharpe = diario.mean() / diario.std(ddof=1) * math.sqrt(365) if diario.std() > 0 else float("nan")
    neg = diario[diario < 0]
    sortino = diario.mean() / neg.std(ddof=1) * math.sqrt(365) if len(neg) > 1 else float("nan")
    pico = np.maximum.accumulate(eq)
    # operaciones: tramos consecutivos con pos = 1
    ops, actual = [], None
    for p, r in zip(pos, ret):
        if p and actual is None:
            actual = 1.0
        if p:
            actual *= 1 + r
        elif actual is not None:
            ops.append(actual * (1 - costo) ** 2 - 1); actual = None
    if actual is not None:
        ops.append(actual * (1 - costo) ** 2 - 1)
    ops = np.array(ops)
    gan, per = ops[ops > 0], ops[ops <= 0]
    lo, hi = wilson(len(gan), len(ops))
    return {"rendimiento_neto": eq[-1] - 1, "max_drawdown": (eq / pico - 1).min(), "sharpe_anual": sharpe, "sortino_anual": sortino,
            "operaciones": len(ops), "win_rate": len(gan) / len(ops) if len(ops) else float("nan"), "wilson_95_inf": lo, "wilson_95_sup": hi,
            "expectativa_por_operacion": ops.mean() if len(ops) else float("nan"),
            "ganancia_media": gan.mean() if len(gan) else float("nan"), "perdida_media": per.mean() if len(per) else float("nan"),
            "profit_factor": gan.sum() / -per.sum() if per.sum() < 0 else float("nan"), "exposicion": pos.mean()}


# ------------------------------------------------------------------ datos de BTC (TE ya usado una vez; aquí solo se mide)
sim = pd.read_csv(os.path.join(RAIZ, "resultados", "simulacion.csv"), parse_dates=["fecha"])
crudo = pd.read_csv(os.path.join(RAIZ, "datos", "originales", "BTCUSDT_1d_mexc_crudo.csv"))
crudo["fecha"] = pd.to_datetime(crudo["open_time"], unit="ms").dt.normalize()
crudo = crudo.set_index("fecha")["close"]
sma20, sma50 = crudo.rolling(20).mean(), crudo.rolling(50).mean()

px = sim["precio_ejecucion"].to_numpy()
ret = np.append(px[1:] / px[:-1] - 1, 0.0)          # tramo de la ejecución t a la t+1 (el último no tiene tramo)
pos_d = (sim["posicion"] > 0).astype(int).to_numpy()
# señal de cada regla técnica con el cierre de la vela anterior a la ejecución (sin mirar el futuro)
previo = sim["fecha"] - pd.Timedelta(days=1)
pos_sma20 = (crudo.reindex(previo).to_numpy() > sma20.reindex(previo).to_numpy()).astype(int)
pos_cruce = (sma20.reindex(previo).to_numpy() > sma50.reindex(previo).to_numpy()).astype(int)
pos_bh = np.ones_like(pos_d)

filas = []
for nombre, pos in [("Estrategia D (modelo LSTM + filtro SMA20)", pos_d), ("Regla técnica: cierre > SMA20", pos_sma20),
                    ("Cruce de medias: SMA20 > SMA50", pos_cruce), ("Comprar y mantener", pos_bh)]:
    eq = simular(pos, ret, COSTO)
    filas.append({"estrategia": nombre, **metricas(eq, pos, ret, COSTO)})
base = pd.DataFrame(filas)
verif = simular(pos_d, ret, COSTO)[-1] - 1

# operar al azar con la misma exposición: permutaciones de la posición diaria de la estrategia D
rng = np.random.default_rng(SEMILLA)
perm = np.array([simular(rng.permutation(pos_d), ret, COSTO)[-1] - 1 for _ in range(N_PERM)])
p_valor = (perm >= base.loc[0, "rendimiento_neto"]).mean()
azar = {"estrategia": f"Azar con la misma exposición ({N_PERM:,} permutaciones)", "rendimiento_neto": np.median(perm),
        "percentil_5": np.percentile(perm, 5), "percentil_95": np.percentile(perm, 95),
        "p_valor_estrategia_D": p_valor}
base.to_csv(os.path.join(SAL, "metricas_y_lineas_base_TE_BTC.csv"), index=False)
pd.DataFrame([azar]).to_csv(os.path.join(SAL, "linea_base_azar_TE_BTC.csv"), index=False)

# ------------------------------------------------------------------ costos y deslizamiento
cost = []
for c in [0.0, 0.0005, 0.001, 0.002, 0.003]:
    for d in [0.0, 0.0005]:
        cost.append({"comision": c, "deslizamiento": d, "rendimiento_neto": simular(pos_d, ret, c + d)[-1] - 1,
                     "comprar_y_mantener": simular(pos_bh, ret, c + d)[-1] - 1})
cost = pd.DataFrame(cost)
lo_c, hi_c = 0.0, 0.01
for _ in range(60):
    m = (lo_c + hi_c) / 2
    lo_c, hi_c = (m, hi_c) if simular(pos_d, ret, m)[-1] - 1 > 0 else (lo_c, m)
equilibrio = lo_c
cost.to_csv(os.path.join(SAL, "sensibilidad_costos_TE_BTC.csv"), index=False)

# ------------------------------------------------------------------ régimen (cierre de la vela previa frente a su SMA50)
reg = np.where(crudo.reindex(previo).to_numpy() > sma50.reindex(previo).to_numpy(), "alcista", "bajista")
regimen = []
for r_ in ["alcista", "bajista"]:
    msk = reg == r_
    g = lambda pos: np.prod(1 + (pos * ret)[msk]) - 1
    regimen.append({"regimen": r_, "dias": int(msk.sum()), "estrategia_D_bruto": g(pos_d), "comprar_y_mantener_bruto": g(pos_bh),
                    "exposicion_D": pos_d[msk].mean()})
regimen = pd.DataFrame(regimen)
regimen.to_csv(os.path.join(SAL, "regimen_TE_BTC.csv"), index=False)

# ------------------------------------------------------------------ deriva en vivo (15 activos)
ciclos = pd.read_csv(os.path.join(RAIZ, "agente", "registros", "ciclos.csv"))
ciclos = ciclos[ciclos["modo"] == "vivo"].copy()
obs = ciclos["observacion"].apply(json.loads)
ciclos["cierre"] = obs.apply(lambda o: o["cierre"]); ciclos["pronostico"] = obs.apply(lambda o: o["pronostico"])
res = []
for f in ["activos_extra", "activos_extra_lote2", "activos_extra_lote3"]:
    res.append(pd.read_csv(os.path.join(RAIZ, f, "resultados", "resumen_activos.csv")))
rmse_te = pd.concat(res).assign(simbolo=lambda d: d["activo"].str.replace(" (referencia)", "", regex=False)).drop_duplicates("simbolo").set_index("simbolo")["RMSE_TE_lstm"]
deriva = []
for s, g in ciclos.sort_values("fecha_vela").groupby("simbolo"):
    g = g.drop_duplicates("fecha_vela")
    real = g["cierre"].shift(-1) / g["cierre"] - 1
    m = real.notna()
    if m.sum() < 3:
        continue
    err = (g.loc[m, "pronostico"] - real[m])
    rmse_v = float(np.sqrt((err ** 2).mean()))
    direccion = float((np.sign(g.loc[m, "pronostico"]) == np.sign(real[m])).mean())
    te = float(rmse_te.get(s, np.nan))
    deriva.append({"simbolo": s, "ciclos_evaluados": int(m.sum()), "rmse_vivo": rmse_v, "rmse_TE": te, "razon": rmse_v / te if te else np.nan,
                   "acierto_direccional_vivo": direccion,
                   "a_vigilar": bool((rmse_v / te > 1.5) or direccion < 0.45) if te else None})
deriva = pd.DataFrame(deriva)
deriva.to_csv(os.path.join(SAL, "deriva_en_vivo.csv"), index=False)

# ------------------------------------------------------------------ reporte en Markdown
p = lambda v, d=2: "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v * 100:+.{d}f} %"
q = lambda v, d=2: "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{d}f}"
L = ["# Análisis complementario (v2.3)", "",
     "Solo lectura de resultados que ya existían: no se reentrenó ni se cambió el modelo, las reglas o la simulación, y la prueba (TE) "
     "no se usó para elegir nada. Script: [`analisis/analisis_complementario.py`](analisis/analisis_complementario.py); tablas en "
     "[`resultados/analisis_complementario/`](resultados/analisis_complementario/).", "",
     f"Comprobación: la reconstrucción de la estrategia D de BTC en TE da {p(verif)} con 0.10 % de comisión (el notebook reportó −3.25 %).", "",
     "## 1. Métricas completas y líneas base (BTC, TE ago 2025 – nov 2026, comisión 0.10 %)", "",
     "| Estrategia | Neto | Drawdown | Sharpe | Sortino | Operaciones | Acierto (IC 95 % Wilson) | Expectativa por operación | Profit factor | Exposición |",
     "|---|---|---|---|---|---|---|---|---|---|"]
for _, r in base.iterrows():
    L.append(f"| {r['estrategia']} | {p(r['rendimiento_neto'])} | {p(r['max_drawdown'],1)} | {q(r['sharpe_anual'])} | {q(r['sortino_anual'])} | "
             f"{r['operaciones']} | {p(r['win_rate'],0).lstrip('+')} ({p(r['wilson_95_inf'],0).lstrip('+')} – {p(r['wilson_95_sup'],0).lstrip('+')}) | "
             f"{p(r['expectativa_por_operacion'])} | {q(r['profit_factor'])} | {p(r['exposicion'],0).lstrip('+')} |")
iguales = bool((pos_d == pos_sma20).all())
L += ["", "Comprar y mantener se mide aquí con la misma convención que las demás (ejecución a la apertura y comisión de entrada), por eso da "
      f"{p(base.loc[3,'rendimiento_neto'])} y no el −31.57 % de cierre a cierre del notebook.", ""]
if iguales:
    L += ["**Hallazgo:** en el TE de BTC la estrategia D coincidió día por día con la regla técnica pura (cierre > SMA20). El pronóstico del ensamble "
          "superó su umbral δ en todos los días en que el cierre estaba sobre la SMA20, así que el filtro de tendencia fue el que decidió. "
          "El aporte medible del modelo en BTC está en el pronóstico (RMSE menor que la regresión lineal en TE) y no en el filtro; en los otros "
          "14 activos la estrategia de cada uno se eligió en validación y no se comparó así. Se reporta tal cual: no se cambia nada después de ver el TE.", ""]
L += ["", f"**Operar al azar con la misma exposición** ({N_PERM:,} permutaciones de la posición diaria de la estrategia D, semilla {SEMILLA}): "
      f"mediana {p(azar['rendimiento_neto'])}, percentiles 5–95 de {p(azar['percentil_5'])} a {p(azar['percentil_95'])}. "
      f"La estrategia D ({p(base.loc[0,'rendimiento_neto'])}) queda por encima del {100 - azar['p_valor_estrategia_D'] * 100:.1f} % de esas carteras al azar "
      f"(p = {azar['p_valor_estrategia_D']:.3f}).", "",
      "## 2. Sensibilidad a costos y deslizamiento (estrategia D, BTC TE)", "",
      "| Comisión | Deslizamiento | Estrategia D | Comprar y mantener |", "|---|---|---|---|"]
for _, r in cost.iterrows():
    L.append(f"| {r['comision']*100:.2f} % | {r['deslizamiento']*100:.2f} % | {p(r['rendimiento_neto'])} | {p(r['comprar_y_mantener'])} |")
L += ["", f"**Costo de equilibrio:** con un costo total por operación menor a {equilibrio*100:.3f} % la estrategia D termina positiva en el TE.", "",
      "## 3. Resultado por régimen de mercado (BTC TE; régimen según el cierre previo frente a su SMA50)", "",
      "| Régimen | Días | Estrategia D (bruto) | Comprar y mantener (bruto) | Exposición de D |", "|---|---|---|---|---|"]
for _, r in regimen.iterrows():
    L.append(f"| {r['regimen']} | {r['dias']} | {p(r['estrategia_D_bruto'])} | {p(r['comprar_y_mantener_bruto'])} | {p(r['exposicion_D'],0).lstrip('+')} |")
L += ["", "## 4. Deriva en vivo y regla de reentrenamiento", "",
      "Error del pronóstico en los ciclos en vivo (rendimiento del día siguiente) frente al RMSE del TE de cada activo.", "",
      "| Activo | Ciclos evaluados | RMSE en vivo | RMSE en TE | Razón | Acierto direccional en vivo | Estado |", "|---|---|---|---|---|---|---|"]
for _, r in deriva.iterrows():
    L.append(f"| {r['simbolo']} | {r['ciclos_evaluados']} | {q(r['rmse_vivo'],4)} | {q(r['rmse_TE'],4)} | {q(r['razon'])} | "
             f"{p(r['acierto_direccional_vivo'],0).lstrip('+')} | {'a vigilar' if r['a_vigilar'] else 'no'} |")
L += ["", "**Regla de reentrenamiento** (fijada el 27 nov, antes de ver más ciclos): se revisa cada 20 ciclos en vivo por activo. Si el RMSE en vivo "
      "supera 1.5 veces el RMSE del TE, o el acierto direccional queda debajo de 45 %, el modelo de ese activo se marca para reentrenar con una "
      "nueva partición cronológica (TR/VA/TE nuevos) y un TE que no se haya visto. Con 7 a 12 ciclos evaluados por activo la muestra todavía es corta: "
      "esta tabla es el primer punto del monitoreo, no una conclusión.", ""]
open(os.path.join(RAIZ, "Analisis_Complementario.md"), "w", encoding="utf-8").write("\n".join(L))
print("\n".join(L))
