"""Verifica que los ensambles LSTM congelados de los activos extra
reproducen en esta computadora los pronósticos generados en Colab:
  1) huellas SHA-256 de checkpoints y escaladores contra la configuración congelada;
  2) las predicciones de TE guardadas (predicciones_TE.csv) y sus señales;
  3) el pronóstico futuro (prediccion_futura.csv) con la descarga reciente de MEXC.

No entrena ni evalúa nada nuevo en TE: solo recarga los modelos y compara.

Uso (desde la carpeta agente_dl, con el entorno .venv activo):
    python agente/verificar_activos_extra.py                        # lote 1: ETH, SOL y XRP (activos_extra/)
    python agente/verificar_activos_extra.py activos_extra_lote2    # lote 2 (activos_extra_lote2/)
"""
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import keras
import sklearn
import tensorflow as tf

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = sys.argv[1].strip("/") if len(sys.argv) > 1 else "activos_extra"
PAQUETE = json.loads((RAIZ / CARPETA / "paquete_agente.json").read_text())
TOLERANCIA = 1e-6


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def pronosticar(rezagos: pd.DataFrame, modelos, esc_x, esc_y, variables) -> np.ndarray:
    """rezagos: columnas ret_lag_0 (r_t) … ret_lag_19. Secuencia antiguo → reciente."""
    if hasattr(esc_x, "feature_names_in_"):
        x = esc_x.transform(rezagos[list(esc_x.feature_names_in_)])
    else:
        x = esc_x.transform(rezagos[variables].to_numpy())
    x = np.asarray(x)[:, ::-1]
    x = np.ascontiguousarray(x, dtype="float32").reshape(len(x), 20, 1)
    preds = [m.predict(x, verbose=0).reshape(-1, 1) for m in modelos]
    pred_esc = np.mean(np.hstack(preds), axis=1).reshape(-1, 1)
    return esc_y.inverse_transform(pred_esc).ravel()


def senal(estimado: np.ndarray, delta: float, sobre_sma20, estrategia: str) -> np.ndarray:
    comprar = estimado > delta
    if estrategia == "D":
        comprar = comprar & np.asarray(sobre_sma20, dtype=bool)
    return np.where(comprar, "comprar", "efectivo")


def verificar(simbolo: str, info: dict) -> dict:
    ruta_cfg = RAIZ / info["config_congelada"]
    cfg = json.loads(ruta_cfg.read_text())
    base = ruta_cfg.parent.parent                      # activos_extra/<SIMBOLO>
    variables = cfg["variables"]

    # 1) Huellas
    huellas = {}
    for ruta, esperado in {**cfg["sha256_checkpoints"], **cfg["sha256_escaladores"]}.items():
        huellas[ruta] = (sha256(RAIZ / ruta) == esperado)
    ok_huellas = all(huellas.values()) and cfg["sha256"] == info["sha256_config"]

    modelos = [keras.models.load_model(RAIZ / p) for p in cfg["checkpoints"]]
    esc_x = joblib.load(RAIZ / cfg["escalador_x"])
    esc_y = joblib.load(RAIZ / cfg["escalador_y"])
    parametros = int(modelos[0].count_params())

    # 2) TE
    ventanas = pd.read_csv(base / f"datos/procesados/{simbolo}_1d_ejemplos_ventanas.csv")
    te = ventanas[ventanas["conjunto"] == "TE"].reset_index(drop=True)
    ref = pd.read_csv(base / "resultados/predicciones_TE.csv")
    te = te.merge(ref[["fecha_emision", "rendimiento_estimado", "senal", "cierre_sobre_SMA20"]],
                  on="fecha_emision", how="inner")
    t0 = time.perf_counter()
    est = pronosticar(te, modelos, esc_x, esc_y, variables)
    seg_te = time.perf_counter() - t0
    dif = np.abs(est - te["rendimiento_estimado"].to_numpy())
    sen = senal(est, cfg["delta"], te["cierre_sobre_SMA20"], cfg["estrategia"])
    senales_iguales = int((sen == te["senal"].to_numpy()).sum())
    ok_te = (len(te) == cfg["particiones"]["TE"]["n"] and dif.max() < TOLERANCIA
             and senales_iguales == len(te))

    # 3) Pronóstico futuro
    fut = pd.read_csv(base / "resultados/prediccion_futura.csv").iloc[0]
    recientes = sorted((base / "datos/originales").glob(f"{simbolo}_1d_mexc_recientes_*.csv"))[-1]
    rec = pd.read_csv(recientes)
    rec["fecha"] = pd.to_datetime(rec["open_time"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    rec = rec[rec["fecha"] <= fut["fecha_corte"]].reset_index(drop=True)
    r = rec["close"].pct_change().to_numpy()
    fila = pd.DataFrame([r[-20:][::-1]], columns=variables)  # ret_lag_0 = r_t
    t0 = time.perf_counter()
    est_fut = float(pronosticar(fila, modelos, esc_x, esc_y, variables)[0])
    lat_fut = time.perf_counter() - t0
    sen_fut = senal(np.array([est_fut]), cfg["delta"], [bool(fut["cierre_sobre_SMA20"])], cfg["estrategia"])[0]
    dif_fut = abs(est_fut - float(fut["rendimiento_estimado"]))
    ok_fut = dif_fut < TOLERANCIA and sen_fut == fut["senal"] and \
        abs(float(rec["close"].iloc[-1]) - float(fut["cierre_en_corte"])) < 1e-9

    return {
        "neuronas": cfg["neuronas"], "parametros": parametros, "estrategia": cfg["estrategia"],
        "delta": cfg["delta"], "config_sha256": cfg["sha256"],
        "huellas": {"todas_coinciden": bool(ok_huellas), "detalle": huellas},
        "TE": {"n": int(len(te)), "n_esperado": cfg["particiones"]["TE"]["n"],
               "primer_objetivo": te["fecha_objetivo"].iloc[0], "ultimo_objetivo": te["fecha_objetivo"].iloc[-1],
               "max_dif_abs": float(dif.max()), "media_dif_abs": float(dif.mean()),
               "senales_iguales": senales_iguales, "segundos": round(seg_te, 3), "coincide": bool(ok_te)},
        "futuro": {"fecha_corte": fut["fecha_corte"], "archivo": recientes.name,
                   "cierre_en_corte": float(rec["close"].iloc[-1]),
                   "colab": float(fut["rendimiento_estimado"]), "local": est_fut, "dif_abs": dif_fut,
                   "senal_colab": fut["senal"], "senal_local": sen_fut,
                   "latencia_s": round(lat_fut, 3), "coincide": bool(ok_fut)},
        "coincide_todo": bool(ok_huellas and ok_te and ok_fut),
    }


def main():
    activos = {s: verificar(s, info) for s, info in PAQUETE["activos"].items()}
    reporte = {
        "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "equipo": {"plataforma": platform.platform(), "procesador": platform.machine(),
                   "python": platform.python_version()},
        "versiones": {"tensorflow": tf.__version__, "keras": keras.__version__,
                      "scikit-learn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__},
        "carpeta": CARPETA,
        "tolerancia": TOLERANCIA,
        "orden_secuencia": "antiguo_a_reciente",
        "activos": activos,
        "coincide_todo": all(a["coincide_todo"] for a in activos.values()),
    }
    nombre = "verificacion_activos_extra_local.json" if CARPETA == "activos_extra" else f"verificacion_{CARPETA}_local.json"
    salida = RAIZ / "agente/evidencia" / nombre
    salida.write_text(json.dumps(reporte, indent=2, ensure_ascii=False))

    for s, a in activos.items():
        print(f"{s:16s}: huellas {'OK' if a['huellas']['todas_coinciden'] else 'NO'} | "
              f"TE {a['TE']['n']} ej., dif. máx. {a['TE']['max_dif_abs']:.2e}, "
              f"señales {a['TE']['senales_iguales']}/{a['TE']['n']} -> {'OK' if a['TE']['coincide'] else 'NO COINCIDE'} | "
              f"futuro {a['futuro']['fecha_corte']}: {a['futuro']['local']:+.6%} ({a['futuro']['senal_local']}) "
              f"-> {'OK' if a['futuro']['coincide'] else 'NO COINCIDE'}")
    print(f"Resultado global: {'TODO COINCIDE' if reporte['coincide_todo'] else 'HAY DIFERENCIAS'}")
    print(f"Reporte guardado en {salida.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
