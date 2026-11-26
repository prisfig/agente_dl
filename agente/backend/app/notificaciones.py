"""v2.0: avisos del laboratorio de señales (por correo; WhatsApp queda como alternativa).

Después de cada ciclo en vivo, si la estrategia del modelo (la cartera "sin_llm", tras pasar el motor de riesgo)
compra o vende, se envía un mensaje para que el usuario decida si opera a mano en MEXC. El laboratorio no envía
órdenes reales: el mensaje solo avisa.

Canal principal (config `notificaciones.correo`): correo por SMTP (Gmail con contraseña de aplicación).
  Secretos en .env: CORREO_USUARIO, CORREO_CONTRASENA_APP y, opcional, CORREO_DESTINO (por defecto, el mismo usuario).
  Solo se permiten servidores SMTP conocidos (smtp.gmail.com, smtp.office365.com) y siempre con TLS.

Alternativa por WhatsApp (config `notificaciones.whatsapp.proveedor`; deshabilitada por defecto):
- "meta": WhatsApp Cloud API oficial (graph.facebook.com), con el número de prueba gratuito de Meta. Fuera de la
  ventana de 24 h solo se pueden enviar plantillas aprobadas, así que, si hay plantilla configurada, el aviso
  se envía con ella; sin plantilla, o si Meta aún no la aprueba (errores 1320xx), se envía como texto (solo llega si el
  usuario escribió al número en las últimas 24 h).
  Secretos en .env: WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID y WHATSAPP_DESTINO.
- "callmebot": API gratuita de uso personal (api.callmebot.com). Secretos: WHATSAPP_TELEFONO y CALLMEBOT_APIKEY.

Reglas comunes:
- Los secretos solo viven en .env; nunca en el repositorio, en la interfaz ni en la bitácora (el teléfono se
  muestra enmascarado y la clave o el token se borran de cualquier respuesta guardada).
- Solo se habla con el host del proveedor, por HTTPS. Cualquier otro se rechaza.
- Un fallo al enviar no pausa el agente ni cambia ninguna decisión: se registra y el ciclo sigue.
- Cada aviso queda en la tabla `notificaciones` de la base del activo; (modo, fecha_vela, tipo) es único,
  así que un reinicio o un ciclo repetido no manda dos veces el mismo mensaje."""
from __future__ import annotations

import os
import re
import smtplib
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Callable
from urllib.parse import urlparse

import httpx

PROVEEDORES = {
    "meta": {"host": "graph.facebook.com", "url": "https://graph.facebook.com", "nombre": "WhatsApp Cloud API (Meta)"},
    "callmebot": {"host": "api.callmebot.com", "url": "https://api.callmebot.com/whatsapp.php", "nombre": "CallMeBot (WhatsApp)"},
}
TIPOS = {"COMPRAR": "compra", "VENDER": "venta"}
PALABRAS_DE_ERROR_CALLMEBOT = ("error", "invalid", "not allowed", "not registered", "blocked", "wrong", "full")


def enmascarar(telefono: str) -> str:
    t = telefono.strip()
    return t[:3] + "*" * max(len(t) - 7, 0) + t[-4:] if len(t) > 7 else "****"


@dataclass(frozen=True)
class CredencialesWhatsApp:
    destino: str              # teléfono que recibe los avisos (con código de país)
    clave: str                # token de Meta o apikey de CallMeBot
    phone_number_id: str = ""  # solo Meta: ID del número emisor (número de prueba)

    def __repr__(self) -> str:   # nunca imprimir el teléfono ni la clave
        return f"CredencialesWhatsApp({enmascarar(self.destino)}, ****)"


def credenciales_desde_entorno(proveedor: str) -> CredencialesWhatsApp | None:
    env = lambda k: os.environ.get(k, "").strip()
    if proveedor == "meta":
        dest, token, pid = env("WHATSAPP_DESTINO").replace(" ", ""), env("WHATSAPP_TOKEN"), env("WHATSAPP_PHONE_NUMBER_ID")
        return CredencialesWhatsApp(dest, token, pid) if dest and token and pid else None
    tel, clave = env("WHATSAPP_TELEFONO").replace(" ", ""), env("CALLMEBOT_APIKEY")
    return CredencialesWhatsApp(tel, clave) if tel and clave else None


class NotificadorWhatsApp:
    def __init__(self, cfg: dict | None, credenciales: CredencialesWhatsApp | None,
                 http: httpx.Client | None = None, dormir: Callable[[float], None] = time.sleep):
        cfg = cfg or {}
        self.habilitado_config = bool(cfg.get("habilitado", False))
        self.proveedor = cfg.get("proveedor", "meta").lower()
        if self.proveedor not in PROVEEDORES:
            raise ValueError(f"Proveedor de WhatsApp desconocido: {self.proveedor}")
        p = PROVEEDORES[self.proveedor]
        self.url = cfg.get("url", p["url"])
        u = urlparse(self.url)
        if u.scheme != "https" or u.hostname != p["host"]:
            raise ValueError(f"Host de notificaciones no permitido para {self.proveedor}: {self.url}")
        self.version_api = cfg.get("version_api", "v25.0")
        if not re.fullmatch(r"v\d+\.\d+", self.version_api):
            raise ValueError(f"version_api inválida: {self.version_api}")
        plantilla = cfg.get("plantilla") or {}
        self.plantilla = plantilla.get("nombre") or None
        self.idioma = plantilla.get("idioma", "es_MX")
        self.reintentos = int(cfg.get("reintentos", 2))
        self.espera_inicial_s = float(cfg.get("espera_inicial_s", 3.0))
        self.avisar_ventas = bool(cfg.get("avisar_ventas", True))
        self.cred = credenciales
        self.http = http or httpx.Client(timeout=float(cfg.get("timeout_s", 20.0)))
        self.dormir = dormir
        self.canal = f"whatsapp:{self.proveedor}"
        self.nombre_canal = "WhatsApp"

    # ------------------------------------------------------------------ estado
    @property
    def activo(self) -> bool:
        return self.habilitado_config and self.cred is not None

    def estado(self) -> dict:
        e = "deshabilitado" if not self.habilitado_config else ("sin_configurar" if self.cred is None else "activo")
        return {"estado": e, "proveedor": PROVEEDORES[self.proveedor]["nombre"],
                "destino": enmascarar(self.cred.destino) if self.cred else None,
                "formato": (f"plantilla «{self.plantilla}» ({self.idioma})" if self.plantilla else "texto")
                if self.proveedor == "meta" else "texto",
                "avisar_ventas": self.avisar_ventas,
                "disparador": "estrategia del modelo (cartera sin LLM) tras el motor de riesgo",
                "secretos_requeridos": (["WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_DESTINO"] if self.proveedor == "meta"
                                        else ["WHATSAPP_TELEFONO", "CALLMEBOT_APIKEY"])}

    # ------------------------------------------------------------------ envío
    def _limpiar(self, texto: str) -> str:
        if self.cred:
            for secreto in (self.cred.clave, self.cred.phone_number_id):
                if secreto:
                    texto = texto.replace(secreto, "****")
            digitos = re.sub(r"\D", "", self.cred.destino)
            texto = texto.replace(self.cred.destino, enmascarar(self.cred.destino))
            if digitos:
                texto = texto.replace(digitos, enmascarar(digitos))
        return " ".join(texto.split())[:300]

    def _peticion(self, texto: str, parametros: list[str] | None) -> httpx.Response:
        if self.proveedor == "callmebot":
            return self.http.get(self.url, params={"phone": self.cred.destino, "text": texto, "apikey": self.cred.clave})
        url = f"{self.url}/{self.version_api}/{self.cred.phone_number_id}/messages"
        cuerpo: dict = {"messaging_product": "whatsapp", "recipient_type": "individual",
                        "to": re.sub(r"[^\d]", "", self.cred.destino)}
        if self.plantilla and parametros is not None:
            cuerpo.update({"type": "template", "template": {
                "name": self.plantilla, "language": {"code": self.idioma},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in parametros]}]}})
        else:
            cuerpo.update({"type": "text", "text": {"preview_url": False, "body": texto}})
        return self.http.post(url, json=cuerpo, headers={"Authorization": f"Bearer {self.cred.clave}"})

    def _plantilla_no_disponible(self, r: httpx.Response) -> bool:
        """Errores 1320xx de Meta: plantilla inexistente, no aprobada, pausada o con otro idioma."""
        if self.proveedor != "meta" or not self.plantilla or not 400 <= r.status_code < 500:
            return False
        try:
            codigo = int((r.json().get("error") or {}).get("code", 0))
        except (ValueError, TypeError, AttributeError):
            return False
        return 132000 <= codigo <= 132099

    def _exito(self, r: httpx.Response) -> tuple[bool, str]:
        cuerpo = r.text or ""
        if self.proveedor == "callmebot":
            ok = r.status_code == 200 and not any(p in cuerpo.lower() for p in PALABRAS_DE_ERROR_CALLMEBOT)
            return ok, f"HTTP {r.status_code}: {cuerpo[:200]}"
        try:
            datos = r.json()
        except ValueError:
            datos = {}
        if r.status_code == 200 and datos.get("messages"):
            return True, f"HTTP 200: aceptado por Meta ({datos['messages'][0].get('id', '')[:24]}…)"
        err = datos.get("error", {}) if isinstance(datos, dict) else {}
        return False, f"HTTP {r.status_code}: código {err.get('code', '?')} · {err.get('message', cuerpo[:150])}"

    def enviar(self, texto: str, parametros: list[str] | None = None) -> tuple[bool, str, int]:
        """Devuelve (enviado, detalle sin secretos, intentos). `parametros` son los de la plantilla (solo Meta)."""
        if not self.activo:
            return False, "avisos " + self.estado()["estado"], 0
        detalle = ""
        for intento in range(1, self.reintentos + 1):
            try:
                r = self._peticion(texto, parametros)
                ok, detalle = self._exito(r)
                detalle = self._limpiar(detalle)
                if ok:
                    return True, detalle, intento
                if parametros is not None and self._plantilla_no_disponible(r):
                    # La plantilla aún no está aprobada (o no existe en ese idioma): se manda como texto.
                    # Llega si el usuario escribió al número de prueba en las últimas 24 h.
                    parametros = None
                    r = self._peticion(texto, None)
                    ok, d2 = self._exito(r)
                    detalle = self._limpiar(f"plantilla no disponible ({detalle}); como texto: {d2}")
                    if ok:
                        return True, detalle, intento
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    return False, detalle, intento     # error de configuración: reintentar no ayuda
            except httpx.HTTPError as e:
                detalle = f"sin conexión con {PROVEEDORES[self.proveedor]['host']}: {e.__class__.__name__}"
            if intento < self.reintentos:
                self.dormir(self.espera_inicial_s * 2 ** (intento - 1))
        return False, detalle, self.reintentos


# ---------------------------------------------------------------------------- correo (canal principal)
SERVIDORES_SMTP = {"smtp.gmail.com": (465, 587), "smtp.office365.com": (587,)}


def enmascarar_correo(c: str) -> str:
    usuario, _, dominio = c.strip().partition("@")
    return f"{usuario[:2]}***@{dominio}" if dominio else "****"


@dataclass(frozen=True)
class CredencialesCorreo:
    usuario: str      # cuenta que envía (p. ej., Gmail)
    contrasena: str   # contraseña de aplicación, no la contraseña normal
    destino: str      # quién recibe los avisos

    def __repr__(self) -> str:
        return f"CredencialesCorreo({enmascarar_correo(self.usuario)} → {enmascarar_correo(self.destino)}, ****)"


def credenciales_correo_desde_entorno() -> CredencialesCorreo | None:
    usuario = os.environ.get("CORREO_USUARIO", "").strip()
    # Gmail la muestra en bloques de 4; al copiarla pueden venir espacios normales o no separables: se quitan todos.
    clave = "".join(os.environ.get("CORREO_CONTRASENA_APP", "").split())
    destino = os.environ.get("CORREO_DESTINO", "").strip() or usuario
    if not usuario or not clave or "@" not in usuario or "@" not in destino:
        return None
    return CredencialesCorreo(usuario, clave, destino)


def _smtp_real(host: str, puerto: int, timeout: float):
    contexto = ssl.create_default_context()
    if puerto == 465:
        return smtplib.SMTP_SSL(host, puerto, timeout=timeout, context=contexto)
    s = smtplib.SMTP(host, puerto, timeout=timeout)
    s.starttls(context=contexto)
    return s


def _iniciar_sesion(s, usuario: str, contrasena: str) -> None:
    """Inicia sesión con AUTH LOGIN cuando el cliente es smtplib: con AUTH PLAIN, Gmail cierra la conexión ante una
    contraseña rechazada (SMTPServerDisconnected) en vez de responder 535, y el error no dice nada útil."""
    if hasattr(s, "auth_login") and hasattr(s, "auth"):
        s.ehlo_or_helo_if_needed()
        s.user, s.password = usuario, contrasena
        s.auth("LOGIN", s.auth_login, initial_response_ok=False)   # lanza SMTPAuthenticationError si no es 235
    else:
        s.login(usuario, contrasena)


class NotificadorCorreo:
    """Mismo contrato que NotificadorWhatsApp: activo, estado(), enviar(texto, parametros), avisar_ventas, canal."""

    def __init__(self, cfg: dict | None, credenciales: CredencialesCorreo | None,
                 smtp: Callable | None = None, dormir: Callable[[float], None] = time.sleep):
        cfg = cfg or {}
        self.habilitado_config = bool(cfg.get("habilitado", False))
        self.host = cfg.get("smtp_host", "smtp.gmail.com")
        self.puerto = int(cfg.get("puerto", 465))
        if self.host not in SERVIDORES_SMTP or self.puerto not in SERVIDORES_SMTP[self.host]:
            raise ValueError(f"Servidor SMTP no permitido: {self.host}:{self.puerto}")
        self.timeout_s = float(cfg.get("timeout_s", 20.0))
        self.reintentos = int(cfg.get("reintentos", 2))
        self.espera_inicial_s = float(cfg.get("espera_inicial_s", 3.0))
        self.avisar_ventas = bool(cfg.get("avisar_ventas", True))
        self.cred = credenciales
        self.smtp = smtp or _smtp_real
        self.dormir = dormir
        self.canal = f"correo:{self.host}"
        self.nombre_canal = "correo"

    @property
    def activo(self) -> bool:
        return self.habilitado_config and self.cred is not None

    def estado(self) -> dict:
        e = "deshabilitado" if not self.habilitado_config else ("sin_configurar" if self.cred is None else "activo")
        return {"estado": e, "canal": "correo", "proveedor": f"Correo ({self.host})",
                "destino": enmascarar_correo(self.cred.destino) if self.cred else None, "formato": "correo de texto",
                "avisar_ventas": self.avisar_ventas,
                "disparador": "estrategia del modelo (cartera sin LLM) tras el motor de riesgo",
                "secretos_requeridos": ["CORREO_USUARIO", "CORREO_CONTRASENA_APP", "CORREO_DESTINO (opcional)"]}

    def _limpiar(self, texto: str) -> str:
        if self.cred:
            texto = texto.replace(self.cred.contrasena, "****")
            for c in {self.cred.usuario, self.cred.destino}:
                texto = texto.replace(c, enmascarar_correo(c))
        return " ".join(str(texto).split())[:300]

    def _mensaje(self, texto: str, parametros: list[str] | None) -> EmailMessage:
        m = EmailMessage()
        if parametros and parametros[0] not in ("PRUEBA",):
            m["Subject"] = f"Laboratorio DL · señal de {parametros[0]} en {parametros[1]} (vela {parametros[2]})"
        else:
            m["Subject"] = "Laboratorio DL · mensaje de prueba"
        m["From"] = self.cred.usuario
        m["To"] = self.cred.destino
        m.set_content(texto.replace("*", ""))
        return m

    def enviar(self, texto: str, parametros: list[str] | None = None) -> tuple[bool, str, int]:
        if not self.activo:
            return False, "avisos " + self.estado()["estado"], 0
        detalle = ""
        for intento in range(1, self.reintentos + 1):
            try:
                with self.smtp(self.host, self.puerto, self.timeout_s) as s:
                    _iniciar_sesion(s, self.cred.usuario, self.cred.contrasena)
                    s.send_message(self._mensaje(texto, parametros))
                return True, f"aceptado por {self.host}", intento
            except smtplib.SMTPAuthenticationError as e:
                return False, self._limpiar(f"{self.host} rechazó el usuario o la contraseña de aplicación (código {e.smtp_code}). "
                                            "Revisa que la contraseña de aplicación sea de la misma cuenta que CORREO_USUARIO"), intento
            except smtplib.SMTPRecipientsRefused:
                return False, self._limpiar(f"{self.host} rechazó el destinatario"), intento
            except (smtplib.SMTPException, OSError) as e:
                detalle = self._limpiar(f"sin conexión con {self.host}:{self.puerto}: {e.__class__.__name__} ({e}). "
                                        "Si estás en una red de escuela o trabajo, puede bloquear el correo: prueba otra red "
                                        "o el puerto 587 en config/agente.json")
            if intento < self.reintentos:
                self.dormir(self.espera_inicial_s * 2 ** (intento - 1))
        return False, detalle, self.reintentos


def construir_notificador(cfg_notificaciones: dict | None):
    """El primer canal habilitado: correo (principal) o WhatsApp (alternativa). Sin ninguno: avisos deshabilitados."""
    n = cfg_notificaciones or {}
    correo, wa = n.get("correo"), n.get("whatsapp")
    if correo and correo.get("habilitado"):
        return NotificadorCorreo(correo, credenciales_correo_desde_entorno())
    if wa and wa.get("habilitado"):
        return NotificadorWhatsApp(wa, credenciales_desde_entorno(wa.get("proveedor", "meta")))
    return NotificadorCorreo(correo or {"habilitado": False}, None)


def _num(v, dec: int) -> str:
    return "—" if v is None else f"{v:,.{dec}f}"


def contenido_alerta(simbolo: str, tipo: str, fecha_vela: str, obs: dict, dec: int, stop: float | None,
                     motivo: str) -> tuple[str, list[str]]:
    """Texto libre del aviso y los 7 parámetros de la plantilla (una línea cada uno, sin saltos)."""
    pron, delta = obs.get("pronostico"), obs.get("delta")
    pron_txt = "—" if pron is None else f"{pron * 100:+.3f} %"
    delta_txt = "—" if delta is None else f"{delta * 100:.3f} %"
    extra = (f"Stop móvil sugerido: {_num(stop, dec)} USDT." if tipo == "compra" and stop
             else f"Motivo: {motivo}." if tipo == "venta" else "Sin stop sugerido.")
    etiqueta = "COMPRA" if tipo == "compra" else "VENTA" if tipo == "venta" else tipo.upper()
    params = [etiqueta, simbolo, fecha_vela, _num(obs.get("cierre"), dec), pron_txt, delta_txt, extra]
    texto = "\n".join([f"*Laboratorio DL · señal de {etiqueta}*", f"{simbolo} · vela {fecha_vela} (UTC)",
                       f"Cierre: {params[3]} USDT", f"Pronóstico del modelo: {pron_txt} (umbral {delta_txt})", extra,
                       "Operación manual opcional en MEXC. El laboratorio no envía órdenes."])
    return texto, params


def notificar_ciclo(notificador, db, simbolo: str, dec: int, r: dict) -> dict | None:
    """Llamada después de un ciclo en vivo completo. Nunca lanza excepciones hacia el ciclo."""
    if notificador is None or r.get("resultado") != "completo" or r.get("modo") != "vivo":
        return None
    d = r["decisiones"].get("sin_llm") or {}
    tipo = TIPOS.get(d.get("final"))
    if tipo is None or not d.get("aprobada", True) or (tipo == "venta" and not notificador.avisar_ventas):
        return None
    fecha = r["fecha_vela"]
    ya = db.consultar("SELECT estado FROM notificaciones WHERE modo='vivo' AND fecha_vela=? AND tipo=?", (fecha, tipo))
    if ya and ya[0]["estado"] == "enviada":
        return {"estado": "duplicada"}
    motivo = "señal del modelo" if d.get("propuesta") == "VENDER" else "stop móvil o control de riesgo"
    texto, params = contenido_alerta(simbolo, tipo, fecha, r.get("observacion", {}), dec,
                                     (r.get("stops") or {}).get("sin_llm"), motivo)
    try:
        if not notificador.activo:
            ok, detalle, intentos = False, "avisos " + notificador.estado()["estado"], 0
            estado = notificador.estado()["estado"]
        else:
            ok, detalle, intentos = notificador.enviar(texto, params)
            estado = "enviada" if ok else "fallida"
    except Exception as e:   # el aviso nunca debe romper el ciclo
        ok, detalle, intentos, estado = False, f"error inesperado: {e.__class__.__name__}", 0, "fallida"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.transaccion() as con:
        con.execute("INSERT INTO notificaciones (modo, fecha_vela, tipo, canal, estado, texto, intentos, detalle, ts_utc) "
                    "VALUES ('vivo',?,?,?,?,?,?,?,?) ON CONFLICT(modo, fecha_vela, tipo) DO UPDATE SET "
                    "estado=excluded.estado, texto=excluded.texto, intentos=notificaciones.intentos + excluded.intentos, "
                    "detalle=excluded.detalle, ts_utc=excluded.ts_utc",
                    (fecha, tipo, notificador.canal, estado, texto, intentos, detalle, ts))
        if estado == "enviada":
            db.evento("info", "notificacion", f"Aviso de {tipo} enviado por {notificador.nombre_canal} ({fecha}).", "vivo", con=con)
        elif estado == "fallida":
            db.evento("aviso", "notificacion_fallo", f"No se pudo enviar el aviso de {tipo} por {notificador.nombre_canal}: {detalle}. "
                      "El ciclo y sus decisiones no cambian.", "vivo", {"intentos": intentos}, con=con)
    return {"estado": estado, "tipo": tipo, "detalle": detalle}
