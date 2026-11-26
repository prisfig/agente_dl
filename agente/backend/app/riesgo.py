"""Controles deterministas de riesgo. La propuesta del LLM nunca sustituye estas reglas."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .paper import ACCIONES, COMPRAR, MANTENER, VENDER


@dataclass(frozen=True)
class LimitesRiesgo:
    exposicion_maxima: float
    perdida_diaria_maxima: float
    stop_movil_k_vol: float
    antiguedad_maxima_horas: float

    @classmethod
    def desde_config(cls, r: dict) -> "LimitesRiesgo":
        return cls(r["exposicion_maxima"], r["perdida_diaria_maxima"], r["stop_movil_k_vol"], r["antiguedad_maxima_horas"])


@dataclass
class DecisionRiesgo:
    propuesta: str
    accion: str
    aprobada: bool
    motivos: list[str] = field(default_factory=list)
    activa_bloqueo: bool = False
    variacion_diaria: float | None = None

    def a_dict(self) -> dict:
        return asdict(self)


def evaluar(propuesta: str, *, en_posicion: bool, cierre: float, stop: float | None,
            patrimonio_actual: float, patrimonio_previo: float | None, bloqueo_vigente: bool,
            limites: LimitesRiesgo, usar_stop: bool = True, decimales: int = 2) -> DecisionRiesgo:
    motivos: list[str] = []
    accion = propuesta

    # 1. Acción permitida y coherente con la posición
    if propuesta not in ACCIONES:
        accion = MANTENER
        motivos.append(f"accion_no_permitida: '{propuesta}' se reemplaza por MANTENER")
    elif propuesta == COMPRAR and en_posicion:
        accion = MANTENER
        motivos.append("compra_rechazada: ya hay una posición abierta")
    elif propuesta == VENDER and not en_posicion:
        accion = MANTENER
        motivos.append("venta_rechazada: no hay posición que vender (sin ventas en corto)")

    # 2. Pérdida diaria máxima
    variacion = None
    activa = False
    if patrimonio_previo:
        variacion = patrimonio_actual / patrimonio_previo - 1
        if variacion <= -limites.perdida_diaria_maxima and not bloqueo_vigente:
            activa = True
            motivos.append(f"perdida_diaria: {variacion:.2%} ≤ −{limites.perdida_diaria_maxima:.0%}; se bloquean nuevas compras")
    bloqueado = bloqueo_vigente or activa

    # 3. Stop móvil (prioridad sobre la propuesta)
    if usar_stop and en_posicion and stop is not None and cierre < stop:
        if accion != VENDER:
            motivos.append(f"stop_movil: cierre {cierre:,.{decimales}f} < stop {stop:,.{decimales}f}; venta forzada")
        accion = VENDER

    # 4. Bloqueo de compras
    if accion == COMPRAR and bloqueado:
        accion = MANTENER
        motivos.append("compra_bloqueada: control de pérdida diaria activo (requiere rearme manual)")

    return DecisionRiesgo(propuesta, accion, accion == propuesta, motivos, activa, variacion)


def nuevo_stop(stop_actual: float | None, cierre: float, vol20: float, k: float, recien_comprado: bool) -> float:
    """Stop móvil: cierre × (1 − k·vol20). Solo sube mientras la posición sigue abierta."""
    candidato = cierre * (1 - k * vol20)
    if recien_comprado or stop_actual is None:
        return candidato
    return max(stop_actual, candidato)


def accion_estrategia(senal: str, en_posicion: bool) -> str:
    """Política sin LLM: la señal de la estrategia del activo (C o D) convertida en acción sobre la posición."""
    if senal == "comprar" and not en_posicion:
        return COMPRAR
    if senal == "efectivo" and en_posicion:
        return VENDER
    return MANTENER


accion_estrategia_d = accion_estrategia   # nombre anterior a la v1.3
