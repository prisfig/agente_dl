"""v1.5: límite de tokens por respuesta del LLM (num_predict de Ollama).

Motivo: el 17 nov la respuesta final de XRP generó 2,328 tokens sin cerrar el JSON y el gateway la cortó a los 2 min
(tres veces). Con el límite, una respuesta desbocada se corta en segundos y se maneja como JSON inválido."""
import json

import httpx
import pytest

from app.llm import ClienteLLM, ErrorLLM
from tests.conftest import CLAVE_GATEWAY


class OllamaDesbocado:
    """Fase 1 normal; respuesta final que nunca cierra el JSON (como XRP) mientras `desbocadas` > 0."""

    def __init__(self, desbocadas: int):
        self.desbocadas = desbocadas
        self.llamadas: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content)
        self.llamadas.append(cuerpo)
        if "tools" in cuerpo:
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}, "done_reason": "stop"})
        if self.desbocadas > 0:
            self.desbocadas -= 1
            return httpx.Response(200, json={"message": {"role": "assistant",
                                  "content": '{"accion": "MANTENER", "simbolo": "XRPUSDT", "fecha_vela": "2026-11-17", "justificacion": "El ' + "precio " * 300},
                                  "done_reason": "length"})
        return httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps(
            {"accion": "MANTENER", "simbolo": "XRPUSDT", "fecha_vela": "2026-11-17", "justificacion": "Pronóstico +0.1177 % bajo δ 0.3708 %."})},
            "done_reason": "stop"})


OBS = {"simbolo": "XRPUSDT", "fecha_vela": "2026-11-17", "acciones_validas": ["COMPRAR", "MANTENER"]}


def cliente(transporte, max_tokens=400, reintentos=3):
    return ClienteLLM("http://gateway.prueba", CLAVE_GATEWAY, "llama3.2:3b", reintentos=reintentos, espera_inicial_s=0,
                      http=httpx.Client(transport=httpx.MockTransport(transporte)), dormir=lambda s: None,
                      max_tokens_respuesta=max_tokens)


def test_el_limite_viaja_a_ollama_en_las_dos_fases():
    o = OllamaDesbocado(0)
    cliente(o).proponer(OBS, {})
    assert [c["options"]["num_predict"] for c in o.llamadas] == [400, 400]
    assert all(c["options"]["temperature"] == 0 and c["options"]["seed"] == 42 for c in o.llamadas)


def test_sin_limite_las_opciones_son_las_de_la_v14():
    o = OllamaDesbocado(0)
    cliente(o, max_tokens=None).proponer(OBS, {})
    assert all(c["options"] == {"temperature": 0, "seed": 42} for c in o.llamadas)


def test_respuesta_desbocada_se_corta_y_el_reintento_la_recupera():
    o = OllamaDesbocado(1)
    r = cliente(o).proponer(OBS, {})
    assert r.propuesta.accion == "MANTENER" and r.intentos == 2
    assert any("respuesta_cortada_por_limite_de_tokens" in a for a in r.avisos)
    reintento = o.llamadas[-1]["messages"][-1]["content"]
    assert "límite de 400 tokens" in reintento                       # el modelo recibe por qué falló


def test_si_siempre_se_desboca_el_error_es_json_invalido_con_motivo_claro():
    o = OllamaDesbocado(99)
    with pytest.raises(ErrorLLM) as e:
        cliente(o).proponer(OBS, {})
    assert e.value.tipo == "json_invalido" and "límite de 400 tokens" in str(e.value) and e.value.intentos == 3


def test_la_demostracion_de_json_invalido_conserva_su_limite_propio(cfg):
    """La instancia de demostración corta la respuesta final a 6 tokens (opciones_extra) y eso debe seguir mandando."""
    import json as _json
    from app.ajustes import AGENTE_DIR
    demo = _json.loads((AGENTE_DIR / "config/demo/demo_json_invalido.json").read_text())["llm"]
    o = OllamaDesbocado(0)
    c = ClienteLLM("http://gateway.prueba", CLAVE_GATEWAY, "llama3.2:3b", reintentos=1, espera_inicial_s=0,
                   http=httpx.Client(transport=httpx.MockTransport(o)), dormir=lambda s: None,
                   max_tokens_respuesta=demo["max_tokens_respuesta"], opciones_extra=demo.get("opciones_extra"))
    c.proponer(OBS, {})
    assert o.llamadas[0]["options"]["num_predict"] == 400
    assert o.llamadas[1]["options"]["num_predict"] == demo["opciones_extra"]["num_predict"]


def test_config_real_trae_el_limite(cfg_completa):
    assert cfg_completa["llm"]["max_tokens_respuesta"] == 400
