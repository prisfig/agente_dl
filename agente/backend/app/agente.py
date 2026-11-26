"""Ciclo del agente: observar → pronosticar → proponer (LLM) → controles de riesgo → ejecutar en Paper → registrar.

Se llevan tres carteras con el mismo periodo, precios y costos (por activo; cada activo tiene su propia base SQLite):
  sin_llm            estrategia del modelo (C o D, la elegida con VA para ese activo) + motor de riesgo
  con_llm            propuesta del LLM + el mismo motor de riesgo
  comprar_y_mantener referencia pasiva (compra en el primer ciclo y no vende)
Los modos 'vivo' (conexión actual con MEXC) y 'replay' (repetición histórica) se guardan por separado."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone

from .db import Base
from .llm import ClienteLLM, ErrorLLM, herramientas_para
from .mexc import DIA_MS, ClienteMEXC, ErrorMercado, Vela, ahora_ms, verificar_antiguedad
from .modelo import ErrorDatos, ModeloPronostico, calcular_variables
from .paper import COMPRAR, MANTENER, VENDER, Cartera, MotorPaper, ResultadoOrden
from .riesgo import DecisionRiesgo, LimitesRiesgo, accion_estrategia, evaluar, nuevo_stop

CARTERAS = ("sin_llm", "con_llm", "comprar_y_mantener")
ERRORES_ESPERADOS = (ErrorMercado, ErrorLLM, ErrorDatos)


def acciones_validas(en_posicion: bool) -> list[str]:
    return [MANTENER, VENDER] if en_posicion else [COMPRAR, MANTENER]


class Agente:
    def __init__(self, cfg: dict, db: Base, mercado: ClienteMEXC, modelo: ModeloPronostico, llm: ClienteLLM,
                 reloj=ahora_ms, lock: threading.Lock | None = None):
        self.cfg = cfg
        self.simbolo = cfg["mercado"]["simbolo"]
        self.activo_base = cfg["mercado"].get("activo_base", "BTC")
        # v1.6: decimales de los precios en el texto para el LLM y en los motivos de riesgo. 2 por defecto
        # (BTC, ETH, SOL y XRP siguen igual); los activos que cotizan por debajo de ~1 USDT usan más (DOGE 0.05819).
        self.dec = int(cfg["mercado"].get("decimales_precio", 2))
        self.db = db
        self.mercado = mercado
        self.modelo = modelo
        self.llm = llm
        self.reloj = reloj
        self.limites = LimitesRiesgo.desde_config(cfg["riesgo"])
        self.reglas_par = mercado.reglas_par(cfg["mercado"]["reglas_par_respaldo"])
        p = cfg["paper"]
        self.paper = MotorPaper(self.reglas_par["paso_cantidad"], self.reglas_par["monto_minimo"],
                                p["costo_compra"], p["costo_venta"], p["deslizamiento"])
        # Con varios activos el candado es compartido: los ciclos corren uno tras otro y Ollama nunca recibe dos a la vez.
        self._lock = lock or threading.Lock()
        self.herramientas = herramientas_para(self.activo_base, modelo.estrategia)
        self.replay_estado: dict = {"en_curso": False}
        db.evento("info", "arranque", "Backend iniciado; estado recuperado de SQLite.", detalle={
            "version": cfg["version"], "simbolo": self.simbolo, "estado": db.estado(), "config_sha256": cfg["_sha256"], "reglas_par": self.reglas_par})

    # ------------------------------------------------------------------ control humano
    def iniciar(self) -> dict:
        self.db.cambiar_estado("corriendo", "iniciado por el usuario", errores=0)
        self.db.evento("info", "control", "Agente iniciado por el usuario.", "vivo")
        return self.db.estado()

    def pausar(self, motivo: str = "pausado por el usuario") -> dict:
        self.db.cambiar_estado("pausado", motivo)
        self.db.evento("info", "control", f"Agente pausado: {motivo}.", "vivo")
        return self.db.estado()

    def detener(self) -> dict:
        self.db.cambiar_estado("detenido", "detenido por el usuario: no se envían nuevas órdenes")
        carteras = {n: c.a_dict() for n, c in self.db.carteras("vivo").items()}
        self.db.evento("aviso", "control", "Agente detenido. Las posiciones se conservan (detener no liquida).", "vivo",
                       {"carteras": carteras})
        return self.db.estado()

    def rearmar_riesgo(self, modo: str = "vivo", origen: str = "activo", carteras_bloqueadas: list[str] | None = None) -> dict:
        """Quita el bloqueo de compras por pérdida diaria. origen: "activo" (botón del activo) o "rearmar_todos" (v1.9)."""
        with self.db.transaccion() as con:
            for c in self.db.carteras(modo).values():
                c.bloqueo_perdida = False
                self.db.guardar_cartera(con, modo, c)
            detalle = {"origen": origen}
            if carteras_bloqueadas is not None:
                detalle["carteras_bloqueadas"] = carteras_bloqueadas
            mensaje = ("El usuario rearmó el control de pérdida diaria (botón «Rearmar todos los bloqueados»)."
                       if origen == "rearmar_todos" else "El usuario rearmó el control de pérdida diaria.")
            self.db.evento("info", "control", mensaje, modo, detalle, con=con)
        return {"ok": True}

    def liquidar(self, modo: str = "vivo") -> dict:
        """Acción explícita: vende todas las posiciones al último cierre observado. Solo con el agente detenido o en pausa."""
        if modo == "vivo" and self.db.estado()["estado"] == "corriendo":
            raise ValueError("Primero pausa o detén el agente antes de liquidar.")
        ultimo = self.db.ultimo_ciclo(modo)
        if not ultimo:
            raise ValueError("No hay ciclos registrados: no hay precio de referencia.")
        precio, fecha = ultimo["observacion"]["cierre"], ultimo["fecha_vela"]
        vendidas = []
        with self.db.transaccion() as con:
            for c in self.db.carteras(modo).values():
                if c.en_posicion:
                    orden = self.paper.vender(c, precio)
                    self._guardar_orden(con, None, modo, fecha, c.nombre, orden, "liquidacion_manual")
                    self.db.guardar_cartera(con, modo, c)
                    vendidas.append(c.nombre)
            self.db.evento("aviso", "control", f"Liquidación manual al cierre {fecha} ({precio:,.{self.dec}f}).", modo,
                           {"carteras": vendidas}, con=con)
        return {"liquidadas": vendidas, "precio": precio, "fecha_vela": fecha}

    # ------------------------------------------------------------------ ciclo en vivo
    def ciclo_vivo(self, registrar_duplicado: bool = True) -> dict:
        estado = self.db.estado()
        if estado["estado"] != "corriendo":
            return {"resultado": "omitido", "motivo": f"El agente está {estado['estado']}: no se toman decisiones."}
        if not self._lock.acquire(blocking=False):
            return {"resultado": "omitido", "motivo": "Ya hay un ciclo en curso."}
        try:
            velas = self.mercado.velas_cerradas(self.cfg["mercado"]["velas_contexto"], ahora=self.reloj())
            if not velas:
                raise ErrorMercado("dato_invalido", "MEXC no devolvió velas cerradas.")
            horas = verificar_antiguedad(velas[-1], self.limites.antiguedad_maxima_horas, self.reloj())
            r = self._procesar("vivo", velas, registrar_duplicado, {"antiguedad_horas": round(horas, 2)})
            if r["resultado"] == "completo":
                self.db.cambiar_estado("corriendo", "ciclo completado", errores=0)
            return r
        except ERRORES_ESPERADOS as e:
            return self._fallo("vivo", e)
        finally:
            self._lock.release()

    def _fallo(self, modo: str, e: Exception) -> dict:
        tipo = getattr(e, "tipo", "dato_invalido")
        detalle = {"intentos": getattr(e, "intentos", None)}
        if getattr(e, "crudo", None):
            detalle["respuesta_cruda"] = e.crudo[:500]
        self.db.evento("error", tipo, str(e), modo, detalle)
        if modo == "vivo":
            n = self.db.sumar_error()
            self.db.cambiar_estado("pausado", f"Pausa automática por error ({tipo}). Revisa la bitácora y vuelve a iniciar.")
            return {"resultado": "error", "tipo": tipo, "mensaje": str(e), "errores_consecutivos": n}
        return {"resultado": "error", "tipo": tipo, "mensaje": str(e)}

    # ------------------------------------------------------------------ núcleo del ciclo
    def _procesar(self, modo: str, velas: list[Vela], registrar_duplicado: bool = True, extra: dict | None = None) -> dict:
        t0 = time.perf_counter()
        inicio = datetime.now(timezone.utc).isoformat(timespec="seconds")
        obs = calcular_variables(velas)
        fecha = obs.fecha_vela
        if self.db.ciclo_existe(modo, fecha):
            if registrar_duplicado:
                self.db.evento("aviso", "evento_duplicado",
                               f"La vela {fecha} ya fue procesada; no se repite ninguna operación.", modo)
            return {"resultado": "duplicado", "fecha_vela": fecha}

        self.modelo.completar(obs)
        precio = obs.cierre   # ejecución en la apertura de t+1, que en MEXC es igual al cierre de t
        carteras = self.db.carteras(modo)
        for nombre in CARTERAS:
            carteras.setdefault(nombre, Cartera(nombre, float(self.cfg["paper"]["capital_inicial"])))

        # Propuesta del LLM (si falla, el ciclo se aborta antes de escribir nada)
        c_llm = carteras["con_llm"]
        observacion_llm = self._observacion_llm(obs, c_llm, modo)
        res = self.llm.proponer(observacion_llm, self._datos_herramientas(obs, c_llm, modo), self.herramientas)

        registros = []
        for nombre in CARTERAS:
            c = carteras[nombre]
            patrimonio_actual = c.patrimonio(precio)
            if nombre == "comprar_y_mantener":
                prop = COMPRAR if not c.en_posicion else MANTENER
                dec = DecisionRiesgo(prop, prop, True, ["referencia pasiva: sin controles de riesgo"])
                exposicion = 1.0
            else:
                prop = accion_estrategia(obs.senal, c.en_posicion) if nombre == "sin_llm" else res.propuesta.accion
                dec = evaluar(prop, en_posicion=c.en_posicion, cierre=precio, stop=c.stop,
                              patrimonio_actual=patrimonio_actual, patrimonio_previo=c.patrimonio_previo,
                              bloqueo_vigente=c.bloqueo_perdida, limites=self.limites, decimales=self.dec)
                if dec.activa_bloqueo:
                    c.bloqueo_perdida = True
                exposicion = self.limites.exposicion_maxima

            orden: ResultadoOrden | None = None
            if dec.accion == COMPRAR:
                orden = self.paper.comprar(c, precio, exposicion)
            elif dec.accion == VENDER:
                orden = self.paper.vender(c, precio)
            if orden is not None and not orden.ejecutada:
                dec.motivos.append(f"orden_rechazada: {orden.motivo}")
                dec.accion, dec.aprobada = MANTENER, False

            if nombre != "comprar_y_mantener" and c.en_posicion:
                recien = orden is not None and orden.ejecutada and orden.lado == COMPRAR
                c.stop = nuevo_stop(c.stop, precio, obs.vol20, self.limites.stop_movil_k_vol, recien)
            c.patrimonio_previo = c.patrimonio(precio)
            registros.append((c, prop, dec, orden))

        latencia_total = time.perf_counter() - t0
        observacion_guardada = {**obs.a_dict(), **(extra or {}), "modo": modo, "version": self.cfg["version"]}
        try:
            with self.db.transaccion() as con:
                cur = con.execute(
                    "INSERT INTO ciclos (modo, fecha_vela, inicio_utc, fin_utc, observacion, latencia_llm_s, latencia_total_s, modelo_llm, config_sha256) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (modo, fecha, inicio, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     json.dumps(observacion_guardada), res.latencia_s, latencia_total, self.llm.modelo, self.cfg["_sha256"]))
                ciclo_id = cur.lastrowid
                for c, prop, dec, orden in registros:
                    es_llm = c.nombre == "con_llm"
                    con.execute(
                        "INSERT INTO decisiones (ciclo_id, modo, fecha_vela, cartera, propuesta, accion_final, aprobada, motivos, justificacion, detalle_llm) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (ciclo_id, modo, fecha, c.nombre, prop, dec.accion, int(dec.aprobada), json.dumps(dec.motivos, ensure_ascii=False),
                         res.propuesta.justificacion if es_llm else (f"Estrategia {obs.estrategia}: señal '{obs.senal}'" if c.nombre == "sin_llm" else "Comprar y mantener"),
                         json.dumps(res.detalle(), ensure_ascii=False) if es_llm else None))
                    if orden is not None:
                        self._guardar_orden(con, ciclo_id, modo, fecha, c.nombre, orden, None)
                        if not orden.ejecutada:
                            self.db.evento("aviso", "saldo_insuficiente" if "saldo" in orden.motivo else "orden_rechazada",
                                           f"Orden {orden.lado} rechazada en {c.nombre}: {orden.motivo}", modo, con=con)
                    if dec.activa_bloqueo:
                        self.db.evento("aviso", "limite_riesgo", f"{c.nombre}: {dec.motivos}", modo, con=con)
                    con.execute("INSERT INTO patrimonio VALUES (?,?,?,?,?,?,?)",
                                (modo, c.nombre, fecha, c.efectivo, c.btc, precio, c.patrimonio(precio)))
                    self.db.guardar_cartera(con, modo, c)
                self.db.evento("info", "ciclo", f"Ciclo {modo} {fecha} completo. LLM propuso {res.propuesta.accion}.", modo,
                               {"latencia_llm_s": round(res.latencia_s, 2), "latencia_total_s": round(latencia_total, 2)}, con=con)
        except sqlite3.IntegrityError:
            self.db.evento("aviso", "evento_duplicado", f"La vela {fecha} ya estaba registrada (carrera detectada); no se duplicó.", modo)
            return {"resultado": "duplicado", "fecha_vela": fecha}

        return {"resultado": "completo", "modo": modo, "simbolo": self.simbolo, "fecha_vela": fecha,
                "propuesta_llm": res.propuesta.accion, "justificacion": res.propuesta.justificacion,
                "decisiones": {c.nombre: {"propuesta": p, "final": d.accion, "aprobada": d.aprobada, "motivos": d.motivos}
                               for c, p, d, _ in registros},
                "latencia_llm_s": round(res.latencia_s, 2)}

    def _guardar_orden(self, con, ciclo_id, modo, fecha, cartera, orden: ResultadoOrden, motivo_extra):
        con.execute(
            "INSERT INTO ordenes (ciclo_id, modo, fecha_vela, cartera, lado, estado, cantidad, precio, monto, costo, motivo, ts_utc) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ciclo_id, modo, fecha, cartera, orden.lado, "ejecutada" if orden.ejecutada else "rechazada",
             orden.cantidad, orden.precio, orden.monto, orden.costo, motivo_extra or orden.motivo,
             datetime.now(timezone.utc).isoformat(timespec="seconds")))

    # ------------------------------------------------------------------ datos para el LLM
    def _indicadores_texto(self, obs) -> dict:
        """Valores ya formateados con su unidad y comparaciones precalculadas: un modelo de 3B
        confundía 0.1783 (en %) con 17.83 %. Los números siguen viniendo solo del backend.
        Para BTC (estrategia D) las claves y el texto son idénticos a los de la v1.0–v1.2."""
        return {
            "precio_cierre": f"{obs.cierre:.{self.dec}f} USDT",
            "pronostico_rendimiento_siguiente_dia": f"{obs.pronostico * 100:+.4f} %",
            "umbral_delta": f"{obs.delta * 100:.4f} %",
            "pronostico_supera_delta": "sí" if obs.pronostico > obs.delta else "no",
            "sma20": f"{obs.sma20:.{self.dec}f} USDT",
            "cierre_sobre_sma20": (f"sí (cierre {obs.cierre:.{self.dec}f} > SMA20 {obs.sma20:.{self.dec}f})" if obs.cierre_sobre_sma20
                                   else f"no (cierre {obs.cierre:.{self.dec}f} < SMA20 {obs.sma20:.{self.dec}f})"),
            "distancia_a_sma20": f"{obs.dist_sma20 * 100:+.3f} %",
            "volatilidad_20d": f"{obs.vol20 * 100:.3f} %",
            f"senal_estrategia_{obs.estrategia}": obs.senal,
        }

    def _observacion_llm(self, obs, c: Cartera, modo: str) -> dict:
        return {
            "simbolo": self.simbolo,
            "fecha_vela": obs.fecha_vela,
            **self._indicadores_texto(obs),
            "posicion": f"con posición en {self.activo_base}" if c.en_posicion else "en efectivo",
            "acciones_validas": acciones_validas(c.en_posicion),
            "stop_movil": f"{c.stop:.{self.dec}f} USDT" if c.stop else "sin stop (no hay posición)",
            "herramientas_disponibles": list(self.herramientas),
        }

    def _datos_herramientas(self, obs, c: Cartera, modo: str) -> dict:
        ultimas = self.db.consultar(
            "SELECT fecha_vela, accion_final, motivos FROM decisiones WHERE modo=? AND cartera='con_llm' ORDER BY fecha_vela DESC LIMIT 5", (modo,))
        return {
            "consultar_indicadores": self._indicadores_texto(obs),
            "consultar_cartera": {"efectivo": f"{c.efectivo:.2f} USDT", self.activo_base.lower(): f"{c.btc:.6f} {self.activo_base}", "en_posicion": c.en_posicion,
                                  "precio_entrada": f"{c.precio_entrada:.{self.dec}f} USDT" if c.precio_entrada else None,
                                  "stop_movil": f"{c.stop:.{self.dec}f} USDT" if c.stop else None,
                                  "acciones_validas": acciones_validas(c.en_posicion)},
            "consultar_ultimas_decisiones": ultimas,
        }

    # ------------------------------------------------------------------ replay histórico
    def replay(self, desde: str, hasta: str, reiniciar: bool = True) -> dict:
        """Repite velas históricas como ciclos marcados 'replay'. No toca el estado ni las carteras en vivo."""
        d0, d1 = date.fromisoformat(desde), date.fromisoformat(hasta)
        hoy = datetime.now(timezone.utc).date()
        if d1 < d0:
            raise ValueError("'hasta' debe ser posterior a 'desde'.")
        if d1 >= hoy:
            raise ValueError("El replay solo usa velas ya cerradas (anteriores a hoy UTC).")
        if self.replay_estado.get("en_curso"):
            raise ValueError("Ya hay un replay en curso.")
        fin_te = self.modelo.version.get("ultimo_objetivo_TE")
        if fin_te and desde <= fin_te:
            raise ValueError(f"El replay de {self.simbolo} debe empezar después de su conjunto de prueba "
                             f"(último objetivo de TE: {fin_te}); TE ya se usó una vez en el notebook.")
        inicio_ms = int(datetime(d0.year, d0.month, d0.day, tzinfo=timezone.utc).timestamp() * 1000) - 45 * DIA_MS
        fin_ms = int(datetime(d1.year, d1.month, d1.day, tzinfo=timezone.utc).timestamp() * 1000) + DIA_MS
        self.replay_estado = {"en_curso": True, "desde": desde, "hasta": hasta, "procesados": 0, "resultados": [], "error": None}
        try:
            velas = self.mercado.velas_rango(inicio_ms, fin_ms)
            if reiniciar:
                self.db.borrar_modo("replay")
            self.db.evento("info", "replay", f"Replay iniciado {desde} → {hasta} con datos históricos de MEXC.", "replay")
            for i, v in enumerate(velas):
                if not (desde <= v.fecha <= hasta):
                    continue
                with self._lock:
                    r = self._procesar("replay", velas[: i + 1], True, {"replay": True})
                self.replay_estado["procesados"] += 1
                self.replay_estado["resultados"].append({"fecha_vela": v.fecha, "resultado": r["resultado"],
                                                         "propuesta_llm": r.get("propuesta_llm")})
        except ERRORES_ESPERADOS as e:
            self.replay_estado["error"] = self._fallo("replay", e)
        finally:
            self.replay_estado["en_curso"] = False
        return self.replay_estado


class Programador(threading.Thread):
    """Revisa periódicamente si ya cerró una vela diaria no procesada y ejecuta el ciclo en vivo de cada activo,
    uno tras otro (en el orden de la configuración: BTC primero)."""

    def __init__(self, agentes: "Agente | list[Agente]", revision_s: int, minutos_tras_cierre: int):
        super().__init__(daemon=True, name="programador-agente")
        self.agentes = agentes if isinstance(agentes, list) else [agentes]
        self.agente = self.agentes[0]
        self.revision_s = revision_s
        self.minutos = minutos_tras_cierre
        self.parar = threading.Event()

    def vela_esperada(self, ahora: datetime | None = None) -> str:
        ahora = ahora or datetime.now(timezone.utc)
        return ((ahora - timedelta(minutes=self.minutos)).date() - timedelta(days=1)).isoformat()

    def proximo_ciclo(self, ahora: datetime | None = None) -> str:
        ahora = ahora or datetime.now(timezone.utc)
        hoy = datetime(ahora.year, ahora.month, ahora.day, tzinfo=timezone.utc) + timedelta(minutes=self.minutos)
        return (hoy if ahora < hoy else hoy + timedelta(days=1)).isoformat(timespec="minutes")

    def revisar_activo(self, agente: Agente) -> dict | None:
        if agente.db.estado()["estado"] != "corriendo":
            return None
        if agente.db.ciclo_existe("vivo", self.vela_esperada()):
            return None
        return agente.ciclo_vivo(registrar_duplicado=False)

    def revisar(self) -> dict:
        """Un error inesperado en un activo lo pausa solo a él; los demás siguen."""
        resultados = {}
        for agente in self.agentes:
            try:
                r = self.revisar_activo(agente)
            except Exception as e:   # el programador nunca debe morir en silencio
                agente.db.evento("error", "programador", f"Error inesperado: {e!r}", "vivo")
                agente.db.cambiar_estado("pausado", "Pausa automática por error inesperado del programador.")
                r = {"resultado": "error", "tipo": "programador", "mensaje": repr(e)}
            if r is not None:
                resultados[agente.simbolo] = r
        return resultados

    def run(self):
        while not self.parar.wait(self.revision_s):
            self.revisar()
