"""Gateway privado de Ollama.

Ollama no exige autenticación por defecto; este servicio es la única puerta que usa el backend.
- Exige el encabezado X-API-Key (GATEWAY_API_KEY, guardado solo en .env del servidor).
- Rechaza claves ausentes o incorrectas con 401 y registra el intento (sin registrar la clave).
- Solo reenvía /api/chat a Ollama local, sin streaming y solo para los modelos permitidos.

Ejecutar (desde agente/backend):  uvicorn gateway.main:app --host 127.0.0.1 --port 8001
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import time
from pathlib import Path

import httpx
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request

from app.ajustes import AGENTE_DIR, cargar_env, leer_secreto

cargar_env()
log = logging.getLogger("gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

CAMPOS_PERMITIDOS = {"model", "messages", "tools", "format", "options", "keep_alive", "stream"}


def _modelos_permitidos() -> set[str]:
    try:
        cfg = json.loads((AGENTE_DIR / "config" / "agente.json").read_text())
        return {cfg["llm"]["modelo"]}
    except Exception:
        return {"llama3.2:3b"}


def crear_app(clave: str | None = None, ollama_url: str | None = None, http: httpx.Client | None = None) -> FastAPI:
    clave_esperada = clave if clave is not None else leer_secreto("GATEWAY_API_KEY")
    url = (ollama_url or os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
    cliente = http or httpx.Client(timeout=120)
    modelos = _modelos_permitidos()
    app = FastAPI(title="Gateway privado de Ollama", docs_url=None, redoc_url=None, openapi_url=None)

    def autenticar(request: Request, x_api_key: str | None = Header(default=None)) -> None:
        if not x_api_key:
            log.warning("Solicitud sin clave desde %s a %s", request.client.host if request.client else "?", request.url.path)
            raise HTTPException(401, "Falta la clave del gateway (X-API-Key).")
        if not hmac.compare_digest(x_api_key.encode(), clave_esperada.encode()):
            log.warning("Clave incorrecta desde %s a %s", request.client.host if request.client else "?", request.url.path)
            raise HTTPException(401, "Clave del gateway incorrecta.")

    @app.get("/salud", dependencies=[Depends(autenticar)])
    def salud():
        try:
            r = cliente.get(url + "/api/version", timeout=5)
            return {"ollama": "disponible", "version": r.json().get("version"), "url": url, "modelos_permitidos": sorted(modelos)}
        except httpx.HTTPError:
            raise HTTPException(502, "Ollama no está disponible en " + url)

    @app.post("/api/chat", dependencies=[Depends(autenticar)])
    def chat(cuerpo: dict = Body(...)):
        extra = set(cuerpo) - CAMPOS_PERMITIDOS
        if extra:
            raise HTTPException(400, f"Campos no permitidos: {sorted(extra)}")
        if cuerpo.get("model") not in modelos:
            raise HTTPException(403, f"Modelo no permitido. Permitidos: {sorted(modelos)}")
        cuerpo["stream"] = False
        t0 = time.perf_counter()
        try:
            r = cliente.post(url + "/api/chat", json=cuerpo)
        except httpx.HTTPError as e:
            log.error("Ollama no responde: %s", e.__class__.__name__)
            raise HTTPException(502, "Ollama no está disponible (¿está detenido?).")
        if r.status_code != 200:
            raise HTTPException(502, f"Ollama devolvió HTTP {r.status_code}: {r.text[:200]}")
        log.info("chat ok modelo=%s latencia=%.2fs", cuerpo.get("model"), time.perf_counter() - t0)
        return r.json()

    return app


def __getattr__(nombre):   # permite `uvicorn gateway.main:app` sin crear la app al importar en pruebas
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)
