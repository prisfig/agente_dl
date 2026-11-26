"""Ciclo completo, control humano, persistencia y los nueve escenarios de error del protocolo."""
import pytest
from fastapi.testclient import TestClient

from app.main import crear_app
from app.mexc import ErrorMercado
from tests.conftest import CLAVE_BACKEND, crear_llm, generar_velas


def contar(agente, tabla, modo="vivo"):
    return agente.db.consultar(f"SELECT COUNT(*) AS n FROM {tabla} WHERE modo=?", (modo,))[0]["n"]


def ultimo_evento(agente, tipo):
    filas = agente.db.consultar("SELECT * FROM eventos WHERE tipo=? ORDER BY id DESC LIMIT 1", (tipo,))
    return filas[0] if filas else None


# ---------- ciclo normal ----------
def test_ciclo_completo_tres_carteras(construir):
    a = construir()
    a.iniciar()
    r = a.ciclo_vivo()
    assert r["resultado"] == "completo"
    assert set(r["decisiones"]) == {"sin_llm", "con_llm", "comprar_y_mantener"}
    assert contar(a, "ciclos") == 1 and contar(a, "decisiones") == 3 and contar(a, "patrimonio") == 3
    c = a.db.carteras("vivo")
    assert c["comprar_y_mantener"].en_posicion
    assert c["con_llm"].stop is not None if c["con_llm"].en_posicion else True
    d = a.db.consultar("SELECT * FROM decisiones WHERE cartera='con_llm'")[0]
    assert d["justificacion"] and d["detalle_llm"]


def test_no_decide_si_no_esta_corriendo(construir):
    a = construir()
    assert a.ciclo_vivo()["resultado"] == "omitido"           # estado inicial: detenido
    a.iniciar(); a.pausar()
    assert a.ciclo_vivo()["resultado"] == "omitido"
    assert contar(a, "ciclos") == 0


# ---------- los nueve escenarios ----------
def test_error_1_api_sin_respuesta_o_limite(construir):
    a = construir()
    a.iniciar()
    a.mercado.fallo = ErrorMercado("limite_solicitudes", "MEXC limitó las solicitudes. Se agotaron 3 intentos.", 3)
    r = a.ciclo_vivo()
    assert r["resultado"] == "error" and r["tipo"] == "limite_solicitudes"
    assert a.db.estado()["estado"] == "pausado" and contar(a, "ordenes") == 0
    assert ultimo_evento(a, "limite_solicitudes")


def test_error_2_dato_atrasado(construir):
    velas = generar_velas()
    a = construir(velas=velas)
    a.reloj = lambda: velas[-1].close_time + 30 * 3_600_000     # 30 h > 26 h
    a.iniciar()
    r = a.ciclo_vivo()
    assert r["tipo"] == "dato_atrasado" and a.db.estado()["estado"] == "pausado" and contar(a, "ordenes") == 0


def test_error_3_ollama_detenido(construir, gateway):
    a = construir()
    a.iniciar()
    gateway.modo = "ollama_detenido"
    r = a.ciclo_vivo()
    assert r["tipo"] == "llm_no_disponible" and a.db.estado()["estado"] == "pausado"
    assert contar(a, "ciclos") == 0          # la vela no se marca como procesada: se puede reintentar


def test_error_4_json_invalido(construir, gateway):
    a = construir()
    a.iniciar()
    gateway.modo = "json_invalido"
    r = a.ciclo_vivo()
    assert r["tipo"] == "json_invalido" and contar(a, "ordenes") == 0
    assert ultimo_evento(a, "json_invalido")["detalle"]


def test_error_5_clave_incorrecta_gateway_y_api(construir, gateway, cfg, secretos):
    a = construir(llm=crear_llm(gateway, clave="clave-equivocada-xxxxxxxxxxxxxxxx"))
    a.iniciar()
    assert a.ciclo_vivo()["tipo"] == "clave_incorrecta"
    # API privada: sin clave o con clave incorrecta → 401
    with TestClient(crear_app(cfg, secretos, agente=construir(), programar=False)) as cli:
        assert cli.get("/api/estado").status_code == 401
        assert cli.post("/api/agente/iniciar", headers={"X-API-Key": "mala"}).status_code == 401
        assert cli.get("/api/estado", headers={"X-API-Key": CLAVE_BACKEND}).status_code == 200


def test_error_6_saldo_insuficiente(construir):
    a = construir()
    a.iniciar()
    with a.db.transaccion() as con:      # carteras casi sin efectivo
        from app.paper import Cartera
        for n in ("sin_llm", "con_llm", "comprar_y_mantener"):
            a.db.guardar_cartera(con, "vivo", Cartera(n, 0.5))
    r = a.ciclo_vivo()
    assert r["resultado"] == "completo"
    assert all(d["final"] == "MANTENER" for d in r["decisiones"].values())
    rech = a.db.consultar("SELECT * FROM ordenes WHERE estado='rechazada'")
    assert rech and all("saldo_insuficiente" in o["motivo"] for o in rech)
    assert ultimo_evento(a, "saldo_insuficiente")


def test_error_7_evento_duplicado(construir):
    a = construir()
    a.iniciar()
    assert a.ciclo_vivo()["resultado"] == "completo"
    ordenes = contar(a, "ordenes")
    r = a.ciclo_vivo()
    assert r["resultado"] == "duplicado" and contar(a, "ordenes") == ordenes and contar(a, "ciclos") == 1
    assert ultimo_evento(a, "evento_duplicado")


def test_error_8_reinicio_del_backend_sin_duplicados(construir, tmp_path):
    ruta = tmp_path / "persistente.sqlite3"
    velas = generar_velas()
    a = construir(velas=velas[:-1], ruta=ruta)
    a.iniciar()
    a.ciclo_vivo()
    antes = {n: c.a_dict() for n, c in a.db.carteras("vivo").items()}
    a.db.con.close()
    # "reinicio": nueva instancia con la misma base
    b = construir(velas=velas[:-1], ruta=ruta)
    assert b.db.estado()["estado"] == "corriendo"
    assert {n: c.a_dict() for n, c in b.db.carteras("vivo").items()} == antes
    assert b.ciclo_vivo()["resultado"] == "duplicado"
    assert contar(b, "ciclos") == 1
    # al llegar una vela nueva, continúa desde el estado recuperado
    c = construir(velas=velas, ruta=ruta)
    assert c.ciclo_vivo()["resultado"] == "completo" and contar(c, "ciclos") == 2


def test_error_9_boton_detener(construir):
    a = construir()
    a.iniciar()
    a.ciclo_vivo()
    pos = {n: c.btc for n, c in a.db.carteras("vivo").items()}
    a.detener()
    assert a.db.estado()["estado"] == "detenido"
    assert a.ciclo_vivo()["resultado"] == "omitido"
    assert {n: c.btc for n, c in a.db.carteras("vivo").items()} == pos      # detener no liquida
    r = a.liquidar("vivo")                                                   # liquidar es una acción explícita
    assert all(c.btc == 0 for c in a.db.carteras("vivo").values())
    assert set(r["liquidadas"]) == {n for n, b in pos.items() if b > 0}


def test_liquidar_exige_detener_o_pausar(construir):
    a = construir()
    a.iniciar()
    a.ciclo_vivo()
    with pytest.raises(ValueError):
        a.liquidar("vivo")


# ---------- riesgo dentro del ciclo ----------
def test_llm_no_puede_saltarse_el_bloqueo(construir, gateway):
    velas = generar_velas()
    a = construir(velas=velas[:-1])
    a.iniciar()
    a.ciclo_vivo()
    with a.db.transaccion() as con:
        for c in a.db.carteras("vivo").values():
            c.bloqueo_perdida = True
            if c.nombre == "con_llm":
                c.btc, c.efectivo, c.stop = 0.0, 50_000.0, None
            a.db.guardar_cartera(con, "vivo", c)
    a.mercado.velas = velas
    gateway.accion = "COMPRAR"
    r = a.ciclo_vivo()
    assert r["decisiones"]["con_llm"]["propuesta"] == "COMPRAR"
    assert r["decisiones"]["con_llm"]["final"] == "MANTENER"


# ---------- replay separado ----------
def test_replay_separado_del_vivo(construir):
    a = construir()
    a.iniciar()
    a.ciclo_vivo()
    vivos = contar(a, "ciclos")
    fechas = [v.fecha for v in a.mercado.velas]
    import app.agente as mod
    real = mod.datetime

    class FalsoDT(real):
        @classmethod
        def now(cls, tz=None):
            return real(2026, 12, 1, tzinfo=tz)
    mod.datetime = FalsoDT
    try:
        r = a.replay(fechas[-10], fechas[-3])
    finally:
        mod.datetime = real
    assert r["procesados"] == 8 and r["error"] is None
    assert contar(a, "ciclos", "replay") == 8 and contar(a, "ciclos") == vivos
    assert a.db.estado()["estado"] == "corriendo"


def test_api_flujo_de_control(construir, cfg, secretos):
    h = {"X-API-Key": CLAVE_BACKEND}
    with TestClient(crear_app(cfg, secretos, agente=construir(), programar=False)) as cli:
        assert cli.post("/api/agente/iniciar", headers=h).json()["estado"] == "corriendo"
        assert cli.post("/api/ciclo", headers=h).json()["resultado"] == "completo"
        est = cli.get("/api/estado", headers=h).json()
        assert est["ultimo_ciclo"]["fecha_vela"] and len(est["decisiones"]) == 3
        assert cli.post("/api/agente/pausar", headers=h).json()["estado"] == "pausado"
        assert cli.post("/api/agente/detener", headers=h).json()["estado"] == "detenido"
        m = cli.get("/api/metricas", headers=h).json()
        assert set(m["carteras"]) == {"sin_llm", "con_llm", "comprar_y_mantener"}
        assert cli.get("/api/config", headers=h).json()["riesgo"]["perdida_diaria_maxima"] == 0.03


def test_api_vistas_de_la_interfaz(construir, cfg, secretos):
    h = {"X-API-Key": CLAVE_BACKEND}
    with TestClient(crear_app(cfg, secretos, agente=construir(), programar=False)) as cli:
        cli.post("/api/agente/iniciar", headers=h)
        cli.post("/api/ciclo", headers=h)
        m = cli.get("/api/mercado", headers=h).json()
        assert len(m["velas"]) == len(m["sma20"]) and m["ordenes"]
        e = cli.get("/api/escaner", headers=h).json()
        assert e["pares"][0]["operable"] and "cierre" in e["pares"][0]
        r = cli.get("/api/red", headers=h).json()
        assert r["fecha_vela"] and r["activaciones"] is None          # modelo simulado: sin activaciones
        s = cli.get("/api/sistema", headers=h).json()
        assert s["mexc"]["estado"] == "conectado" and s["llm"]["estado"] == "disponible"
        assert cli.get("/api/evidencia", headers=h).status_code == 200
        for ruta in ("/api/mercado", "/api/escaner", "/api/red", "/api/sistema", "/api/evidencia"):
            assert cli.get(ruta).status_code == 401
