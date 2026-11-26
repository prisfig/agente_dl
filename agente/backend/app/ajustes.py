"""Carga de configuración (archivo JSON versionado) y secretos (.env, solo servidor)."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

AGENTE_DIR = Path(__file__).resolve().parents[2]   # agente_dl/agente
RAIZ = AGENTE_DIR.parent                           # agente_dl
LONGITUD_MINIMA_CLAVE = 24


class ErrorConfiguracion(Exception):
    pass


def cargar_env(ruta: Path | None = None) -> None:
    """Lee .env sin dependencias externas. No sobrescribe variables ya definidas."""
    ruta = ruta or AGENTE_DIR / ".env"
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def leer_secreto(nombre: str) -> str:
    valor = os.environ.get(nombre, "")
    if len(valor) < LONGITUD_MINIMA_CLAVE:
        raise ErrorConfiguracion(
            f"Falta {nombre} en .env o es demasiado corta (mínimo {LONGITUD_MINIMA_CLAVE} caracteres)."
        )
    return valor


@dataclass(frozen=True)
class Secretos:
    backend_api_key: str
    gateway_api_key: str

    def __repr__(self) -> str:   # nunca imprimir claves en logs
        return "Secretos(****)"


def cargar_secretos() -> Secretos:
    cargar_env()
    return Secretos(leer_secreto("BACKEND_API_KEY"), leer_secreto("GATEWAY_API_KEY"))


def cargar_config(ruta: Path | None = None) -> dict:
    """Por defecto config/agente.json. Con AGENTE_CONFIG=config/demo/demo.json se arranca una instancia
    de demostración con su propia base de datos (los ciclos en vivo no se tocan)."""
    if ruta is None:
        elegido = os.environ.get("AGENTE_CONFIG")
        ruta = (AGENTE_DIR / elegido) if elegido else AGENTE_DIR / "config" / "agente.json"
    contenido = ruta.read_bytes()
    cfg = json.loads(contenido)
    validar_config(cfg)
    cfg["_sha256"] = hashlib.sha256(contenido).hexdigest()
    cfg["_ruta"] = str(ruta)
    return cfg


def activos_de(cfg: dict) -> list[dict]:
    """Una configuración por activo, con la misma forma que la de un solo activo (v1.0–v1.2):
    `mercado.simbolo`, `mercado.activo_base`, `modelo` y `base_datos` propios; riesgo, Paper, LLM y ciclo comunes.
    El primer activo de la lista es el principal (BTCUSDT). Una configuración sin `activos` (p. ej. las de demostración)
    se usa tal cual, como un solo activo."""
    if "activos" not in cfg:
        return [cfg]
    salida = []
    for a in cfg["activos"]:
        c = copy.deepcopy({k: v for k, v in cfg.items() if k != "activos"})
        c["mercado"].update({"simbolo": a["simbolo"], "activo_base": a["activo_base"],
                             "decimales_precio": int(a.get("decimales_precio", 2))})
        if "reglas_par_respaldo" in a:
            c["mercado"]["reglas_par_respaldo"] = a["reglas_par_respaldo"]
        c["modelo"] = a["modelo"]
        c["base_datos"] = a["base_datos"]
        salida.append(c)
    return salida


def validar_config(cfg: dict) -> None:
    r = cfg["riesgo"]
    p = cfg["paper"]
    errores = []
    if "activos" in cfg:
        simbolos = [a.get("simbolo") for a in cfg["activos"]]
        bases = [a.get("base_datos") for a in cfg["activos"]]
        if not simbolos:
            errores.append("la lista de activos está vacía")
        if len(set(simbolos)) != len(simbolos):
            errores.append("hay símbolos repetidos en activos")
        if len(set(bases)) != len(bases):
            errores.append("cada activo necesita su propia base de datos")
        for a in cfg["activos"]:
            faltan = [k for k in ("simbolo", "activo_base", "base_datos", "modelo") if k not in a]
            faltan += [f"modelo.{k}" for k in ("config_congelada", "escalador_x", "escalador_y") if k not in a.get("modelo", {})]
            if faltan:
                errores.append(f"{a.get('simbolo', '?')}: faltan {', '.join(faltan)}")
    if not 0 < r["exposicion_maxima"] <= 1:
        errores.append("exposicion_maxima debe estar en (0, 1]: sin apalancamiento")
    if not 0 < r["perdida_diaria_maxima"] < 1:
        errores.append("perdida_diaria_maxima debe estar en (0, 1)")
    if r["stop_movil_k_vol"] <= 0:
        errores.append("stop_movil_k_vol debe ser positivo")
    if r["antiguedad_maxima_horas"] <= 0:
        errores.append("antiguedad_maxima_horas debe ser positiva")
    if p["capital_inicial"] <= 0:
        errores.append("capital_inicial debe ser positivo")
    for k in ("costo_compra", "costo_venta", "deslizamiento"):
        if not 0 <= p[k] < 0.05:
            errores.append(f"{k} fuera de rango")
    if errores:
        raise ErrorConfiguracion("; ".join(errores))
