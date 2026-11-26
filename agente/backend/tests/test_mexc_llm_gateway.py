"""Datos de MEXC, cliente del LLM y gateway con API key."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.llm import ErrorLLM
from app.mexc import DIA_MS, ClienteMEXC, ErrorMercado, verificar_antiguedad
from gateway.main import crear_app as crear_gateway
from tests.conftest import CLAVE_GATEWAY, crear_llm, generar_velas


def cliente_mexc(manejador, reintentos=3):
    esperas = []
    c = ClienteMEXC("https://api.mexc.test", "BTCUSDT", reintentos=reintentos, espera_inicial_s=1.0,
                    http=httpx.Client(transport=httpx.MockTransport(manejador)), dormir=esperas.append)
    return c, esperas


def filas(velas):
    return [[v.open_time, str(v.open), str(v.high), str(v.low), str(v.close), str(v.volume), v.close_time, "0"] for v in velas]


# ---------- MEXC ----------
def test_mexc_limite_de_solicitudes_reintenta_con_espera_creciente_y_falla():
    c, esperas = cliente_mexc(lambda r: httpx.Response(429))
    with pytest.raises(ErrorMercado) as e:
        c.velas_cerradas()
    assert e.value.tipo == "limite_solicitudes" and esperas == [1.0, 2.0]


def test_mexc_sin_respuesta():
    def caido(r):
        raise httpx.ConnectTimeout("timeout")
    c, esperas = cliente_mexc(caido)
    with pytest.raises(ErrorMercado) as e:
        c.velas_cerradas()
    assert e.value.tipo == "sin_respuesta" and len(esperas) == 2


def test_mexc_recupera_si_el_segundo_intento_funciona():
    velas = generar_velas(30)
    respuestas = iter([httpx.Response(503), httpx.Response(200, json=filas(velas))])
    c, _ = cliente_mexc(lambda r: next(respuestas))
    assert len(c.velas_cerradas(ahora=velas[-1].close_time)) == 30


def test_mexc_descarta_vela_abierta():
    velas = generar_velas(30)
    c, _ = cliente_mexc(lambda r: httpx.Response(200, json=filas(velas)))
    cerradas = c.velas_cerradas(ahora=velas[-1].close_time - 1)     # la última aún no cierra
    assert cerradas[-1].fecha == velas[-2].fecha


def test_dato_atrasado():
    v = generar_velas(30)[-1]
    assert verificar_antiguedad(v, 26, v.close_time + 3_600_000) == pytest.approx(1.0)
    with pytest.raises(ErrorMercado) as e:
        verificar_antiguedad(v, 26, v.close_time + 2 * DIA_MS)
    assert e.value.tipo == "dato_atrasado"


def test_bloqueo_de_operaciones_reales():
    c, _ = cliente_mexc(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ErrorMercado) as e:
        c._get("/api/v3/order", {"symbol": "BTCUSDT", "side": "BUY"})
    assert e.value.tipo == "ruta_bloqueada"
    with pytest.raises(PermissionError):
        c.enviar_orden_real("BTCUSDT", "BUY", 1)


# ---------- LLM ----------
OBS = {"simbolo": "BTCUSDT", "fecha_vela": "2026-11-14", "pronostico_rendimiento_siguiente_dia": "+0.2000 %",
       "acciones_validas": ["COMPRAR", "MANTENER"]}


def test_detecta_valores_inventados_en_la_justificacion():
    from app.llm import valores_no_presentes
    datos = {"pronostico_rendimiento_siguiente_dia": "+0.1783 %", "umbral_delta": "0.0866 %", "volatilidad_20d": "2.092 %"}
    # Caso real del replay v1: el modelo leyó 0.1783 % como 17.83 %
    assert valores_no_presentes("El pronóstico es 17.83% y delta 8.66%", datos) == ["17.83", "8.66"]
    assert valores_no_presentes("El pronóstico es 0.1783 % > delta 0.0866 %; volatilidad 2.092 %", datos) == []


def test_llm_respuesta_valida_con_herramienta(gateway):
    r = crear_llm(gateway).proponer(OBS, {"consultar_indicadores": {"pronostico_pct": 0.2}})
    assert r.propuesta.accion == "COMPRAR" and r.herramientas == [{"herramienta": "consultar_indicadores", "permitida": True}]
    assert gateway.llamadas[0]["tools"] and gateway.llamadas[-1]["format"]["additionalProperties"] is False


def test_llm_herramienta_no_permitida_se_registra(gateway):
    gateway.pedir_herramienta = "borrar_base_de_datos"
    r = crear_llm(gateway).proponer(OBS, {})
    assert r.herramientas[0]["permitida"] is False and any("no_permitida" in a for a in r.avisos)


@pytest.mark.parametrize("modo,tipo", [("json_invalido", "json_invalido"), ("clave_extra", "respuesta_invalida"),
                                        ("simbolo_malo", "respuesta_invalida")])
def test_llm_respuestas_invalidas_se_rechazan(gateway, modo, tipo):
    gateway.modo = modo
    with pytest.raises(ErrorLLM) as e:
        crear_llm(gateway).proponer(OBS, {})
    assert e.value.tipo == tipo


def test_llm_clave_incorrecta_no_reintenta(gateway):
    with pytest.raises(ErrorLLM) as e:
        crear_llm(gateway, clave="clave-equivocada-xxxxxxxxxxxxxxxx").proponer(OBS, {})
    assert e.value.tipo == "clave_incorrecta" and len(gateway.llamadas) == 1


@pytest.mark.parametrize("modo", ["caido", "ollama_detenido"])
def test_llm_ollama_detenido(gateway, modo):
    gateway.modo = modo
    with pytest.raises(ErrorLLM) as e:
        crear_llm(gateway).proponer(OBS, {})
    assert e.value.tipo == "llm_no_disponible"


# ---------- Gateway ----------
def ollama_falso(request: httpx.Request):
    if request.url.path == "/api/version":
        return httpx.Response(200, json={"version": "0.40.16"})
    cuerpo = json.loads(request.content)
    return httpx.Response(200, json={"model": cuerpo["model"], "message": {"role": "assistant", "content": "{}"}})


@pytest.fixture
def gw():
    app = crear_gateway(CLAVE_GATEWAY, "http://ollama.prueba", httpx.Client(transport=httpx.MockTransport(ollama_falso)))
    return TestClient(app)


def test_gateway_rechaza_clave_ausente_e_incorrecta(gw):
    cuerpo = {"model": "llama3.2:3b", "messages": []}
    assert gw.post("/api/chat", json=cuerpo).status_code == 401
    assert gw.post("/api/chat", json=cuerpo, headers={"X-API-Key": "otra"}).status_code == 401
    assert gw.post("/api/chat", json=cuerpo, headers={"X-API-Key": CLAVE_GATEWAY}).status_code == 200


def test_gateway_solo_modelos_y_campos_permitidos(gw):
    h = {"X-API-Key": CLAVE_GATEWAY}
    assert gw.post("/api/chat", json={"model": "otro:70b", "messages": []}, headers=h).status_code == 403
    assert gw.post("/api/chat", json={"model": "llama3.2:3b", "messages": [], "raw": True}, headers=h).status_code == 400


def test_gateway_ollama_detenido():
    def caido(r):
        raise httpx.ConnectError("rechazada")
    app = crear_gateway(CLAVE_GATEWAY, "http://ollama.prueba", httpx.Client(transport=httpx.MockTransport(caido)))
    r = TestClient(app).post("/api/chat", json={"model": "llama3.2:3b", "messages": []}, headers={"X-API-Key": CLAVE_GATEWAY})
    assert r.status_code == 502


def test_opciones_de_demostracion_solo_en_la_respuesta_final(gateway):
    from tests.conftest import CLAVE_GATEWAY
    import httpx as _h
    from app.llm import ClienteLLM
    llm = ClienteLLM("http://gateway.prueba", CLAVE_GATEWAY, "llama3.2:3b", reintentos=1, espera_inicial_s=0,
                     opciones_extra={"num_predict": 6}, http=_h.Client(transport=_h.MockTransport(gateway)), dormir=lambda s: None)
    llm.proponer(OBS, {})
    assert "num_predict" not in gateway.llamadas[0]["options"]          # fase de herramientas
    assert gateway.llamadas[-1]["options"]["num_predict"] == 6          # respuesta JSON final
