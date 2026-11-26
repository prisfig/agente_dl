"""Utilidades de prueba: mercado, modelo y LLM simulados (sin red, sin TensorFlow, sin Ollama)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import httpx
import numpy as np
import pytest

from app.agente import Agente
from app.ajustes import Secretos, activos_de, cargar_config
from app.db import Base
from app.llm import ClienteLLM
from app.mexc import DIA_MS, ClienteMEXC, ErrorMercado, Vela
from app.modelo import ModeloPronostico

CLAVE_BACKEND = "clave-backend-de-prueba-123456789"
CLAVE_GATEWAY = "clave-gateway-de-prueba-123456789"


def ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def generar_velas(n: int = 80, fin: date = date(2026, 11, 14), semilla: int = 0, tendencia: float = 0.001) -> list[Vela]:
    rng = np.random.default_rng(semilla)
    precio = 70_000.0
    velas = []
    for i in range(n):
        d = fin - timedelta(days=n - 1 - i)
        abre = precio
        precio = precio * (1 + tendencia + rng.normal(0, 0.02))
        velas.append(Vela(d.isoformat(), ms(d), ms(d) + DIA_MS, abre, max(abre, precio) * 1.01,
                          min(abre, precio) * 0.99, precio, 1000.0))
    return velas


class MercadoFalso:
    """Imita ClienteMEXC. `fallo` puede ser un ErrorMercado que se lanza en la siguiente consulta."""

    def __init__(self, velas: list[Vela]):
        self.velas = velas
        self.fallo: ErrorMercado | None = None

    def velas_cerradas(self, limite=60, ahora=None):
        if self.fallo:
            raise self.fallo
        return self.velas[-limite:]

    def velas_rango(self, inicio_ms, fin_ms):
        return [v for v in self.velas if inicio_ms <= v.open_time and v.close_time <= fin_ms]

    def reglas_par(self, respaldo):
        return {"paso_cantidad": "0.000001", "monto_minimo": "1", "fuente": "prueba"}

    def latencia_ms(self):
        if self.fallo:
            raise self.fallo
        return 12.3

    def para_simbolo(self, simbolo):
        return self

    def precios_actuales(self, simbolos):
        raise ErrorMercado("sin_respuesta", "El mercado de prueba no da precios en vivo.")


class GatewayFalso:
    """Transporte httpx que imita al gateway + Ollama. `modo` controla la respuesta."""

    def __init__(self):
        self.modo = "ok"
        self.accion = "COMPRAR"
        self.llamadas: list[dict] = []
        self.pedir_herramienta = "consultar_indicadores"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/salud":
            if request.headers.get("X-API-Key") != CLAVE_GATEWAY:
                return httpx.Response(401, json={"detail": "Clave del gateway incorrecta."})
            if self.modo in ("caido", "ollama_detenido"):
                return httpx.Response(502, json={"detail": "Ollama no está disponible"})
            return httpx.Response(200, json={"ollama": "disponible", "version": "0.40.16", "modelos_permitidos": ["llama3.2:3b"]})
        cuerpo = json.loads(request.content)
        self.llamadas.append(cuerpo)
        if request.headers.get("X-API-Key") != CLAVE_GATEWAY:
            return httpx.Response(401, json={"detail": "Clave del gateway incorrecta."})
        if self.modo == "caido":
            raise httpx.ConnectError("conexión rechazada")
        if self.modo == "ollama_detenido":
            return httpx.Response(502, json={"detail": "Ollama no está disponible (¿está detenido?)."})
        if "tools" in cuerpo:   # fase 1
            if self.pedir_herramienta:
                return httpx.Response(200, json={"message": {"role": "assistant", "content": "",
                                       "tool_calls": [{"function": {"name": self.pedir_herramienta, "arguments": {}}}]}})
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})
        usuario = [m for m in cuerpo["messages"] if m["role"] == "user"][0]["content"]
        datos = json.loads(usuario.split("\n", 1)[1])
        if self.modo == "json_invalido":
            contenido = "COMPRAR porque sí"
        elif self.modo == "clave_extra":
            contenido = json.dumps({"accion": self.accion, "simbolo": datos["simbolo"], "fecha_vela": datos["fecha_vela"],
                                    "justificacion": "pronóstico 0.2%", "pronostico": "+0.2%"})
        elif self.modo == "simbolo_malo":
            contenido = json.dumps({"accion": self.accion, "simbolo": "ETHUSDT", "fecha_vela": datos["fecha_vela"],
                                    "justificacion": "pronóstico 0.2%"})
        else:
            contenido = json.dumps({"accion": self.accion, "simbolo": datos["simbolo"], "fecha_vela": datos["fecha_vela"],
                                    "justificacion": f"Pronóstico {datos['pronostico_rendimiento_siguiente_dia']} frente a delta."})
        return httpx.Response(200, json={"message": {"role": "assistant", "content": contenido}})


@pytest.fixture
def cfg_completa():
    return cargar_config()


@pytest.fixture
def cfg(cfg_completa):
    """Configuración del activo principal (BTCUSDT), con la misma forma que en la v1.2."""
    return activos_de(cfg_completa)[0]


@pytest.fixture
def secretos():
    return Secretos(CLAVE_BACKEND, CLAVE_GATEWAY)


@pytest.fixture
def gateway():
    return GatewayFalso()


def crear_llm(gateway: GatewayFalso, clave: str = CLAVE_GATEWAY) -> ClienteLLM:
    return ClienteLLM("http://gateway.prueba", clave, "llama3.2:3b", reintentos=2, espera_inicial_s=0,
                      http=httpx.Client(transport=httpx.MockTransport(gateway)), dormir=lambda s: None)


@pytest.fixture
def construir(cfg, gateway, tmp_path):
    """Devuelve una función que crea un agente con piezas simuladas. Reusar la ruta de la base simula un reinicio."""
    ruta_db = tmp_path / "agente.sqlite3"

    def _construir(velas=None, pronostico=0.002, ruta=ruta_db, llm=None):
        mercado = MercadoFalso(velas or generar_velas())
        modelo = ModeloPronostico(cfg["modelo"], raiz=tmp_path, funcion=lambda r: pronostico)
        ahora = mercado.velas[-1].close_time + 10 * 60_000
        return Agente(cfg, Base(ruta), mercado, modelo, llm or crear_llm(gateway), reloj=lambda: ahora)

    return _construir
