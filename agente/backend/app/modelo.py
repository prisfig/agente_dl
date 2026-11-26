"""Variables y pronóstico con el ensamble LSTM congelado de cada activo (mismo contrato de variables).

Estrategias de la práctica (elegidas con VA, una por activo, en su configuración congelada):
  C  comprar si pronóstico > δ                       (sin filtro)
  D  comprar si pronóstico > δ y cierre > SMA20      (con filtro de tendencia)"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from .ajustes import RAIZ
from .mexc import Vela

N_REZAGOS = 20
VENTANA_SMA = 20


class ErrorDatos(Exception):
    pass


@dataclass
class Observacion:
    fecha_vela: str
    cierre: float
    rezagos: list[float]           # ret_lag_0 (r_t) … ret_lag_19
    sma20: float
    cierre_sobre_sma20: bool
    dist_sma20: float
    vol20: float
    pronostico: float = float("nan")
    delta: float = float("nan")
    estrategia: str = ""           # "C" | "D"
    senal: str = ""                # "comprar" | "efectivo"

    def a_dict(self) -> dict:
        d = asdict(self)
        d["rezagos"] = [float(x) for x in self.rezagos]
        if self.estrategia == "D":   # nombre anterior a la v1.3 (los ciclos guardados de BTC lo usan)
            d["senal_d"] = self.senal
        return d


def calcular_variables(velas: Sequence[Vela]) -> Observacion:
    """Misma definición que en entrenamiento: r_t = P_t/P_{t-1} − 1, SMA de 20 cierres incluyendo t,
    volatilidad = desviación estándar muestral de r_t … r_{t-19}. Solo usa información hasta el cierre de t."""
    if len(velas) < N_REZAGOS + 1:
        raise ErrorDatos(f"Se necesitan al menos {N_REZAGOS + 1} velas cerradas; hay {len(velas)}.")
    ultimas = list(velas)[-(N_REZAGOS + 1):]
    fechas = [date.fromisoformat(v.fecha) for v in ultimas]
    for a, b in zip(fechas, fechas[1:]):
        if b - a != timedelta(days=1):
            raise ErrorDatos(f"Hay un hueco en las velas entre {a} y {b}: no se rellenan datos faltantes.")
    cierres = np.array([v.close for v in ultimas], dtype=float)
    r = cierres[1:] / cierres[:-1] - 1                    # r_{t-19} … r_t
    sma20 = float(cierres[-VENTANA_SMA:].mean())
    cierre = float(cierres[-1])
    return Observacion(
        fecha_vela=ultimas[-1].fecha,
        cierre=cierre,
        rezagos=[float(x) for x in r[::-1]],
        sma20=sma20,
        cierre_sobre_sma20=bool(cierre > sma20),
        dist_sma20=cierre / sma20 - 1,
        vol20=float(np.std(r, ddof=1)),
    )


ESTRATEGIAS = {
    "C": "pronóstico > δ (sin filtro)",
    "D": "pronóstico > δ y cierre > SMA20",
}


def senal_estrategia(estrategia: str, pronostico: float, delta: float, cierre_sobre_sma20: bool) -> str:
    if estrategia not in ESTRATEGIAS:
        raise ErrorDatos(f"Estrategia desconocida: '{estrategia}' (solo C o D).")
    comprar = pronostico > delta and (cierre_sobre_sma20 or estrategia == "C")
    return "comprar" if comprar else "efectivo"


def senal_estrategia_d(pronostico: float, delta: float, cierre_sobre_sma20: bool) -> str:
    return senal_estrategia("D", pronostico, delta, cierre_sobre_sma20)


class ErrorModelo(Exception):
    """Un checkpoint o escalador no coincide con la huella SHA-256 de la configuración congelada."""


class ModeloPronostico:
    """Carga el ensamble y los escaladores. `funcion` permite inyectar un pronóstico falso en pruebas."""

    def __init__(self, cfg_modelo: dict, raiz: Path = RAIZ, funcion: Callable[[list[float]], float] | None = None):
        self.raiz = raiz
        ruta_cfg = raiz / cfg_modelo["config_congelada"]
        self.config_congelada = json.loads(ruta_cfg.read_text()) if ruta_cfg.exists() else {}
        self.delta = float(self.config_congelada.get("delta", 0.000866))
        self.estrategia = self.config_congelada.get("estrategia", "D")
        if self.estrategia not in ESTRATEGIAS:
            raise ErrorModelo(f"Estrategia '{self.estrategia}' no soportada en {ruta_cfg.name}.")
        te = (self.config_congelada.get("particiones") or {}).get("TE") or {}
        self.version = {
            "modelo": self.config_congelada.get("modelo_pronostico", "lstm_A"),
            "activo": self.config_congelada.get("activo"),
            "neuronas": self.config_congelada.get("neuronas", 20),
            "semillas": self.config_congelada.get("semillas"),
            "estrategia": self.estrategia,
            "regla_estrategia": ESTRATEGIAS[self.estrategia],
            "delta": self.delta,
            "ultimo_objetivo_TE": te.get("ultimo_objetivo"),
            "sha256_config_congelada": self.config_congelada.get("sha256"),
            "checkpoints": {},
        }
        if funcion is not None:
            self._funcion = funcion
            self.version["modelo"] += " (simulado para pruebas)"
            return
        import joblib
        import keras
        # Huellas: si la configuración congelada las trae (activos extra), cada archivo debe coincidir antes de cargarse.
        esperadas = {**self.config_congelada.get("sha256_checkpoints", {}), **self.config_congelada.get("sha256_escaladores", {})}
        for rel in [*self.config_congelada["checkpoints"], cfg_modelo["escalador_x"], cfg_modelo["escalador_y"]]:
            huella = hashlib.sha256((raiz / rel).read_bytes()).hexdigest()
            if rel in esperadas and huella != esperadas[rel]:
                raise ErrorModelo(f"{rel} no coincide con la huella SHA-256 de la configuración congelada: no se carga.")
            if rel in self.config_congelada["checkpoints"]:
                self.version["checkpoints"][rel] = huella[:16]
        self.version["huellas_verificadas"] = bool(esperadas)
        self._modelos = [keras.models.load_model(raiz / rel) for rel in self.config_congelada["checkpoints"]]
        self._esc_x = joblib.load(raiz / cfg_modelo["escalador_x"])
        self._esc_y = joblib.load(raiz / cfg_modelo["escalador_y"])
        self.version["parametros"] = int(self._modelos[0].count_params())
        self._variables = list(getattr(self._esc_x, "feature_names_in_", self.config_congelada["variables"]))
        self.version["keras"] = keras.__version__
        self._funcion = self._pronosticar_ensamble

    def _entrada(self, rezagos: list[float]) -> np.ndarray:
        import pandas as pd
        fila = pd.DataFrame([rezagos], columns=self.config_congelada["variables"])[self._variables]
        x = self._esc_x.transform(fila) if hasattr(self._esc_x, "feature_names_in_") else self._esc_x.transform(fila.to_numpy())
        return np.ascontiguousarray(x[:, ::-1], dtype="float32").reshape(1, N_REZAGOS, 1)   # antiguo → reciente

    def _pronosticar_ensamble(self, rezagos: list[float]) -> float:
        x = self._entrada(rezagos)
        preds = [float(m.predict(x, verbose=0).ravel()[0]) for m in self._modelos]
        return float(self._esc_y.inverse_transform([[float(np.mean(preds))]])[0][0])

    def activaciones(self, rezagos: list[float]) -> dict | None:
        """Valores internos de cada red para una entrada: secuencia escalada, estado final de la LSTM,
        capa densa ReLU y salida. Sirve para la vista 'red neuronal en vivo'."""
        if not hasattr(self, "_modelos"):
            return None
        x = self._entrada(rezagos)
        redes = []
        for semilla, m in zip(self.config_congelada["semillas"], self._modelos):
            capas, h = [], x
            for capa in m.layers:
                if capa.__class__.__name__ == "InputLayer":   # el modelo guardado incluye la capa de entrada
                    continue
                h = capa(h)
                capas.append({"nombre": capa.name, "tipo": capa.__class__.__name__,
                              "valores": [round(float(v), 5) for v in np.array(h).ravel()]})
            salida_esc = capas[-1]["valores"][0]
            redes.append({"semilla": semilla, "capas": capas, "salida_escalada": salida_esc,
                          "salida": float(self._esc_y.inverse_transform([[salida_esc]])[0][0])})
        media_esc = float(np.mean([r["salida_escalada"] for r in redes]))
        return {"entrada_escalada": [round(float(v), 5) for v in x.ravel()],
                "entrada_original": [float(v) for v in rezagos[::-1]],   # antiguo → reciente
                "redes": redes,
                "ensamble": float(self._esc_y.inverse_transform([[media_esc]])[0][0])}

    def completar(self, obs: Observacion) -> Observacion:
        obs.pronostico = float(self._funcion(obs.rezagos))
        obs.delta = self.delta
        obs.estrategia = self.estrategia
        obs.senal = senal_estrategia(self.estrategia, obs.pronostico, self.delta, obs.cierre_sobre_sma20)
        return obs
