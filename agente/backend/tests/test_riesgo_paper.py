"""Controles deterministas de riesgo y simulador Paper."""
import pytest

from app.paper import COMPRAR, MANTENER, VENDER, Cartera, MotorPaper
from app.riesgo import LimitesRiesgo, accion_estrategia_d, evaluar, nuevo_stop

L = LimitesRiesgo(exposicion_maxima=1.0, perdida_diaria_maxima=0.03, stop_movil_k_vol=2.0, antiguedad_maxima_horas=26)


def ev(prop, **kw):
    base = dict(en_posicion=False, cierre=100.0, stop=None, patrimonio_actual=1000.0, patrimonio_previo=1000.0,
                bloqueo_vigente=False, limites=L)
    base.update(kw)
    return evaluar(prop, **base)


def test_accion_no_permitida_se_reemplaza_por_mantener():
    d = ev("SHORT")
    assert d.accion == MANTENER and not d.aprobada and "accion_no_permitida" in d.motivos[0]


def test_compra_con_posicion_y_venta_sin_posicion_se_rechazan():
    assert ev(COMPRAR, en_posicion=True).accion == MANTENER
    assert ev(VENDER, en_posicion=False).accion == MANTENER


def test_stop_movil_fuerza_venta_aunque_el_llm_diga_mantener():
    d = ev(MANTENER, en_posicion=True, cierre=95.0, stop=96.0)
    assert d.accion == VENDER and any("stop_movil" in m for m in d.motivos)


def test_perdida_diaria_bloquea_compras_pero_no_ventas():
    d = ev(COMPRAR, patrimonio_actual=960.0, patrimonio_previo=1000.0)
    assert d.activa_bloqueo and d.accion == MANTENER
    d2 = ev(VENDER, en_posicion=True, patrimonio_actual=960.0, patrimonio_previo=1000.0)
    assert d2.accion == VENDER
    d3 = ev(COMPRAR, bloqueo_vigente=True)            # sigue bloqueado hasta el rearme manual
    assert d3.accion == MANTENER


def test_stop_solo_sube():
    s = nuevo_stop(None, 100.0, 0.02, 2.0, recien_comprado=True)
    assert s == pytest.approx(96.0)
    assert nuevo_stop(s, 90.0, 0.02, 2.0, False) == pytest.approx(96.0)
    assert nuevo_stop(s, 110.0, 0.02, 2.0, False) == pytest.approx(105.6)


def test_estrategia_d_a_acciones():
    assert accion_estrategia_d("comprar", False) == COMPRAR
    assert accion_estrategia_d("efectivo", True) == VENDER
    assert accion_estrategia_d("comprar", True) == MANTENER
    assert accion_estrategia_d("efectivo", False) == MANTENER


def test_paper_respeta_paso_de_cantidad_y_saldo():
    m = MotorPaper("0.000001", "1", 0.0, 0.0, 0.0)
    c = Cartera("x", 50_000.0)
    r = m.comprar(c, 73_456.78, 1.0)
    assert r.ejecutada
    assert round(r.cantidad / 0.000001) == pytest.approx(r.cantidad / 0.000001)   # múltiplo del paso
    assert c.efectivo >= 0 and r.monto <= 50_000
    v = m.vender(c, 74_000.0)
    assert v.ejecutada and c.btc == 0 and c.stop is None


def test_paper_saldo_insuficiente_y_monto_minimo():
    m = MotorPaper("0.000001", "5", 0.0, 0.0, 0.0)
    c = Cartera("x", 3.0)
    r = m.comprar(c, 70_000.0, 1.0)
    assert not r.ejecutada and "saldo_insuficiente" in r.motivo
    assert c.efectivo == 3.0 and c.btc == 0


def test_paper_exposicion_maxima_y_costos():
    m = MotorPaper("0.000001", "1", 0.001, 0.001, 0.0)
    c = Cartera("x", 10_000.0)
    r = m.comprar(c, 100.0, 0.5)
    assert r.ejecutada and r.monto + r.costo <= 5_000.0 + 1e-6
