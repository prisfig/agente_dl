"""Persistencia en SQLite: velas procesadas (ciclos), decisiones, órdenes Paper, patrimonio, errores y estado.
Cada ciclo se guarda en una sola transacción y (modo, fecha_vela) es único: una vela nunca se procesa dos veces."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .paper import Cartera

ESQUEMA = """
CREATE TABLE IF NOT EXISTS estado_agente (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  estado TEXT NOT NULL,
  motivo TEXT,
  errores_consecutivos INTEGER NOT NULL DEFAULT 0,
  actualizado_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS carteras (
  modo TEXT NOT NULL, nombre TEXT NOT NULL,
  efectivo REAL NOT NULL, btc REAL NOT NULL,
  precio_entrada REAL, stop REAL, patrimonio_previo REAL,
  bloqueo_perdida INTEGER NOT NULL DEFAULT 0,
  actualizado_utc TEXT NOT NULL,
  PRIMARY KEY (modo, nombre)
);
CREATE TABLE IF NOT EXISTS ciclos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  modo TEXT NOT NULL, fecha_vela TEXT NOT NULL,
  inicio_utc TEXT NOT NULL, fin_utc TEXT NOT NULL,
  observacion TEXT NOT NULL,
  latencia_llm_s REAL, latencia_total_s REAL,
  modelo_llm TEXT, config_sha256 TEXT,
  UNIQUE (modo, fecha_vela)
);
CREATE TABLE IF NOT EXISTS decisiones (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ciclo_id INTEGER NOT NULL REFERENCES ciclos(id),
  modo TEXT NOT NULL, fecha_vela TEXT NOT NULL, cartera TEXT NOT NULL,
  propuesta TEXT NOT NULL, accion_final TEXT NOT NULL, aprobada INTEGER NOT NULL,
  motivos TEXT, justificacion TEXT, detalle_llm TEXT
);
CREATE TABLE IF NOT EXISTS ordenes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ciclo_id INTEGER REFERENCES ciclos(id),
  modo TEXT NOT NULL, fecha_vela TEXT NOT NULL, cartera TEXT NOT NULL,
  lado TEXT NOT NULL, estado TEXT NOT NULL,
  cantidad REAL, precio REAL, monto REAL, costo REAL, motivo TEXT, ts_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS patrimonio (
  modo TEXT NOT NULL, cartera TEXT NOT NULL, fecha_vela TEXT NOT NULL,
  efectivo REAL NOT NULL, btc REAL NOT NULL, precio REAL NOT NULL, patrimonio REAL NOT NULL,
  PRIMARY KEY (modo, cartera, fecha_vela)
);
CREATE TABLE IF NOT EXISTS notificaciones (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  modo TEXT NOT NULL, fecha_vela TEXT NOT NULL, tipo TEXT NOT NULL,
  canal TEXT NOT NULL, estado TEXT NOT NULL, texto TEXT NOT NULL,
  intentos INTEGER NOT NULL DEFAULT 0, detalle TEXT, ts_utc TEXT NOT NULL,
  UNIQUE (modo, fecha_vela, tipo)
);
CREATE TABLE IF NOT EXISTS eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL, modo TEXT, nivel TEXT NOT NULL, tipo TEXT NOT NULL,
  mensaje TEXT NOT NULL, detalle TEXT
);
"""


def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Base:
    def __init__(self, ruta: str | Path):
        self.ruta = str(ruta)
        if self.ruta != ":memory:":
            Path(self.ruta).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.ruta, check_same_thread=False, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA foreign_keys=ON")
        self.lock = threading.RLock()
        with self.lock:
            self.con.executescript(ESQUEMA)
            if not self.con.execute("SELECT 1 FROM estado_agente WHERE id = 1").fetchone():
                self.con.execute("INSERT INTO estado_agente VALUES (1, 'detenido', 'estado inicial', 0, ?)", (ahora_iso(),))

    # ---------- transacciones ----------
    def transaccion(self):
        base = self

        class _T:
            def __enter__(self_inner):
                base.lock.acquire()
                base.con.execute("BEGIN IMMEDIATE")
                return base.con

            def __exit__(self_inner, tipo, *_):
                try:
                    base.con.execute("ROLLBACK" if tipo else "COMMIT")
                finally:
                    base.lock.release()
                return False
        return _T()

    # ---------- estado ----------
    def estado(self) -> dict:
        with self.lock:
            return dict(self.con.execute("SELECT * FROM estado_agente WHERE id = 1").fetchone())

    def cambiar_estado(self, estado: str, motivo: str, errores: int | None = None) -> None:
        with self.lock:
            if errores is None:
                self.con.execute("UPDATE estado_agente SET estado=?, motivo=?, actualizado_utc=? WHERE id=1",
                                 (estado, motivo, ahora_iso()))
            else:
                self.con.execute("UPDATE estado_agente SET estado=?, motivo=?, errores_consecutivos=?, actualizado_utc=? WHERE id=1",
                                 (estado, motivo, errores, ahora_iso()))

    def sumar_error(self) -> int:
        with self.lock:
            self.con.execute("UPDATE estado_agente SET errores_consecutivos = errores_consecutivos + 1 WHERE id=1")
            return self.estado()["errores_consecutivos"]

    # ---------- eventos ----------
    def evento(self, nivel: str, tipo: str, mensaje: str, modo: str | None = None, detalle: dict | None = None,
               con: sqlite3.Connection | None = None) -> None:
        sql = "INSERT INTO eventos (ts_utc, modo, nivel, tipo, mensaje, detalle) VALUES (?,?,?,?,?,?)"
        args = (ahora_iso(), modo, nivel, tipo, mensaje, json.dumps(detalle, ensure_ascii=False, default=str) if detalle else None)
        if con is not None:
            con.execute(sql, args)
        else:
            with self.lock:
                self.con.execute(sql, args)

    # ---------- carteras ----------
    def carteras(self, modo: str) -> dict[str, Cartera]:
        with self.lock:
            filas = self.con.execute("SELECT * FROM carteras WHERE modo=?", (modo,)).fetchall()
        return {f["nombre"]: Cartera(f["nombre"], f["efectivo"], f["btc"], f["precio_entrada"], f["stop"],
                                     f["patrimonio_previo"], bool(f["bloqueo_perdida"])) for f in filas}

    def guardar_cartera(self, con: sqlite3.Connection, modo: str, c: Cartera) -> None:
        con.execute(
            "INSERT INTO carteras VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(modo, nombre) DO UPDATE SET "
            "efectivo=excluded.efectivo, btc=excluded.btc, precio_entrada=excluded.precio_entrada, stop=excluded.stop, "
            "patrimonio_previo=excluded.patrimonio_previo, bloqueo_perdida=excluded.bloqueo_perdida, actualizado_utc=excluded.actualizado_utc",
            (modo, c.nombre, c.efectivo, c.btc, c.precio_entrada, c.stop, c.patrimonio_previo, int(c.bloqueo_perdida), ahora_iso()))

    # ---------- ciclos ----------
    def ciclo_existe(self, modo: str, fecha_vela: str) -> bool:
        with self.lock:
            return self.con.execute("SELECT 1 FROM ciclos WHERE modo=? AND fecha_vela=?", (modo, fecha_vela)).fetchone() is not None

    def ultimo_ciclo(self, modo: str) -> dict | None:
        with self.lock:
            f = self.con.execute("SELECT * FROM ciclos WHERE modo=? ORDER BY fecha_vela DESC LIMIT 1", (modo,)).fetchone()
        if not f:
            return None
        d = dict(f)
        d["observacion"] = json.loads(d["observacion"])
        return d

    def consultar(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(f) for f in self.con.execute(sql, args).fetchall()]

    def borrar_modo(self, modo: str) -> None:
        """Solo para reiniciar un replay; nunca se usa con el modo en vivo."""
        if modo == "vivo":
            raise ValueError("El historial en vivo no se borra.")
        with self.transaccion() as con:
            for tabla in ("decisiones", "ordenes", "patrimonio", "carteras"):
                con.execute(f"DELETE FROM {tabla} WHERE modo=?", (modo,))
            con.execute("DELETE FROM ciclos WHERE modo=?", (modo,))
