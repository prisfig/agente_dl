"""v2.0: laboratorio de señales con avisos por correo (canal principal) y WhatsApp (alternativa), sin red real."""
import json
import threading
from dataclasses import replace

import httpx
import smtplib

import pytest
from fastapi.testclient import TestClient

from app.agente import Agente
from app.ajustes import activos_de
from app.db import Base
from app.main import crear_app
from app.modelo import ModeloPronostico
from app.notificaciones import (CredencialesCorreo, CredencialesWhatsApp, NotificadorCorreo, NotificadorWhatsApp,
                                construir_notificador, notificar_ciclo)
from tests.conftest import CLAVE_BACKEND, MercadoFalso, crear_llm, generar_velas

H = {"X-API-Key": CLAVE_BACKEND}
CRED = CredencialesWhatsApp("+525512345678", "987654")
CFG_WA = {"habilitado": True, "proveedor": "callmebot", "url": "https://api.callmebot.com/whatsapp.php", "reintentos": 2, "espera_inicial_s": 0}
CRED_META = CredencialesWhatsApp("+525512345678", "EAAtokensecreto123", "1029384756")
CFG_META = {"habilitado": True, "proveedor": "meta", "version_api": "v25.0", "reintentos": 2, "espera_inicial_s": 0,
            "plantilla": {"nombre": "senal_laboratorio", "idioma": "es_MX"}}


class CallMeBotFalso:
    """Imita la API de CallMeBot. modo: ok | error_http | caido | clave_mala"""

    def __init__(self, modo="ok"):
        self.modo = modo
        self.mensajes: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.mensajes.append(dict(request.url.params))
        if self.modo == "caido":
            raise httpx.ConnectError("sin red")
        if self.modo == "error_http":
            return httpx.Response(500, text="Internal error")
        if self.modo == "clave_mala":
            return httpx.Response(200, text=f"APIKey is invalid for {request.url.params['phone']} {request.url.params['apikey']}")
        return httpx.Response(200, text="Message queued. You will receive it in a few seconds.")


class MetaFalso:
    """Imita la WhatsApp Cloud API. modo: ok | no_permitido (131030) | token_vencido (190) | caido | error_servidor |
    plantilla_pendiente (132001 solo para plantillas; el texto pasa)"""

    def __init__(self, modo="ok"):
        self.modo = modo
        self.peticiones: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.peticiones.append({"url": str(request.url), "auth": request.headers.get("Authorization"),
                                "cuerpo": json.loads(request.content)})
        if self.modo == "caido":
            raise httpx.ConnectError("sin red")
        if self.modo == "error_servidor":
            return httpx.Response(500, json={"error": {"code": 1, "message": "error interno"}})
        if self.modo == "no_permitido":
            return httpx.Response(400, json={"error": {"code": 131030, "message": "(#131030) Recipient phone number 525512345678 not in allowed list"}})
        if self.modo == "plantilla_pendiente" and json.loads(request.content)["type"] == "template":
            return httpx.Response(404, json={"error": {"code": 132001, "message": "(#132001) Template name does not exist in the translation"}})
        if self.modo == "token_vencido":
            return httpx.Response(401, json={"error": {"code": 190, "message": "Error validating access token EAAtokensecreto123"}})
        return httpx.Response(200, json={"messaging_product": "whatsapp", "contacts": [{"wa_id": "5215512345678"}],
                                         "messages": [{"id": "wamid.HBgMNTIxNTUxMjM0NTY3OBUCABEYEjE2"}]})


def notificador(bot, cred=CRED, cfg=CFG_WA):
    return NotificadorWhatsApp(cfg, cred, http=httpx.Client(transport=httpx.MockTransport(bot)), dormir=lambda s: None)


def agente(cfg_completa, tmp_path, gateway, pronosticos, notif, accion_llm="MANTENER", nombre="BTCUSDT"):
    """Agente de BTC con tendencia al alza (cierre > SMA20) y pronósticos guionizados."""
    btc = activos_de(cfg_completa)[0]
    velas = generar_velas(tendencia=0.004, semilla=11)
    guion = iter(pronosticos)
    modelo = ModeloPronostico(btc["modelo"], raiz=tmp_path, funcion=lambda r: next(guion))
    gateway.accion = accion_llm
    a = Agente(btc, Base(tmp_path / f"{nombre}.sqlite3"), MercadoFalso(velas), modelo, crear_llm(gateway),
               reloj=lambda: velas[-1].close_time + 10 * 60_000, lock=threading.Lock(), notificador=notif)
    a.iniciar()
    return a, velas


def filas(a):
    return a.db.consultar("SELECT * FROM notificaciones ORDER BY id")


def test_compra_del_modelo_envia_un_whatsapp(cfg_completa, tmp_path, gateway):
    bot = CallMeBotFalso()
    a, velas = agente(cfg_completa, tmp_path, gateway, [0.01, 0.01], notificador(bot))
    r = a.ciclo_vivo()
    assert r["resultado"] == "completo" and r["decisiones"]["sin_llm"]["final"] == "COMPRAR"
    assert r["alerta"]["estado"] == "enviada" and len(bot.mensajes) == 1
    texto = bot.mensajes[0]["text"]
    assert "COMPRA" in texto and "BTCUSDT" in texto and velas[-1].fecha in texto and "Stop móvil sugerido" in texto
    assert "no envía órdenes" in texto
    f = filas(a)
    assert len(f) == 1 and f[0]["estado"] == "enviada" and f[0]["tipo"] == "compra" and f[0]["intentos"] == 1
    # la misma vela no se vuelve a procesar ni a avisar
    assert a.ciclo_vivo()["resultado"] == "duplicado" and len(bot.mensajes) == 1


def test_sin_senal_del_modelo_no_hay_aviso_aunque_el_llm_compre(cfg_completa, tmp_path, gateway):
    bot = CallMeBotFalso()
    a, _ = agente(cfg_completa, tmp_path, gateway, [-0.01], notificador(bot), accion_llm="COMPRAR")
    r = a.ciclo_vivo()
    assert r["decisiones"]["sin_llm"]["final"] == "MANTENER" and r["decisiones"]["con_llm"]["final"] == "COMPRAR"
    assert r["alerta"] is None and bot.mensajes == [] and filas(a) == []


def test_venta_por_senal_del_modelo_tambien_avisa(cfg_completa, tmp_path, gateway):
    bot = CallMeBotFalso()
    n = notificador(bot)
    a, velas = agente(cfg_completa, tmp_path, gateway, [0.01, -0.01], n)
    a._procesar("vivo", velas[:-1])                       # compra en la vela anterior (sin aviso: _procesar no notifica)
    r = a._procesar("vivo", velas)                        # el modelo pasa a efectivo: vende
    assert r["decisiones"]["sin_llm"]["final"] == "VENDER"
    out = notificar_ciclo(n, a.db, a.simbolo, a.dec, r)
    assert out["estado"] == "enviada" and out["tipo"] == "venta"
    assert "VENTA" in bot.mensajes[-1]["text"] and "señal del modelo" in bot.mensajes[-1]["text"]


def test_fallo_de_whatsapp_no_pausa_ni_cambia_el_ciclo(cfg_completa, tmp_path, gateway):
    for modo in ("caido", "error_http", "clave_mala"):
        bot = CallMeBotFalso(modo)
        a, _ = agente(cfg_completa, tmp_path / modo, gateway, [0.01], notificador(bot))
        r = a.ciclo_vivo()
        assert r["resultado"] == "completo" and r["alerta"]["estado"] == "fallida"
        assert a.db.estado()["estado"] == "corriendo"                       # el agente sigue
        assert len(bot.mensajes) == 2                                        # reintentos limitados
        assert a.db.carteras("vivo")["sin_llm"].en_posicion                  # la decisión se mantuvo
        ev = a.db.consultar("SELECT * FROM eventos WHERE tipo='notificacion_fallo'")
        assert len(ev) == 1
        f = filas(a)[0]
        assert f["estado"] == "fallida" and "987654" not in (f["detalle"] or "") and "+525512345678" not in (f["detalle"] or "")


def test_sin_credenciales_no_envia_y_lo_registra(cfg_completa, tmp_path, gateway):
    bot = CallMeBotFalso()
    n = notificador(bot, cred=None)
    assert n.estado()["estado"] == "sin_configurar" and not n.activo
    a, _ = agente(cfg_completa, tmp_path, gateway, [0.01], n)
    r = a.ciclo_vivo()
    assert r["resultado"] == "completo" and r["alerta"]["estado"] == "sin_configurar" and bot.mensajes == []


def test_deshabilitado_y_host_no_permitido():
    assert NotificadorWhatsApp({"habilitado": False}, CRED).estado()["estado"] == "deshabilitado"
    assert NotificadorWhatsApp(None, CRED).estado()["estado"] == "deshabilitado"
    for cfg in ({"habilitado": True, "proveedor": "callmebot", "url": "https://evil.example.com/whatsapp.php"},
                {"habilitado": True, "proveedor": "callmebot", "url": "http://api.callmebot.com/whatsapp.php"},
                {"habilitado": True, "proveedor": "meta", "url": "https://api.callmebot.com"},
                {"habilitado": True, "proveedor": "meta", "url": "https://graph.facebook.com.evil.com"},
                {"habilitado": True, "proveedor": "meta", "version_api": "../v1"},
                {"habilitado": True, "proveedor": "otro"}):
        with pytest.raises(ValueError):
            NotificadorWhatsApp(cfg, CRED)


def test_secretos_no_se_muestran():
    assert "987654" not in repr(CRED) and "12345678" not in repr(CRED)
    est = NotificadorWhatsApp(CFG_WA, CRED).estado()
    assert est["estado"] == "activo" and est["destino"].endswith("5678") and "55123" not in est["destino"]


def test_replay_nunca_envia(cfg_completa, tmp_path, gateway):
    bot = CallMeBotFalso()
    a, velas = agente(cfg_completa, tmp_path, gateway, [0.01], notificador(bot))
    r = a._procesar("replay", velas)
    assert notificar_ciclo(a.notificador, a.db, a.simbolo, a.dec, r) is None and bot.mensajes == []


def test_api_senales_sin_saldos_y_mensaje_de_prueba(cfg_completa, secretos, tmp_path, gateway):
    bot = CallMeBotFalso()
    a, _ = agente(cfg_completa, tmp_path, gateway, [0.01], notificador(bot))
    a.ciclo_vivo()
    with TestClient(crear_app(cfg_completa, secretos, agentes={"BTCUSDT": a}, programar=False)) as cli:
        assert cli.get("/api/senales").status_code == 401
        d = cli.get("/api/senales", headers=H).json()
        s = d["senales"][0]
        assert s["simbolo"] == "BTCUSDT" and s["accion"] == "COMPRAR" and s["senal_activa"] and s["alerta"]["estado"] == "enviada"
        assert d["avisos"]["estado"] == "activo"
        for clave in ("efectivo", "patrimonio", "saldo", "carteras"):
            assert clave not in s
        n = cli.get("/api/notificaciones", headers=H).json()
        assert len(n["alertas"]) == 1 and n["alertas"][0]["simbolo"] == "BTCUSDT"
        p = cli.post("/api/notificaciones/prueba", headers=H).json()
        assert p["enviado"] is True and "prueba" in bot.mensajes[-1]["text"]


def test_api_historial_senal_de_un_activo_sin_saldos(cfg_completa, secretos, tmp_path, gateway):
    """v2.2: la pestaña Señales muestra la historia de la señal del activo elegido."""
    a, _ = agente(cfg_completa, tmp_path, gateway, [0.01], notificador(CallMeBotFalso()))
    a.ciclo_vivo()
    with TestClient(crear_app(cfg_completa, secretos, agentes={"BTCUSDT": a}, programar=False)) as cli:
        assert cli.get("/api/historial_senal").status_code == 401
        d = cli.get("/api/historial_senal?simbolo=BTCUSDT", headers=H).json()
        assert d["simbolo"] == "BTCUSDT" and d["estrategia"] in ("C", "D") and len(d["filas"]) == 1
        f = d["filas"][0]
        assert f["accion"] == "COMPRAR" and f["pronostico"] > f["delta"] and f["aviso"]["estado"] == "enviada"
        assert f["vol20"] is not None and f["sma20"] is not None
        for clave in ("efectivo", "patrimonio", "saldo", "carteras"):
            assert clave not in f and clave not in d
        assert cli.get("/api/historial_senal?simbolo=BTCUSDT&modo=replay", headers=H).json()["filas"] == []


def test_api_prueba_sin_configurar_responde_409(cfg_completa, secretos, tmp_path, gateway):
    a, _ = agente(cfg_completa, tmp_path, gateway, [0.01], notificador(CallMeBotFalso(), cred=None))
    with TestClient(crear_app(cfg_completa, secretos, agentes={"BTCUSDT": a}, programar=False)) as cli:
        r = cli.post("/api/notificaciones/prueba", headers=H)
        assert r.status_code == 409 and "WHATSAPP_TELEFONO" in r.json()["detail"]


def test_config_real_usa_correo_y_deja_whatsapp_como_alternativa(cfg_completa):
    n = cfg_completa["notificaciones"]
    assert n["correo"]["habilitado"] is True and n["correo"]["smtp_host"] == "smtp.gmail.com" and n["correo"]["puerto"] == 465
    assert n["whatsapp"]["habilitado"] is False and n["whatsapp"]["proveedor"] == "meta"
    assert n["whatsapp"]["plantilla"]["nombre"] and n["whatsapp"]["plantilla"]["idioma"] == "es_MX"
    elegido = construir_notificador({**n, "correo": {**n["correo"]}})
    assert isinstance(elegido, NotificadorCorreo)
    assert isinstance(construir_notificador({**n, "correo": {**n["correo"], "habilitado": False},
                                             "whatsapp": {**n["whatsapp"], "habilitado": True}}), NotificadorWhatsApp)
    assert construir_notificador(None).estado()["estado"] == "deshabilitado"


# ---------------------------------------------------------------- Meta (WhatsApp Cloud API oficial)
def test_meta_envia_la_plantilla_con_los_datos_de_la_senal(cfg_completa, tmp_path, gateway):
    meta = MetaFalso()
    a, velas = agente(cfg_completa, tmp_path, gateway, [0.01], notificador(meta, CRED_META, CFG_META))
    r = a.ciclo_vivo()
    assert r["alerta"]["estado"] == "enviada" and len(meta.peticiones) == 1
    p = meta.peticiones[0]
    assert p["url"] == "https://graph.facebook.com/v25.0/1029384756/messages"
    assert p["auth"] == "Bearer EAAtokensecreto123"
    c = p["cuerpo"]
    assert c["messaging_product"] == "whatsapp" and c["to"] == "525512345678" and c["type"] == "template"
    assert c["template"]["name"] == "senal_laboratorio" and c["template"]["language"]["code"] == "es_MX"
    params = [x["text"] for x in c["template"]["components"][0]["parameters"]]
    assert params[0] == "COMPRA" and params[1] == "BTCUSDT" and params[2] == velas[-1].fecha
    assert params[6].startswith("Stop móvil sugerido") and all("\n" not in x for x in params) and len(params) == 7
    f = filas(a)[0]
    assert f["canal"] == "whatsapp:meta" and "EAAtoken" not in f["detalle"] and "1029384756" not in f["detalle"]


def test_meta_sin_plantilla_envia_texto(cfg_completa, tmp_path, gateway):
    meta = MetaFalso()
    cfg = {**CFG_META, "plantilla": None}
    a, _ = agente(cfg_completa, tmp_path, gateway, [0.01], notificador(meta, CRED_META, cfg))
    a.ciclo_vivo()
    c = meta.peticiones[0]["cuerpo"]
    assert c["type"] == "text" and "señal de COMPRA" in c["text"]["body"]


def test_meta_errores_de_configuracion_no_reintentan_y_no_filtran_secretos(cfg_completa, tmp_path, gateway):
    for modo, codigo in (("no_permitido", "131030"), ("token_vencido", "190")):
        meta = MetaFalso(modo)
        a, _ = agente(cfg_completa, tmp_path / modo, gateway, [0.01], notificador(meta, CRED_META, CFG_META))
        r = a.ciclo_vivo()
        assert r["resultado"] == "completo" and r["alerta"]["estado"] == "fallida" and len(meta.peticiones) == 1
        d = filas(a)[0]["detalle"]
        assert codigo in d and "EAAtokensecreto123" not in d and "5512345678" not in d
        assert a.db.estado()["estado"] == "corriendo"


def test_meta_caido_reintenta_y_sigue(cfg_completa, tmp_path, gateway):
    for modo in ("caido", "error_servidor"):
        meta = MetaFalso(modo)
        a, _ = agente(cfg_completa, tmp_path / modo, gateway, [0.01], notificador(meta, CRED_META, CFG_META))
        r = a.ciclo_vivo()
        assert r["alerta"]["estado"] == "fallida" and len(meta.peticiones) == 2 and a.db.estado()["estado"] == "corriendo"


def test_meta_mensaje_de_prueba_por_api(cfg_completa, secretos, tmp_path, gateway):
    meta = MetaFalso()
    a, _ = agente(cfg_completa, tmp_path, gateway, [0.01], notificador(meta, CRED_META, CFG_META))
    with TestClient(crear_app(cfg_completa, secretos, agentes={"BTCUSDT": a}, programar=False)) as cli:
        p = cli.post("/api/notificaciones/prueba", headers=H).json()
        assert p["enviado"] is True
        params = [x["text"] for x in meta.peticiones[-1]["cuerpo"]["template"]["components"][0]["parameters"]]
        assert params[1] == "LABORATORIO" and "prueba" in params[6]


def test_meta_plantilla_no_aprobada_se_envia_como_texto(cfg_completa, tmp_path, gateway):
    meta = MetaFalso("plantilla_pendiente")
    a, _ = agente(cfg_completa, tmp_path, gateway, [0.01], notificador(meta, CRED_META, CFG_META))
    r = a.ciclo_vivo()
    assert r["alerta"]["estado"] == "enviada" and len(meta.peticiones) == 2
    assert [p["cuerpo"]["type"] for p in meta.peticiones] == ["template", "text"]
    assert "132001" in filas(a)[0]["detalle"] and "como texto" in filas(a)[0]["detalle"]



# ---------------------------------------------------------------- correo (canal principal)
CRED_CORREO = CredencialesCorreo("laboratorio.dl@gmail.com", "abcdefghijklmnop", "destino.dl@gmail.com")
CFG_CORREO = {"habilitado": True, "smtp_host": "smtp.gmail.com", "puerto": 465, "reintentos": 2, "espera_inicial_s": 0}


class SMTPFalso:
    """Imita smtplib. modo: ok | auth (contraseña rechazada) | caido | destinatario"""

    def __init__(self, modo="ok"):
        self.modo = modo
        self.conexiones: list[tuple] = []
        self.logins: list[tuple] = []
        self.mensajes: list = []

    def __call__(self, host, puerto, timeout):
        self.conexiones.append((host, puerto))
        if self.modo == "caido":
            raise OSError("sin red")
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, u, p):
        self.logins.append((u, p))
        if self.modo == "auth":
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted abcdefghijklmnop")

    def send_message(self, m):
        if self.modo == "destinatario":
            raise smtplib.SMTPRecipientsRefused({"destino.dl@gmail.com": (550, b"no")})
        self.mensajes.append(m)


def correo(smtp, cred=CRED_CORREO, cfg=CFG_CORREO):
    return NotificadorCorreo(cfg, cred, smtp=smtp, dormir=lambda s: None)


def test_correo_compra_del_modelo(cfg_completa, tmp_path, gateway):
    smtp = SMTPFalso()
    a, velas = agente(cfg_completa, tmp_path, gateway, [0.01, 0.01], correo(smtp))
    r = a.ciclo_vivo()
    assert r["alerta"]["estado"] == "enviada" and len(smtp.mensajes) == 1
    assert smtp.conexiones == [("smtp.gmail.com", 465)] and smtp.logins == [("laboratorio.dl@gmail.com", "abcdefghijklmnop")]
    m = smtp.mensajes[0]
    assert m["Subject"] == f"Laboratorio DL · señal de COMPRA en BTCUSDT (vela {velas[-1].fecha})"
    assert m["From"] == "laboratorio.dl@gmail.com" and m["To"] == "destino.dl@gmail.com"
    cuerpo = m.get_content()
    assert "Stop móvil sugerido" in cuerpo and "*" not in cuerpo and "no envía órdenes" in cuerpo
    f = filas(a)[0]
    assert f["canal"] == "correo:smtp.gmail.com" and f["estado"] == "enviada"
    assert a.ciclo_vivo()["resultado"] == "duplicado" and len(smtp.mensajes) == 1


def test_correo_fallos_no_pausan_y_no_filtran_la_contrasena(cfg_completa, tmp_path, gateway):
    for modo, intentos in (("auth", 1), ("destinatario", 1), ("caido", 2)):
        smtp = SMTPFalso(modo)
        a, _ = agente(cfg_completa, tmp_path / modo, gateway, [0.01], correo(smtp))
        r = a.ciclo_vivo()
        assert r["resultado"] == "completo" and r["alerta"]["estado"] == "fallida" and a.db.estado()["estado"] == "corriendo"
        assert len(smtp.conexiones) == intentos
        f = filas(a)[0]
        assert "abcdefghijklmnop" not in f["detalle"] and "laboratorio.dl@" not in f["detalle"] and "destino.dl@" not in f["detalle"]
        assert len(a.db.consultar("SELECT * FROM eventos WHERE tipo='notificacion_fallo'")) == 1


def test_correo_servidor_no_permitido_y_secretos_ocultos():
    for cfg in ({"habilitado": True, "smtp_host": "smtp.evil.com", "puerto": 465},
                {"habilitado": True, "smtp_host": "smtp.gmail.com", "puerto": 25}):
        with pytest.raises(ValueError):
            NotificadorCorreo(cfg, CRED_CORREO)
    assert "abcdefghijklmnop" not in repr(CRED_CORREO) and "laboratorio.dl@" not in repr(CRED_CORREO)
    e = correo(SMTPFalso()).estado()
    assert e["estado"] == "activo" and e["canal"] == "correo" and e["destino"] == "de***@gmail.com"
    assert NotificadorCorreo(CFG_CORREO, None).estado()["estado"] == "sin_configurar"


def test_correo_credenciales_desde_el_entorno(monkeypatch):
    from app.notificaciones import credenciales_correo_desde_entorno
    monkeypatch.setenv("CORREO_USUARIO", "laboratorio.dl@gmail.com")
    monkeypatch.setenv("CORREO_CONTRASENA_APP", "abcd efgh\u00a0ijkl\u202fmnop")   # espacios normales y no separables
    monkeypatch.delenv("CORREO_DESTINO", raising=False)
    c = credenciales_correo_desde_entorno()
    assert c.contrasena == "abcdefghijklmnop" and c.destino == "laboratorio.dl@gmail.com"
    monkeypatch.setenv("CORREO_USUARIO", "")
    assert credenciales_correo_desde_entorno() is None


def test_correo_prueba_por_api(cfg_completa, secretos, tmp_path, gateway):
    smtp = SMTPFalso()
    a, _ = agente(cfg_completa, tmp_path, gateway, [0.01], correo(smtp))
    with TestClient(crear_app(cfg_completa, secretos, agentes={"BTCUSDT": a}, programar=False)) as cli:
        p = cli.post("/api/notificaciones/prueba", headers=H).json()
        assert p["enviado"] is True and smtp.mensajes[-1]["Subject"] == "Laboratorio DL · mensaje de prueba"
        assert cli.get("/api/senales", headers=H).json()["avisos"]["canal"] == "correo"
