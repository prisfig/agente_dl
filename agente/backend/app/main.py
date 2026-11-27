"""API privada del agente (FastAPI). Todas las rutas, salvo /api/salud, exigen el encabezado X-API-Key.

Desde la v1.3 un mismo backend atiende varios activos (v1.6: 14 pares; lista en config/agente.json). Cada activo es un agente
independiente con su propia base SQLite, carteras, estado y control humano. Las rutas aceptan `?simbolo=ETHUSDT`;
sin ese parámetro se usa el activo principal (BTCUSDT), igual que en la v1.2.

Ejecutar (desde agente/backend):  uvicorn app.main:app --host 127.0.0.1 --port 8000
Documentación interactiva: http://127.0.0.1:8000/docs (también protegida por la clave para las llamadas)."""
from __future__ import annotations

import hmac
import json
import os
import platform
import resource
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agente import CARTERAS, Agente, Programador
from .ajustes import AGENTE_DIR, RAIZ, Secretos, activos_de, cargar_config, cargar_secretos
from .db import Base
from .llm import ClienteLLM
from .metricas import metricas
from .operaciones import CARTERAS as CARTERAS_OPERACIONES, comparacion_carteras, rearmar_bloqueados, resumen_operaciones
from .mexc import ClienteMEXC, ErrorMercado
from .modelo import ErrorDatos, ModeloPronostico, calcular_variables
from .notificaciones import construir_notificador as _construir_notificador, contenido_alerta
from .sugerencias import niveles_sugeridos

Modo = Literal["vivo", "replay"]


class SolicitudReplay(BaseModel):
    desde: str
    hasta: str
    reiniciar: bool = True


def construir_agente(cfg: dict, secretos: Secretos, db: Base | None = None, modelo: ModeloPronostico | None = None,
                     mercado: ClienteMEXC | None = None, llm: ClienteLLM | None = None,
                     lock: threading.Lock | None = None, notificador=None) -> Agente:
    m, l = cfg["mercado"], cfg["llm"]
    db = db or Base(RAIZ / cfg["base_datos"])
    mercado = mercado or ClienteMEXC(m["url_base"], m["simbolo"], m["intervalo"], m["reintentos"], m["espera_inicial_s"], m["timeout_s"])
    modelo = modelo or ModeloPronostico(cfg["modelo"])
    llm = llm or ClienteLLM(l["url_gateway"], secretos.gateway_api_key, l["modelo"], timeout_s=l["timeout_s"],
                            keep_alive=l["keep_alive"], temperatura=l["temperatura"], semilla=l["semilla"],
                            reintentos=l["reintentos"], espera_inicial_s=l["espera_inicial_s"],
                            max_llamadas_herramientas=l["max_llamadas_herramientas"],
                            max_tokens_respuesta=l.get("max_tokens_respuesta"),
                            opciones_extra=l.get("opciones_extra"))
    return Agente(cfg, db, mercado, modelo, llm, lock=lock, notificador=notificador)


def construir_notificador(cfg: dict):
    """v2.0: un solo notificador para todos los activos: correo (principal) o WhatsApp (alternativa).
    Sin la sección `notificaciones` (p. ej., las instancias de demostración) los avisos quedan deshabilitados."""
    return _construir_notificador(cfg.get("notificaciones"))


def construir_agentes(cfg: dict, secretos: Secretos) -> dict[str, Agente]:
    """Un agente por activo, en el orden de la configuración. Comparten el cliente del LLM, el notificador
    de avisos (v2.0) y un candado de ciclo."""
    lock = threading.Lock()
    agentes: dict[str, Agente] = {}
    llm = None
    notificador = construir_notificador(cfg)
    for c in activos_de(cfg):
        a = construir_agente(c, secretos, llm=llm, lock=lock, notificador=notificador)
        llm = a.llm
        agentes[a.simbolo] = a
    return agentes


def crear_app(cfg: dict | None = None, secretos: Secretos | None = None, agente: Agente | None = None,
              programar: bool = True, agentes: dict[str, Agente] | None = None) -> FastAPI:
    cfg = cfg or cargar_config()
    secretos = secretos or cargar_secretos()
    if agente is not None:
        agentes = {agente.simbolo: agente}

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        app.state.agentes = agentes or construir_agentes(cfg, secretos)
        app.state.agente = next(iter(app.state.agentes.values()))          # activo principal
        app.state.notificador = app.state.agente.notificador
        if app.state.notificador is not None:
            app.state.agente.db.evento("info", "notificacion", "Avisos por " + app.state.notificador.nombre_canal + ": "
                                       + app.state.notificador.estado()["estado"] + ".",
                                       detalle=app.state.notificador.estado())
        app.state.programador = Programador(list(app.state.agentes.values()), cfg["ciclo"]["revision_cada_s"],
                                            cfg["ciclo"]["minutos_tras_cierre"])
        if programar:
            app.state.programador.start()
        yield
        app.state.programador.parar.set()

    app = FastAPI(title="Agente DL para Finanzas — API privada", version=cfg["version"], lifespan=ciclo_de_vida)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST"], allow_headers=["X-API-Key", "Content-Type"])
    if (AGENTE_DIR / "frontend" / "dist").exists():   # versión compilada de la interfaz (npm run build)
        from fastapi.staticfiles import StaticFiles
        app.mount("/ui", StaticFiles(directory=AGENTE_DIR / "frontend" / "dist", html=True), name="ui")

    def autenticar(request: Request, x_api_key: str | None = Header(default=None)) -> None:
        if not x_api_key or not hmac.compare_digest(x_api_key.encode(), secretos.backend_api_key.encode()):
            ag: Agente | None = getattr(request.app.state, "agente", None)
            if ag is not None:
                ag.db.evento("aviso", "clave_incorrecta",
                             f"Acceso rechazado a {request.method} {request.url.path}: clave {'ausente' if not x_api_key else 'incorrecta'}.")
            raise HTTPException(401, "Clave de API ausente o incorrecta.")

    def ag(request: Request, simbolo: str | None = None) -> Agente:
        if not simbolo:
            return request.app.state.agente
        a = request.app.state.agentes.get(simbolo.upper())
        if a is None:
            raise HTTPException(404, f"Activo no configurado: {simbolo}. Disponibles: {', '.join(request.app.state.agentes)}.")
        return a

    def resumen_activo(a: Agente, modo: str = "vivo") -> dict:
        ultimo = a.db.ultimo_ciclo(modo)
        precio = ultimo["observacion"]["cierre"] if ultimo else None
        return {
            "simbolo": a.simbolo, "activo_base": a.activo_base, "estado": a.db.estado(),
            "estrategia": a.modelo.estrategia, "regla_estrategia": a.modelo.version.get("regla_estrategia"),
            "neuronas": a.modelo.version.get("neuronas"), "delta": a.modelo.delta,
            "ultima_vela": ultimo["fecha_vela"] if ultimo else None,
            "senal": (ultimo["observacion"].get("senal") or ultimo["observacion"].get("senal_d")) if ultimo else None,
            "pronostico": ultimo["observacion"].get("pronostico") if ultimo else None,
            "cierre": precio,
            "ciclos": a.db.consultar("SELECT COUNT(*) AS n FROM ciclos WHERE modo=?", (modo,))[0]["n"],
            "carteras": {n: (c.patrimonio(precio) if precio else c.efectivo) for n, c in a.db.carteras(modo).items()},
        }

    protegido = [Depends(autenticar)]

    @app.get("/api/salud")
    def salud():
        return {"ok": True}

    @app.get("/api/estado", dependencies=protegido)
    def estado(request: Request, simbolo: str | None = None, modo: Modo = "vivo"):
        a = ag(request, simbolo)
        ultimo = a.db.ultimo_ciclo(modo)
        decisiones = []
        if ultimo:
            decisiones = a.db.consultar("SELECT cartera, propuesta, accion_final, aprobada, motivos, justificacion FROM decisiones "
                                        "WHERE ciclo_id=?", (ultimo["id"],))
            for d in decisiones:
                d["motivos"] = json.loads(d["motivos"] or "[]")
        carteras = {}
        precio = ultimo["observacion"]["cierre"] if ultimo else None
        for n, c in a.db.carteras(modo).items():
            carteras[n] = {**c.a_dict(), "en_posicion": c.en_posicion,
                           "patrimonio": c.patrimonio(precio) if precio else c.efectivo}
        return {
            "version": cfg["version"],
            "demostracion": cfg.get("demostracion"),
            "agente": a.db.estado(),
            "modo": modo,
            "activo": a.simbolo,
            "activo_base": a.activo_base,
            "estrategia": a.modelo.estrategia,
            "activos": list(request.app.state.agentes),
            "ultimo_ciclo": ultimo,
            "decisiones": decisiones,
            "carteras": carteras,
            "riesgo": cfg["riesgo"],
            "paper": {k: v for k, v in cfg["paper"].items()},
            "reglas_par": a.reglas_par,
            "proximo_ciclo_utc": request.app.state.programador.proximo_ciclo(),
            "modelo": a.modelo.version,
            "base_datos": a.cfg["base_datos"],
            "llm": {"modelo": cfg["llm"]["modelo"], "gateway": cfg["llm"]["url_gateway"],
                    "max_tokens_respuesta": cfg["llm"].get("max_tokens_respuesta")},
            "config_sha256": cfg["_sha256"],
            "replay": {k: v for k, v in a.replay_estado.items() if k != "resultados"},
        }

    @app.get("/api/activos", dependencies=protegido)
    def activos(request: Request, modo: Modo = "vivo"):
        """Resumen de todos los activos (para el selector y la tabla multi-activo de la interfaz)."""
        return {"principal": request.app.state.agente.simbolo, "capital_inicial": cfg["paper"]["capital_inicial"],
                "activos": [resumen_activo(a, modo) for a in request.app.state.agentes.values()]}

    @app.post("/api/agente/iniciar", dependencies=protegido)
    def iniciar(request: Request, simbolo: str | None = None):
        return ag(request, simbolo).iniciar()

    @app.post("/api/agente/pausar", dependencies=protegido)
    def pausar(request: Request, simbolo: str | None = None):
        return ag(request, simbolo).pausar()

    @app.post("/api/agente/detener", dependencies=protegido)
    def detener(request: Request, simbolo: str | None = None):
        return ag(request, simbolo).detener()

    @app.post("/api/agente/liquidar", dependencies=protegido)
    def liquidar(request: Request, simbolo: str | None = None):
        try:
            return ag(request, simbolo).liquidar("vivo")
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/riesgo/rearmar", dependencies=protegido)
    def rearmar(request: Request, simbolo: str | None = None):
        return ag(request, simbolo).rearmar_riesgo("vivo")

    @app.post("/api/riesgo/rearmar_todos", dependencies=protegido)
    def rearmar_todos(request: Request):
        """v1.9: rearma todos los activos con el control de pérdida diaria activo (una acción del usuario)."""
        return rearmar_bloqueados(request.app.state.agentes)

    @app.post("/api/ciclo", dependencies=protegido)
    def ciclo(request: Request, simbolo: str | None = None):
        """Ejecuta ahora el ciclo en vivo (solo si el agente está corriendo). Si la vela ya se procesó, no repite nada."""
        return ag(request, simbolo).ciclo_vivo(registrar_duplicado=True)

    @app.post("/api/replay", dependencies=protegido)
    def replay(request: Request, s: SolicitudReplay, simbolo: str | None = None):
        a = ag(request, simbolo)
        if a.replay_estado.get("en_curso"):
            raise HTTPException(409, "Ya hay un replay en curso.")
        try:
            from datetime import date
            date.fromisoformat(s.desde), date.fromisoformat(s.hasta)
        except ValueError:
            raise HTTPException(422, "Fechas en formato AAAA-MM-DD.")

        def correr():
            try:
                a.replay(s.desde, s.hasta, s.reiniciar)
            except ValueError as e:
                a.replay_estado = {"en_curso": False, "error": {"mensaje": str(e)}}
        threading.Thread(target=correr, daemon=True, name="replay").start()
        return {"iniciado": True, "desde": s.desde, "hasta": s.hasta}

    @app.get("/api/replay", dependencies=protegido)
    def replay_estado(request: Request, simbolo: str | None = None):
        return ag(request, simbolo).replay_estado

    @app.get("/api/decisiones", dependencies=protegido)
    def decisiones(request: Request, simbolo: str | None = None, modo: Modo = "vivo", limite: int = Query(100, le=1000)):
        filas = ag(request, simbolo).db.consultar(
            "SELECT d.*, c.latencia_llm_s FROM decisiones d JOIN ciclos c ON c.id = d.ciclo_id WHERE d.modo=? "
            "ORDER BY d.fecha_vela DESC, d.cartera LIMIT ?", (modo, limite))
        for f in filas:
            f["motivos"] = json.loads(f["motivos"] or "[]")
            f["detalle_llm"] = json.loads(f["detalle_llm"]) if f["detalle_llm"] else None
        return filas

    @app.get("/api/ordenes", dependencies=protegido)
    def ordenes(request: Request, simbolo: str | None = None, modo: Modo = "vivo", limite: int = Query(200, le=2000)):
        return ag(request, simbolo).db.consultar("SELECT * FROM ordenes WHERE modo=? ORDER BY id DESC LIMIT ?", (modo, limite))

    @app.get("/api/patrimonio", dependencies=protegido)
    def patrimonio(request: Request, simbolo: str | None = None, modo: Modo = "vivo"):
        return ag(request, simbolo).db.consultar("SELECT * FROM patrimonio WHERE modo=? ORDER BY fecha_vela, cartera", (modo,))

    @app.get("/api/eventos", dependencies=protegido)
    def eventos(request: Request, simbolo: str | None = None, nivel: str | None = None, limite: int = Query(200, le=2000)):
        if nivel:
            filas = ag(request, simbolo).db.consultar("SELECT * FROM eventos WHERE nivel=? ORDER BY id DESC LIMIT ?", (nivel, limite))
        else:
            filas = ag(request, simbolo).db.consultar("SELECT * FROM eventos ORDER BY id DESC LIMIT ?", (limite,))
        for f in filas:
            f["detalle"] = json.loads(f["detalle"]) if f["detalle"] else None
        return filas

    @app.get("/api/metricas", dependencies=protegido)
    def metricas_api(request: Request, simbolo: str | None = None, modo: Modo = "vivo"):
        a = ag(request, simbolo)
        return {**metricas(a.db, modo, float(cfg["paper"]["capital_inicial"])), "simbolo": a.simbolo}

    # ------------------------------------------------------------------ vistas de la interfaz
    cache: dict[str, tuple[float, object]] = {}
    inicio_proceso = time.time()

    def en_cache(clave: str, ttl: float, funcion):
        ahora = time.time()
        if clave in cache and ahora - cache[clave][0] < ttl:
            return cache[clave][1]
        valor = funcion()
        cache[clave] = (ahora, valor)
        return valor

    @app.get("/api/mercado", dependencies=protegido)
    def mercado(request: Request, simbolo: str | None = None, modo: Modo = "vivo", limite: int = Query(90, ge=25, le=500)):
        a = ag(request, simbolo)
        try:
            velas = en_cache(f"velas{a.simbolo}{limite}", 60, lambda: a.mercado.velas_cerradas(limite))
        except ErrorMercado as e:
            raise HTTPException(502, f"MEXC: {e}")
        cierres = [v.close for v in velas]
        sma = [None if i < 19 else sum(cierres[i - 19:i + 1]) / 20 for i in range(len(cierres))]
        ordenes = a.db.consultar("SELECT fecha_vela, cartera, lado, precio, motivo FROM ordenes WHERE modo=? AND estado='ejecutada'", (modo,))
        stops = a.db.consultar("SELECT c.fecha_vela, d.cartera FROM ciclos c JOIN decisiones d ON d.ciclo_id=c.id WHERE c.modo=?", (modo,))
        return {"simbolo": a.simbolo, "activo_base": a.activo_base, "velas": [v.a_dict() for v in velas], "sma20": sma,
                "ordenes": ordenes, "carteras": {n: c.a_dict() for n, c in a.db.carteras(modo).items()},
                "ciclos": sorted({s["fecha_vela"] for s in stops})}

    @app.get("/api/operaciones", dependencies=protegido)
    def operaciones(request: Request, modo: Modo = "vivo", cartera: str = "con_llm"):
        """Posiciones abiertas, historial, saldo total y riesgo de una cartera, sumando todos los activos (v1.8)."""
        if cartera not in CARTERAS_OPERACIONES:
            raise HTTPException(422, f"Cartera desconocida: {cartera}. Opciones: {', '.join(CARTERAS_OPERACIONES)}.")
        agentes = request.app.state.agentes
        principal = request.app.state.agente
        try:
            precios = en_cache("precios_actuales", 30, lambda: principal.mercado.precios_actuales(list(agentes)))
            precios_ts = cache["precios_actuales"][0]
        except ErrorMercado:
            precios, precios_ts = {}, None
        capital = float(cfg["paper"]["capital_inicial"])
        r = resumen_operaciones(agentes, modo, cartera, capital, precios, principal.limites)
        r["comparacion"] = comparacion_carteras(agentes, modo, capital)
        r["precios_actuales_utc"] = (datetime.fromtimestamp(precios_ts, timezone.utc).isoformat(timespec="seconds")
                                     if precios_ts else None)
        r["paper"] = {k: v for k, v in cfg["paper"].items()}
        return r

    @app.get("/api/escaner", dependencies=protegido)
    def escaner(request: Request):
        a = request.app.state.agente
        operables = request.app.state.agentes

        def escanear():
            filas = []
            for s in cfg.get("escaner", {}).get("simbolos", list(operables)):
                fila = {"simbolo": s, "operable": s in operables}
                try:
                    t0 = time.perf_counter()
                    velas = a.mercado.para_simbolo(s).velas_cerradas(30)
                    fila["latencia_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                    obs = calcular_variables(velas)
                    previo = velas[-2].close
                    fila.update({"cierre": obs.cierre, "variacion_1d": obs.cierre / previo - 1, "sma20": obs.sma20,
                                 "cierre_sobre_sma20": obs.cierre_sobre_sma20, "dist_sma20": obs.dist_sma20,
                                 "vol20": obs.vol20, "ultima_vela": obs.fecha_vela, "velas": len(velas),
                                 "antiguedad_h": round((time.time() * 1000 - velas[-1].close_time) / 3_600_000, 1),
                                 "cierres": [v.close for v in velas[-30:]]})
                except (ErrorMercado, ErrorDatos) as e:
                    fila["error"] = str(e)
                filas.append(fila)
            return {"generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "nota": cfg.get("escaner", {}).get("nota", ""), "pares": filas}
        return en_cache("escaner", 300, escanear)

    @app.get("/api/red", dependencies=protegido)
    def red(request: Request, simbolo: str | None = None, modo: Modo = "vivo"):
        """Activaciones de las 3 LSTM para la entrada del último ciclo (o de la última vela si aún no hay ciclos)."""
        a = ag(request, simbolo)
        ultimo = a.db.ultimo_ciclo(modo)
        if ultimo:
            obs, origen = ultimo["observacion"], f"último ciclo {modo}"
        else:
            try:
                velas = en_cache(f"velas{a.simbolo}90", 60, lambda: a.mercado.velas_cerradas(90))
                obs, origen = a.modelo.completar(calcular_variables(velas)).a_dict(), "última vela cerrada (sin ciclo)"
            except (ErrorMercado, ErrorDatos) as e:
                raise HTTPException(502, str(e))
        try:
            act = a.modelo.activaciones(obs["rezagos"])
        except Exception as e:   # error con mensaje claro en vez de una respuesta 500 sin CORS
            raise HTTPException(500, f"No se pudieron calcular las activaciones: {e!r}")
        return {"origen": origen, "simbolo": a.simbolo, "fecha_vela": obs["fecha_vela"], "pronostico": obs.get("pronostico"),
                "delta": obs.get("delta"), "senal": obs.get("senal") or obs.get("senal_d"),
                "estrategia": obs.get("estrategia") or a.modelo.estrategia, "cierre_sobre_sma20": obs.get("cierre_sobre_sma20"),
                "modelo": a.modelo.version, "activaciones": act}

    @app.get("/api/sistema", dependencies=protegido)
    def sistema(request: Request, simbolo: str | None = None):
        a = ag(request, simbolo)

        def medir():
            try:
                lat_mexc = {"estado": "conectado", "latencia_ms": round(a.mercado.latencia_ms(), 1)}
            except ErrorMercado as e:
                lat_mexc = {"estado": "sin_conexion", "detalle": str(e)}
            memoria = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            memoria_mb = memoria / (1024 * 1024) if platform.system() == "Darwin" else memoria / 1024
            ruta_db = RAIZ / a.cfg["base_datos"]
            ciclos = a.db.consultar("SELECT modo, COUNT(*) AS n, AVG(latencia_llm_s) AS lat_llm, AVG(latencia_total_s) AS lat_total "
                                    "FROM ciclos GROUP BY modo")
            return {
                "mexc": lat_mexc,
                "llm": a.llm.salud(),
                "proceso": {"memoria_max_mb": round(memoria_mb, 1), "hilos": threading.active_count(),
                            "activo_desde_s": round(time.time() - inicio_proceso), "pid": os.getpid()},
                "programador": {"vivo": request.app.state.programador.is_alive(),
                                "revision_cada_s": cfg["ciclo"]["revision_cada_s"],
                                "proximo_ciclo_utc": request.app.state.programador.proximo_ciclo()},
                "base_datos": {"ruta": str(ruta_db.relative_to(RAIZ)) if ruta_db.is_relative_to(RAIZ) else str(ruta_db),
                               "tamano_kb": round(ruta_db.stat().st_size / 1024, 1) if ruta_db.exists() else 0},
                "ciclos": ciclos,
                "equipo": {"sistema": platform.platform(), "procesador": platform.machine(), "python": platform.python_version(),
                           "cpus": os.cpu_count()},
                "modelo": a.modelo.version,
                "simbolo": a.simbolo,
                "activos": {s_: {"estado": x.db.estado()["estado"],
                                 "ciclos_vivo": x.db.consultar("SELECT COUNT(*) AS n FROM ciclos WHERE modo='vivo'")[0]["n"]}
                            for s_, x in request.app.state.agentes.items()},
                "config_sha256": cfg["_sha256"],
                "medido_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        return en_cache(f"sistema{a.simbolo}", 10, medir)

    @app.get("/api/evidencia", dependencies=protegido)
    def evidencia(request: Request, simbolo: str | None = None):
        a = ag(request, simbolo)
        ruta = RAIZ / a.cfg["modelo"].get("verificacion_local", "")
        archivos = sorted(p.name for p in (AGENTE_DIR / "evidencia").glob("*")) if (AGENTE_DIR / "evidencia").exists() else []
        verif = json.loads(ruta.read_text()) if ruta.is_file() else None
        if verif and "activos" in verif:       # reporte conjunto de los activos extra: solo la parte de este activo
            comun = {k: v for k, v in verif.items() if k != "activos"}
            verif = {**comun, **verif["activos"][a.simbolo]} if a.simbolo in verif["activos"] else None
        return {"simbolo": a.simbolo, "verificacion_modelo": verif, "archivos": archivos}

    # ------------------------------------------------------------------ v2.0: laboratorio de señales y alertas
    @app.get("/api/senales", dependencies=protegido)
    def senales(request: Request):
        """Señal del modelo de cada activo en su último ciclo en vivo y el aviso (correo) de esa vela.
        Sin saldos: el laboratorio no compra; la simulación Paper sigue por dentro solo como evaluación."""
        filas = []
        for a in request.app.state.agentes.values():
            ultimo = a.db.ultimo_ciclo("vivo")
            fila = {"simbolo": a.simbolo, "estado": a.db.estado()["estado"], "estrategia": a.modelo.estrategia,
                    "delta": a.modelo.delta, "decimales": a.dec}
            if ultimo:
                o = ultimo["observacion"]
                dec = a.db.consultar("SELECT propuesta, accion_final, motivos FROM decisiones WHERE ciclo_id=? AND cartera='sin_llm'",
                                     (ultimo["id"],))
                c = a.db.carteras("vivo").get("sin_llm")
                alerta = a.db.consultar("SELECT tipo, estado, ts_utc FROM notificaciones WHERE modo='vivo' AND fecha_vela=? "
                                        "ORDER BY id DESC LIMIT 1", (ultimo["fecha_vela"],))
                fila.update({
                    "fecha_vela": ultimo["fecha_vela"], "cierre": o.get("cierre"), "pronostico": o.get("pronostico"),
                    "senal": o.get("senal") or o.get("senal_d"), "cierre_sobre_sma20": o.get("cierre_sobre_sma20"),
                    "dist_sma20": o.get("dist_sma20"),
                    "accion": dec[0]["accion_final"] if dec else None,
                    "motivos": json.loads(dec[0]["motivos"] or "[]") if dec else [],
                    "senal_activa": bool(c and c.en_posicion),
                    "precio_entrada": c.precio_entrada if c and c.en_posicion else None,
                    "stop": c.stop if c and c.en_posicion else None,
                    "alerta": alerta[0] if alerta else None,
                    # v2.3: stop, take profit y tamaño sugeridos para la compra manual (no cambian decisiones)
                    "sugerencia": niveles_sugeridos(a.cfg.get("sugerencias"), a.simbolo, o.get("cierre"), o.get("vol20"),
                                                    a.limites.stop_movil_k_vol),
                })
            filas.append(fila)
        notif = getattr(request.app.state, "notificador", None)
        return {"senales": filas, "avisos": notif.estado() if notif else {"estado": "deshabilitado"},
                "proximo_ciclo_utc": request.app.state.programador.proximo_ciclo()}

    @app.get("/api/historial_senal", dependencies=protegido)
    def historial_senal(request: Request, simbolo: str | None = None, modo: Modo = "vivo", limite: int = Query(60, ge=1, le=500)):
        """v2.2: la señal del modelo de UN activo en cada ciclo (pronóstico frente a δ, tendencia, volatilidad, acción y aviso).
        Solo lectura y sin saldos: es la historia de la señal, no de una cuenta."""
        a = ag(request, simbolo)
        ciclos = a.db.consultar("SELECT id, fecha_vela, observacion FROM ciclos WHERE modo=? ORDER BY fecha_vela DESC LIMIT ?",
                                (modo, limite))
        filas = []
        for c in reversed(ciclos):
            o = json.loads(c["observacion"])
            dec = a.db.consultar("SELECT accion_final, motivos FROM decisiones WHERE ciclo_id=? AND cartera='sin_llm'", (c["id"],))
            aviso = a.db.consultar("SELECT tipo, estado FROM notificaciones WHERE modo=? AND fecha_vela=? ORDER BY id DESC LIMIT 1",
                                   (modo, c["fecha_vela"]))
            filas.append({"fecha_vela": c["fecha_vela"], "cierre": o.get("cierre"), "pronostico": o.get("pronostico"),
                          "delta": o.get("delta", a.modelo.delta), "senal": o.get("senal") or o.get("senal_d"),
                          "sma20": o.get("sma20"), "dist_sma20": o.get("dist_sma20"), "vol20": o.get("vol20"),
                          "accion": dec[0]["accion_final"] if dec else None,
                          "motivos": json.loads(dec[0]["motivos"] or "[]") if dec else [],
                          "aviso": aviso[0] if aviso else None})
        return {"simbolo": a.simbolo, "estrategia": a.modelo.estrategia, "delta": a.modelo.delta, "decimales": a.dec, "filas": filas}

    @app.get("/api/notificaciones", dependencies=protegido)
    def notificaciones(request: Request, limite: int = Query(100, le=1000)):
        filas = []
        for a in request.app.state.agentes.values():
            for f in a.db.consultar("SELECT * FROM notificaciones ORDER BY id DESC LIMIT ?", (limite,)):
                filas.append({"simbolo": a.simbolo, **f})
        filas.sort(key=lambda f: (f["ts_utc"], f["simbolo"]), reverse=True)
        notif = getattr(request.app.state, "notificador", None)
        return {"avisos": notif.estado() if notif else {"estado": "deshabilitado"}, "alertas": filas[:limite]}

    @app.post("/api/notificaciones/prueba", dependencies=protegido)
    def notificacion_prueba(request: Request):
        """Envía un aviso de prueba por el canal configurado (no corresponde a ninguna señal real)."""
        notif = getattr(request.app.state, "notificador", None)
        if notif is None or not notif.activo:
            estado = notif.estado()["estado"] if notif else "deshabilitado"
            faltan = ", ".join(notif.estado()["secretos_requeridos"]) if notif else "los datos del canal de avisos"
            raise HTTPException(409, f"Avisos {estado}: revisa {faltan} en .env "
                                     "y la sección notificaciones de la configuración.")
        hoy = datetime.now(timezone.utc).date().isoformat()
        texto, params = contenido_alerta("LABORATORIO", "prueba", hoy, {}, 2, None, "")
        texto = texto.replace("señal de PRUEBA", "mensaje de prueba")
        params[-1] = "Mensaje de prueba: los avisos funcionan."
        ok, detalle, intentos = notif.enviar(texto, params)
        request.app.state.agente.db.evento("info" if ok else "aviso", "notificacion_prueba",
                                           f"Aviso de prueba por {notif.nombre_canal}: {'enviado' if ok else 'falló'} ({detalle}).",
                                           detalle={"intentos": intentos})
        return {"enviado": ok, "detalle": detalle, "intentos": intentos}

    @app.get("/api/config", dependencies=protegido)
    def config():
        """Solo lectura. La configuración se cambia editando config/agente.json con el backend apagado."""
        return {k: v for k, v in cfg.items() if not k.startswith("_")} | {"sha256": cfg["_sha256"]}

    return app


def __getattr__(nombre):   # `uvicorn app.main:app`
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)
