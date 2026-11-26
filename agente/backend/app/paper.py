"""Simulador Paper: dinero virtual, respeta saldo, tamaño mínimo y precisión del par, costos y deslizamiento."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import ROUND_DOWN, Decimal

COMPRAR, MANTENER, VENDER = "COMPRAR", "MANTENER", "VENDER"
ACCIONES = (COMPRAR, MANTENER, VENDER)


@dataclass
class Cartera:
    nombre: str
    efectivo: float
    btc: float = 0.0
    precio_entrada: float | None = None
    stop: float | None = None
    patrimonio_previo: float | None = None   # patrimonio al cierre del ciclo anterior
    bloqueo_perdida: bool = False

    @property
    def en_posicion(self) -> bool:
        return self.btc > 0

    def patrimonio(self, precio: float) -> float:
        return self.efectivo + self.btc * precio

    def a_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoOrden:
    ejecutada: bool
    lado: str
    cantidad: float = 0.0
    precio: float = 0.0
    monto: float = 0.0
    costo: float = 0.0
    motivo: str = ""


class MotorPaper:
    def __init__(self, paso_cantidad: str, monto_minimo: str, costo_compra: float = 0.0,
                 costo_venta: float = 0.0, deslizamiento: float = 0.0):
        self.paso = Decimal(str(paso_cantidad))
        self.monto_minimo = float(monto_minimo)
        self.costo_compra = costo_compra
        self.costo_venta = costo_venta
        self.deslizamiento = deslizamiento

    def _ajustar(self, cantidad: float) -> float:
        if cantidad <= 0:
            return 0.0
        return float((Decimal(str(cantidad)) / self.paso).to_integral_value(rounding=ROUND_DOWN) * self.paso)

    def comprar(self, c: Cartera, precio: float, exposicion_maxima: float) -> ResultadoOrden:
        if c.en_posicion:
            return ResultadoOrden(False, COMPRAR, motivo="ya_en_posicion")
        precio_ej = precio * (1 + self.deslizamiento)
        presupuesto = min(c.efectivo, exposicion_maxima * c.patrimonio(precio))
        cantidad = self._ajustar(presupuesto / (precio_ej * (1 + self.costo_compra)))
        monto = cantidad * precio_ej
        costo = monto * self.costo_compra
        if cantidad <= 0 or monto < self.monto_minimo:
            return ResultadoOrden(False, COMPRAR, cantidad, precio_ej, monto, costo,
                                  f"saldo_insuficiente: el monto {monto:.2f} es menor al mínimo del par ({self.monto_minimo})")
        if monto + costo > c.efectivo + 1e-9:
            return ResultadoOrden(False, COMPRAR, cantidad, precio_ej, monto, costo, "saldo_insuficiente")
        c.efectivo -= monto + costo
        c.btc += cantidad
        c.precio_entrada = precio_ej
        return ResultadoOrden(True, COMPRAR, cantidad, precio_ej, monto, costo, "ejecutada")

    def vender(self, c: Cartera, precio: float) -> ResultadoOrden:
        cantidad = self._ajustar(c.btc)
        if cantidad <= 0:
            return ResultadoOrden(False, VENDER, motivo="sin_posicion")
        precio_ej = precio * (1 - self.deslizamiento)
        monto = cantidad * precio_ej
        costo = monto * self.costo_venta
        c.efectivo += monto - costo
        resto = c.btc - cantidad
        # Las compras siempre son múltiplos del paso, así que el resto solo es ruido de punto flotante.
        c.btc = resto if resto >= float(self.paso) else 0.0
        if c.btc == 0:
            c.precio_entrada = None
            c.stop = None
        return ResultadoOrden(True, VENDER, cantidad, precio_ej, monto, costo, "ejecutada")
