"""Verifica que el ensamble LSTM congelado reproduce en esta computadora
los pronósticos generados en Colab (TE y pronóstico futuro del 2026-11-11).

Uso (desde la carpeta agente_dl, con el entorno .venv activo):
    python agente/verificar_modelo.py
"""
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import keras
import tensorflow as tf

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = json.loads((RAIZ / "resultados/configuracion_final_congelada.json").read_text())
VARIABLES = CONFIG["variables"]                     # ret_lag_0 (más reciente) … ret_lag_19
TOLERANCIA = 1e-6


def cargar():
    modelos = [keras.models.load_model(RAIZ / p) for p in CONFIG["checkpoints"]]
    esc_x = joblib.load(RAIZ / "modelos/cap11/escalador_A_cap11.joblib")
    esc_y = joblib.load(RAIZ / "modelos/cap11/escalador_y_cap11.joblib")
    return modelos, esc_x, esc_y


def pronosticar(rezagos: pd.DataFrame, modelos, esc_x, esc_y, invertir: bool) -> np.ndarray:
    """rezagos: columnas ret_lag_0 … ret_lag_19. Devuelve el rendimiento estimado (escala original)."""
    columnas = list(getattr(esc_x, "feature_names_in_", VARIABLES))
    x = esc_x.transform(rezagos[columnas]) if hasattr(esc_x, "feature_names_in_") else esc_x.transform(rezagos[VARIABLES].to_numpy())
    if invertir:                                   # secuencia antiguo → reciente
        x = x[:, ::-1]
    x = np.ascontiguousarray(x, dtype="float32").reshape(len(x), 20, 1)
    preds = [m.predict(x, verbose=0).reshape(-1, 1) for m in modelos]
    pred_esc = np.mean(np.hstack(preds), axis=1).reshape(-1, 1)
    return esc_y.inverse_transform(pred_esc).ravel()


def main():
    modelos, esc_x, esc_y = cargar()

    # 1) Predicciones de TE guardadas en Colab
    ventanas = pd.read_csv(RAIZ / "datos/procesados/BTCUSDT_1d_ejemplos_ventanas.csv")
    te = ventanas[ventanas["conjunto"] == "TE"].reset_index(drop=True)
    ref = pd.read_csv(RAIZ / "resultados/predicciones_TE.csv")
    te = te.merge(ref[["fecha_emision", "rendimiento_estimado"]], on="fecha_emision", how="inner")

    resultados = {}
    for invertir in (True, False):
        t0 = time.perf_counter()
        est = pronosticar(te, modelos, esc_x, esc_y, invertir)
        dif = np.abs(est - te["rendimiento_estimado"].to_numpy())
        resultados["antiguo_a_reciente" if invertir else "reciente_a_antiguo"] = {
            "max_dif_abs": float(dif.max()),
            "media_dif_abs": float(dif.mean()),
            "segundos": round(time.perf_counter() - t0, 3),
            "_est": est,
        }
    orden = min(resultados, key=lambda k: resultados[k]["max_dif_abs"])
    ok_te = resultados[orden]["max_dif_abs"] < TOLERANCIA

    # 2) Pronóstico futuro (corte 2026-11-11) con la descarga reciente de MEXC
    fut = pd.read_csv(RAIZ / "resultados/prediccion_futura.csv").iloc[0]
    rec = pd.read_csv(RAIZ / "datos/originales/BTCUSDT_1d_mexc_recientes_20261112T142547Z.csv")
    rec["fecha"] = pd.to_datetime(rec["open_time"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    rec = rec[rec["fecha"] <= fut["fecha_corte"]].reset_index(drop=True)
    r = rec["close"].pct_change().to_numpy()
    ultimos = r[-20:][::-1]                       # ret_lag_0 = r_t
    fila = pd.DataFrame([ultimos], columns=VARIABLES)
    t0 = time.perf_counter()
    est_fut = float(pronosticar(fila, modelos, esc_x, esc_y, orden == "antiguo_a_reciente")[0])
    lat_fut = time.perf_counter() - t0
    dif_fut = abs(est_fut - float(fut["rendimiento_estimado"]))
    ok_fut = dif_fut < TOLERANCIA

    reporte = {
        "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "equipo": {"plataforma": platform.platform(), "procesador": platform.machine(),
                   "python": platform.python_version()},
        "versiones": {"tensorflow": tf.__version__, "keras": keras.__version__,
                      "numpy": np.__version__, "pandas": pd.__version__},
        "config_sha256": CONFIG["sha256"],
        "orden_secuencia": orden,
        "TE": {"n": int(len(te)), **{k: {kk: vv for kk, vv in v.items() if kk != "_est"} for k, v in resultados.items()},
               "coincide": bool(ok_te)},
        "futuro": {"fecha_corte": fut["fecha_corte"], "cierre_en_corte": float(rec["close"].iloc[-1]),
                   "colab": float(fut["rendimiento_estimado"]), "local": est_fut,
                   "dif_abs": dif_fut, "latencia_s": round(lat_fut, 3), "coincide": bool(ok_fut)},
        "tolerancia": TOLERANCIA,
    }
    salida = RAIZ / "agente/evidencia/verificacion_modelo_local.json"
    salida.write_text(json.dumps(reporte, indent=2, ensure_ascii=False))

    print(f"Orden de secuencia: {orden}")
    print(f"TE ({len(te)} ejemplos): dif. máx. = {resultados[orden]['max_dif_abs']:.2e} -> {'OK' if ok_te else 'NO COINCIDE'}")
    print(f"Futuro {fut['fecha_corte']}: Colab {float(fut['rendimiento_estimado']):.8f} | local {est_fut:.8f} -> {'OK' if ok_fut else 'NO COINCIDE'}")
    print(f"Reporte guardado en {salida.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
