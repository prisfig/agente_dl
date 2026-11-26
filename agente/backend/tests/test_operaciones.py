"""v1.8: vista de operaciones (posiciones abiertas, historial, saldo total y riesgo) sobre todos los activos."""
import threading

import pytest
from fastapi.testclient import TestClient

from app.agente import Agente
from app.ajustes import activos_de
from app.db import Base
from app.main import crear_app
from app.modelo import ModeloPronostico
from app.operaciones import comparacion_carteras, resumen_operaciones
from tests.conftest import CLAVE_BACKEND, MercadoFalso, crear_llm, generar_velas

H = {"X-API-Key": CLAVE_BACKEND}


def agente_con_guion(cfg_activo, tmp_path, gateway, pronosticos, lock, accion_llm="MANTENER"):
    """Agente cuyo pronóstico sigue una lista (un valor por ciclo) para provocar compras y ventas."""
    velas = generar_velas(tendencia=0.004, semilla=11)          # tendencia al alza: cierre > SMA20 (vale para C y D)
    guion = iter(pronosticos)
    modelo = ModeloPronostico(cfg_activo["modelo"], raiz=tmp_path, funcion=lambda r: next(guion))
    db = Base(tmp_path / f"{cfg_activo['mercado']['simbolo']}.sqlite3")
    gateway.accion = accion_llm
    a = Agente(cfg_activo, db, MercadoFalso(velas), modelo, crear_llm(gateway), reloj=lambda: velas[-1].close_time, lock=lock)
    return a, velas


@pytest.fixture
def dos_con_historia(cfg_completa, tmp_path, gateway):
    lock = threading.Lock()
    btc, eth = activos_de(cfg_completa)[:2]
    # BTC: compra (ciclo 1), mantiene, vende por señal (ciclo 3), vuelve a comprar (ciclo 4) y queda abierta.
    a, velas = agente_con_guion(btc, tmp_path, gateway, [0.01, 0.01, -0.01, 0.01], lock)
    for n in range(len(velas) - 3, len(velas) + 1):
        assert a._procesar("vivo", velas[:n])["resultado"] == "completo"
    # ETH: sin ciclos todavía (capital intacto).
    b, _ = agente_con_guion(eth, tmp_path, gateway, [], lock)
    return {"BTCUSDT": a, "ETHUSDT": b}, velas


def test_posiciones_abiertas_historial_y_saldo_cuadran(dos_con_historia, cfg_completa):
    agentes, velas = dos_con_historia
    a = agentes["BTCUSDT"]
    r = resumen_operaciones(agentes, "vivo", "sin_llm", 50_000, {"BTCUSDT": velas[-1].close * 1.01}, a.limites)
    assert r["n_activos"] == 2 and r["capital_inicial_total"] == 100_000
    # una operación cerrada por señal y una posición abierta
    assert len(r["cerradas"]) == 1 and len(r["abiertas"]) == 1
    t = r["cerradas"][0]
    assert t["motivo_salida"] == "señal del modelo: efectivo" and t["fecha_compra"] < t["fecha_venta"]
    p = r["abiertas"][0]
    assert p["simbolo"] == "BTCUSDT" and p["lado"] == "LONG" and p["fecha_compra"] == velas[-1].fecha
    assert p["stop"] is not None and p["ultimo_cierre"] == velas[-1].close
    assert p["pnl_actual"] == pytest.approx(p["cantidad"] * velas[-1].close * 1.01 - p["invertido"])
    # saldo total = capital + realizado + no realizado (al cierre)
    assert r["saldo_total"] == pytest.approx(r["capital_inicial_total"] + r["pnl_realizado"] + r["pnl_no_realizado"])
    assert r["saldo_total"] == pytest.approx(r["efectivo_total"] + r["invertido_total"])
    assert r["operaciones_cerradas"] == 1 and r["acierto"] in (0.0, 1.0)
    # ETH sin ciclos cuenta con su capital
    eth = next(x for x in r["por_activo"] if x["simbolo"] == "ETHUSDT")
    assert eth["patrimonio"] == 50_000 and eth["ultima_vela"] is None
    assert r["serie_saldo"][-1]["saldo"] == pytest.approx(r["saldo_total"])


def test_salida_por_stop_movil_se_identifica(cfg_completa, tmp_path, gateway):
    from dataclasses import replace
    btc = activos_de(cfg_completa)[0]
    a, velas = agente_con_guion(btc, tmp_path, gateway, [0.01, 0.01], threading.Lock(), accion_llm="COMPRAR")
    a._procesar("vivo", velas[:-1])                                     # el LLM compra
    gateway.accion = "MANTENER"                                         # luego propone mantener...
    caida = replace(velas[-1], close=velas[-2].close * 0.80, low=velas[-2].close * 0.79)   # ...pero el cierre perfora el stop
    a._procesar("vivo", velas[:-1] + [caida])
    r = resumen_operaciones({"BTCUSDT": a}, "vivo", "con_llm", 50_000, {}, a.limites)
    assert r["cerradas"][0]["motivo_salida"] == "stop móvil" and r["cerradas"][0]["pnl"] < 0
    assert not r["abiertas"] and r["pnl_no_realizado"] == 0


def test_comparacion_de_las_tres_carteras(dos_con_historia):
    agentes, _ = dos_con_historia
    comp = comparacion_carteras(agentes, "vivo", 50_000)
    assert set(comp) == {"sin_llm", "con_llm", "comprar_y_mantener"}
    assert comp["comprar_y_mantener"]["posiciones_abiertas"] == 1                # BTC compró y mantiene; ETH sin ciclos


def test_api_operaciones(cfg_completa, secretos, dos_con_historia):
    agentes, _ = dos_con_historia
    with TestClient(crear_app(cfg_completa, secretos, agentes=agentes, programar=False)) as cli:
        r = cli.get("/api/operaciones?cartera=sin_llm", headers=H)
        assert r.status_code == 200
        d = r.json()
        assert d["cartera"] == "sin_llm" and len(d["abiertas"]) == 1 and set(d["comparacion"]) == {"sin_llm", "con_llm", "comprar_y_mantener"}
        assert d["precios_actuales_disponibles"] is False                       # el mercado falso no da precios: se usa el cierre
        assert cli.get("/api/operaciones?cartera=otra", headers=H).status_code == 422
        assert cli.get("/api/operaciones").status_code == 401


def test_rearmar_todos_los_bloqueados(cfg_completa, secretos, dos_con_historia):
    """v1.9: el botón quita el bloqueo solo de los activos bloqueados y deja un evento en cada uno."""
    agentes, _ = dos_con_historia
    btc, eth = agentes["BTCUSDT"], agentes["ETHUSDT"]
    with btc.db.transaccion() as con:                       # simula el bloqueo que deja una caída ≥ 3 %
        for c in btc.db.carteras("vivo").values():
            if c.nombre in ("sin_llm", "con_llm"):
                c.bloqueo_perdida = True
                btc.db.guardar_cartera(con, "vivo", c)
    eventos_eth = len(eth.db.consultar("SELECT id FROM eventos"))
    with TestClient(crear_app(cfg_completa, secretos, agentes=agentes, programar=False)) as cli:
        d = cli.get("/api/operaciones?cartera=sin_llm", headers=H).json()
        assert d["riesgo"]["bloqueados_todas_carteras"] == {"BTCUSDT": ["con_llm", "sin_llm"]}
        assert cli.post("/api/riesgo/rearmar_todos").status_code == 401
        r = cli.post("/api/riesgo/rearmar_todos", headers=H)
        assert r.status_code == 200 and r.json()["rearmados"] == ["BTCUSDT"] and r.json()["sin_bloqueo"] == ["ETHUSDT"]
        assert not any(c.bloqueo_perdida for c in btc.db.carteras("vivo").values())
        ev = btc.db.consultar("SELECT mensaje, detalle FROM eventos WHERE tipo='control' ORDER BY id DESC LIMIT 1")[0]
        assert "Rearmar todos los bloqueados" in ev["mensaje"] and "con_llm" in ev["detalle"]
        assert len(eth.db.consultar("SELECT id FROM eventos")) == eventos_eth   # sin bloqueo: no se toca
        d = cli.get("/api/operaciones?cartera=sin_llm", headers=H).json()
        assert d["riesgo"]["bloqueados_todas_carteras"] == {}
        assert cli.post("/api/riesgo/rearmar_todos", headers=H).json()["rearmados"] == []   # repetir no hace nada
