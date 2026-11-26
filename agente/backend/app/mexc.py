"""Datos públicos de MEXC (solo lectura). No existe ninguna ruta para órdenes reales."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable

import httpx

DIA_MS = 86_400_000
# Lista blanca: solo endpoints públicos de lectura. Cualquier otra ruta se rechaza.
RUTAS_PERMITIDAS = frozenset({"/api/v3/klines", "/api/v3/exchangeInfo", "/api/v3/time", "/api/v3/ping",
                              "/api/v3/ticker/price"})   # v1.8: último precio (solo lectura, informativo)
ORDENES_REALES_HABILITADAS = False


class ErrorMercado(Exception):
    """tipo: sin_respuesta | limite_solicitudes | dato_invalido | dato_atrasado | ruta_bloqueada"""

    def __init__(self, tipo: str, mensaje: str, intentos: int = 0):
        super().__init__(mensaje)
        self.tipo = tipo
        self.intentos = intentos


@dataclass(frozen=True)
class Vela:
    fecha: str          # YYYY-MM-DD (UTC) de apertura
    open_time: int      # ms
    close_time: int     # ms
    open: float
    high: float
    low: float
    close: float
    volume: float

    def a_dict(self) -> dict:
        return asdict(self)


def fecha_utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def ahora_ms() -> int:
    return int(time.time() * 1000)


class ClienteMEXC:
    def __init__(
        self,
        url_base: str,
        simbolo: str,
        intervalo: str = "1d",
        reintentos: int = 3,
        espera_inicial_s: float = 2.0,
        timeout_s: float = 10.0,
        http: httpx.Client | None = None,
        dormir: Callable[[float], None] = time.sleep,
    ):
        self.url_base = url_base.rstrip("/")
        self.simbolo = simbolo
        self.intervalo = intervalo
        self.reintentos = reintentos
        self.espera_inicial_s = espera_inicial_s
        self.http = http or httpx.Client(timeout=timeout_s)
        self.dormir = dormir
        self.ultimo_intentos = 0

    # ---------- transporte con reintentos y espera creciente ----------
    def _get(self, ruta: str, params: dict) -> object:
        if ruta not in RUTAS_PERMITIDAS:
            raise ErrorMercado("ruta_bloqueada", f"Ruta no permitida: {ruta}. El sistema solo lee datos públicos.")
        ultimo_tipo, ultimo_msg = "sin_respuesta", ""
        for intento in range(1, self.reintentos + 1):
            self.ultimo_intentos = intento
            espera = self.espera_inicial_s * 2 ** (intento - 1)
            try:
                resp = self.http.get(self.url_base + ruta, params=params)
            except httpx.TimeoutException as e:
                ultimo_tipo, ultimo_msg = "sin_respuesta", f"Tiempo de espera agotado: {e.__class__.__name__}"
            except httpx.TransportError as e:
                ultimo_tipo, ultimo_msg = "sin_respuesta", f"Sin conexión con MEXC: {e.__class__.__name__}"
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError:
                        raise ErrorMercado("dato_invalido", "MEXC respondió algo que no es JSON.", intento)
                if resp.status_code in (418, 429):
                    ultimo_tipo, ultimo_msg = "limite_solicitudes", f"MEXC limitó las solicitudes (HTTP {resp.status_code})."
                    try:
                        espera = max(espera, float(resp.headers.get("Retry-After", 0)))
                    except ValueError:
                        pass
                elif resp.status_code >= 500:
                    ultimo_tipo, ultimo_msg = "sin_respuesta", f"MEXC devolvió HTTP {resp.status_code}."
                else:
                    raise ErrorMercado("dato_invalido", f"MEXC devolvió HTTP {resp.status_code}: {resp.text[:200]}", intento)
            if intento < self.reintentos:
                self.dormir(espera)
        raise ErrorMercado(ultimo_tipo, f"{ultimo_msg} Se agotaron {self.reintentos} intentos.", self.reintentos)

    # ---------- velas ----------
    def _parsear_velas(self, filas: object) -> list[Vela]:
        if not isinstance(filas, list):
            raise ErrorMercado("dato_invalido", "La respuesta de velas no es una lista.")
        velas = []
        for f in filas:
            if not isinstance(f, list) or len(f) < 7:
                raise ErrorMercado("dato_invalido", "Vela con formato inesperado.")
            ot, ct = int(f[0]), int(f[6])
            v = Vela(fecha_utc(ot), ot, ct, float(f[1]), float(f[2]), float(f[3]), float(f[4]), float(f[5]))
            if v.close <= 0 or v.high < v.low:
                raise ErrorMercado("dato_invalido", f"Vela {v.fecha} con precios inválidos.")
            velas.append(v)
        for a, b in zip(velas, velas[1:]):
            if b.open_time <= a.open_time:
                raise ErrorMercado("dato_invalido", "Las velas no vienen en orden cronológico.")
        if self.intervalo == "1d":
            velas = [v for v in velas if v.open_time % DIA_MS == 0]   # solo cortes 00:00 UTC
        return velas

    def velas_cerradas(self, limite: int = 60, ahora: int | None = None) -> list[Vela]:
        """Velas diarias cerradas más recientes. Descarta la vela en curso."""
        ahora = ahora if ahora is not None else ahora_ms()
        filas = self._get("/api/v3/klines", {"symbol": self.simbolo, "interval": self.intervalo, "limit": limite + 1})
        return [v for v in self._parsear_velas(filas) if v.close_time <= ahora]

    def velas_rango(self, inicio_ms: int, fin_ms: int) -> list[Vela]:
        """Velas cerradas entre dos instantes (para replay histórico). Descarga en bloques."""
        velas: list[Vela] = []
        cursor = inicio_ms
        while cursor < fin_ms:
            bloque_fin = min(fin_ms, cursor + 200 * DIA_MS)
            filas = self._get("/api/v3/klines", {
                "symbol": self.simbolo, "interval": self.intervalo,
                "startTime": cursor, "endTime": bloque_fin, "limit": 1000,
            })
            nuevas = [v for v in self._parsear_velas(filas) if v.open_time >= cursor]
            velas.extend(v for v in nuevas if not velas or v.open_time > velas[-1].open_time)
            cursor = bloque_fin
        ahora = ahora_ms()
        return [v for v in velas if v.close_time <= min(fin_ms, ahora)]

    def reglas_par(self, respaldo: dict) -> dict:
        """Tamaño mínimo y precisión del par. Usa valores de respaldo si MEXC no responde."""
        try:
            info = self._get("/api/v3/exchangeInfo", {"symbol": self.simbolo})
            simbolos = info.get("symbols", []) if isinstance(info, dict) else []
            s = next(x for x in simbolos if x.get("symbol") == self.simbolo)
            return {
                "paso_cantidad": str(s.get("baseSizePrecision") or respaldo["paso_cantidad"]),
                "monto_minimo": str(s.get("quoteAmountPrecision") or respaldo["monto_minimo"]),
                "decimales_base": s.get("baseAssetPrecision"),
                "decimales_cotizado": s.get("quotePrecision"),
                "estado": s.get("status"),
                "fuente": "MEXC exchangeInfo",
            }
        except (ErrorMercado, StopIteration, AttributeError, KeyError):
            return {"paso_cantidad": respaldo["paso_cantidad"], "monto_minimo": respaldo["monto_minimo"],
                    "fuente": "respaldo de configuración (exchangeInfo no disponible)"}

    def precios_actuales(self, simbolos) -> dict[str, float]:
        """Último precio negociado de cada par (una sola consulta pública). Solo se muestra en la interfaz;
        el agente decide y ejecuta con el cierre diario."""
        datos = self._get("/api/v3/ticker/price", {})
        if not isinstance(datos, list):
            raise ErrorMercado("dato_invalido", "La respuesta de ticker/price no es una lista.")
        quiero = set(simbolos)
        salida = {}
        for d in datos:
            try:
                if d.get("symbol") in quiero:
                    salida[d["symbol"]] = float(d["price"])
            except (TypeError, ValueError, KeyError, AttributeError):
                continue
        return salida

    def latencia_ms(self) -> float:
        t0 = time.perf_counter()
        self._get("/api/v3/time", {})
        return (time.perf_counter() - t0) * 1000

    def para_simbolo(self, simbolo: str) -> "ClienteMEXC":
        """Cliente de solo lectura para otro par (escáner informativo); comparte la conexión HTTP."""
        return ClienteMEXC(self.url_base, simbolo, self.intervalo, 1, 0, http=self.http, dormir=self.dormir)

    # ---------- bloqueo explícito de operaciones reales ----------
    def enviar_orden_real(self, *_, **__):
        raise PermissionError("Órdenes reales deshabilitadas: este sistema solo ejecuta en el simulador Paper.")


def verificar_antiguedad(vela: Vela, max_horas: float, ahora: int | None = None) -> float:
    """Devuelve la antigüedad en horas desde el cierre; lanza ErrorMercado si supera el límite."""
    ahora = ahora if ahora is not None else ahora_ms()
    horas = (ahora - vela.close_time) / 3_600_000
    if horas > max_horas:
        raise ErrorMercado("dato_atrasado",
                           f"La última vela cerrada ({vela.fecha}) tiene {horas:.1f} h de antigüedad; el máximo es {max_horas} h.")
    return horas
