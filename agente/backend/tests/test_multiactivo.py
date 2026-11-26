"""v1.3–v1.7: varios activos (BTC, ETH, SOL, XRP, diez más en la v1.6 y DOT en la v1.7), cada uno con su propio modelo, estrategia (C o D), base SQLite y control."""
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.agente import Agente, Programador
from app.ajustes import RAIZ, ErrorConfiguracion, activos_de, validar_config
from app.db import Base
from app.llm import HERRAMIENTAS, herramientas_para
from app.main import crear_app
from app.modelo import ErrorModelo, ModeloPronostico, calcular_variables, senal_estrategia
from tests.conftest import CLAVE_BACKEND, MercadoFalso, crear_llm, generar_velas

H = {"X-API-Key": CLAVE_BACKEND}


def config_congelada(tmp_path: Path, cfg_activo: dict, estrategia: str, delta: float, **extra) -> None:
    ruta = tmp_path / cfg_activo["modelo"]["config_congelada"]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"estrategia": estrategia, "delta": delta, "neuronas": 10, "semillas": [42, 123, 2024], **extra}))


def agente_de(cfg_activo, tmp_path, gateway, velas=None, pronostico=0.002, lock=None, nombre_db=None):
    mercado = MercadoFalso(velas or generar_velas())
    modelo = ModeloPronostico(cfg_activo["modelo"], raiz=tmp_path, funcion=lambda r: pronostico)
    ahora = mercado.velas[-1].close_time + 10 * 60_000
    db = Base(tmp_path / (nombre_db or f"{cfg_activo['mercado']['simbolo']}.sqlite3"))
    return Agente(cfg_activo, db, mercado, modelo, crear_llm(gateway), reloj=lambda: ahora, lock=lock)


# ---------- configuración ----------
def test_config_quince_activos_btc_sin_cambios(cfg_completa):
    activos = activos_de(cfg_completa)
    assert [a["mercado"]["simbolo"] for a in activos] == ["BTCUSDT", *["ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT", "LTCUSDT", "TRXUSDT", "DOGEUSDT", "MXUSDT", "FILUSDT", "BCHUSDT", "ZECUSDT", "NEARUSDT", "DOTUSDT"]]
    assert "GOLD(PAXG)USDT" not in {a["mercado"]["simbolo"] for a in activos}      # excluido en la v1.6 (respaldado por oro)
    btc = activos[0]
    assert btc["base_datos"] == "agente/datos/agente.sqlite3"                      # la base de los ciclos en vivo de BTC
    assert btc["modelo"]["config_congelada"] == "resultados/configuracion_final_congelada.json"
    assert len({a["base_datos"] for a in activos}) == 15
    assert [a["mercado"]["decimales_precio"] for a in activos[:4]] == [2, 2, 2, 2]     # los cuatro anteriores no cambian
    assert all(a["riesgo"] == cfg_completa["riesgo"] and a["paper"] == cfg_completa["paper"] for a in activos)
    assert cfg_completa["version"] == "2.0"


def test_config_sin_activos_se_usa_tal_cual(cfg):
    assert activos_de(cfg) == [cfg]          # configuraciones de demostración (un solo activo)


def test_config_rechaza_simbolo_repetido_o_base_compartida(cfg_completa):
    mala = json.loads(json.dumps(cfg_completa))
    mala["activos"][1]["simbolo"] = "BTCUSDT"
    with pytest.raises(ErrorConfiguracion, match="repetidos"):
        validar_config(mala)
    mala = json.loads(json.dumps(cfg_completa))
    mala["activos"][2]["base_datos"] = mala["activos"][0]["base_datos"]
    with pytest.raises(ErrorConfiguracion, match="propia base"):
        validar_config(mala)


# ---------- estrategias C y D ----------
def test_senal_c_ignora_sma20_y_d_la_exige():
    assert senal_estrategia("C", 0.01, 0.004, cierre_sobre_sma20=False) == "comprar"
    assert senal_estrategia("D", 0.01, 0.004, cierre_sobre_sma20=False) == "efectivo"
    assert senal_estrategia("D", 0.01, 0.004, cierre_sobre_sma20=True) == "comprar"
    assert senal_estrategia("C", 0.003, 0.004, cierre_sobre_sma20=True) == "efectivo"


def test_agente_eth_estrategia_c_compra_bajo_sma20(cfg_completa, tmp_path, gateway):
    eth = activos_de(cfg_completa)[1]
    config_congelada(tmp_path, eth, "C", 0.004315)
    velas = generar_velas(tendencia=-0.01, semilla=3)
    a = agente_de(eth, tmp_path, gateway, velas=velas, pronostico=0.006)
    obs = calcular_variables(velas)
    assert not obs.cierre_sobre_sma20
    a.iniciar()
    r = a.ciclo_vivo()
    assert r["resultado"] == "completo" and r["simbolo"] == "ETHUSDT"
    assert r["decisiones"]["sin_llm"]["propuesta"] == "COMPRAR"                   # con D habría quedado en efectivo
    guardada = a.db.ultimo_ciclo("vivo")["observacion"]
    assert guardada["estrategia"] == "C" and guardada["senal"] == "comprar" and "senal_d" not in guardada
    d = a.db.consultar("SELECT justificacion FROM decisiones WHERE cartera='sin_llm'")[0]
    assert d["justificacion"] == "Estrategia C: señal 'comprar'"


def test_llm_de_eth_recibe_eth_y_estrategia_c(cfg_completa, tmp_path, gateway):
    eth = activos_de(cfg_completa)[1]
    config_congelada(tmp_path, eth, "C", 0.004315)
    a = agente_de(eth, tmp_path, gateway)
    a.iniciar()
    a.ciclo_vivo()
    fase1 = next(c for c in gateway.llamadas if "tools" in c)
    datos = json.loads(fase1["messages"][1]["content"].split("\n", 1)[1])
    assert datos["simbolo"] == "ETHUSDT" and "senal_estrategia_C" in datos and "senal_estrategia_D" not in datos
    descripciones = {t["function"]["name"]: t["function"]["description"] for t in fase1["tools"]}
    assert "estrategia C" in descripciones["consultar_indicadores"]
    assert "efectivo, ETH," in descripciones["consultar_cartera"]


def test_btc_el_llm_recibe_lo_mismo_que_en_v12(construir, gateway):
    """Para BTC (estrategia D) las claves, textos y herramientas que ve el LLM no cambian respecto de la v1.2."""
    assert herramientas_para("BTC", "D") == HERRAMIENTAS
    a = construir()
    a.iniciar()
    a.ciclo_vivo()
    fase1 = next(c for c in gateway.llamadas if "tools" in c)
    datos = json.loads(fase1["messages"][1]["content"].split("\n", 1)[1])
    assert list(datos) == ["simbolo", "fecha_vela", "precio_cierre", "pronostico_rendimiento_siguiente_dia", "umbral_delta",
                           "pronostico_supera_delta", "sma20", "cierre_sobre_sma20", "distancia_a_sma20", "volatilidad_20d",
                           "senal_estrategia_D", "posicion", "acciones_validas", "stop_movil", "herramientas_disponibles"]
    assert [t["function"]["description"] for t in fase1["tools"]] == [h["descripcion"] for h in HERRAMIENTAS.values()]
    obs = a.db.ultimo_ciclo("vivo")["observacion"]
    assert obs["senal_d"] == obs["senal"] and obs["estrategia"] == "D"            # el nombre anterior se conserva
    herr = a._datos_herramientas(calcular_variables(a.mercado.velas), a.db.carteras("vivo")["con_llm"], "vivo")
    assert "btc" in herr["consultar_cartera"]


# ---------- huellas del modelo ----------
def test_modelo_rechaza_checkpoint_alterado(cfg_completa, tmp_path):
    eth = activos_de(cfg_completa)[1]
    for rel in (eth["modelo"]["escalador_x"], eth["modelo"]["escalador_y"], "activos_extra/ETHUSDT/modelos/lstm/m.keras"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(b"contenido alterado")
    config_congelada(tmp_path, eth, "C", 0.004315, checkpoints=["activos_extra/ETHUSDT/modelos/lstm/m.keras"],
                     sha256_checkpoints={"activos_extra/ETHUSDT/modelos/lstm/m.keras": "0" * 64}, variables=[])
    with pytest.raises(ErrorModelo, match="huella"):
        ModeloPronostico(eth["modelo"], raiz=tmp_path)


# ---------- replay fuera de TE ----------
def test_replay_no_repite_el_conjunto_de_prueba(cfg_completa, tmp_path, gateway):
    sol = activos_de(cfg_completa)[2]
    config_congelada(tmp_path, sol, "C", 0.00122, particiones={"TE": {"ultimo_objetivo": "2026-11-17"}})
    a = agente_de(sol, tmp_path, gateway)
    with pytest.raises(ValueError, match="después de su conjunto de prueba"):
        a.replay("2026-11-05", "2026-11-14")


# ---------- varios agentes en un backend ----------
@pytest.fixture
def dos_activos(cfg_completa, tmp_path, gateway):
    import threading
    lock = threading.Lock()
    btc, eth = activos_de(cfg_completa)[:2]
    config_congelada(tmp_path, eth, "C", 0.004315)
    return {"BTCUSDT": agente_de(btc, tmp_path, gateway, lock=lock),
            "ETHUSDT": agente_de(eth, tmp_path, gateway, pronostico=0.006, lock=lock)}


def test_api_selector_de_activo(cfg_completa, secretos, dos_activos):
    with TestClient(crear_app(cfg_completa, secretos, agentes=dos_activos, programar=False)) as cli:
        lista = cli.get("/api/activos", headers=H).json()
        assert [x["simbolo"] for x in lista["activos"]] == ["BTCUSDT", "ETHUSDT"] and lista["principal"] == "BTCUSDT"
        assert cli.get("/api/estado", headers=H).json()["activo"] == "BTCUSDT"          # sin parámetro: el principal
        est = cli.get("/api/estado?simbolo=ETHUSDT", headers=H).json()
        assert est["activo"] == "ETHUSDT" and est["activo_base"] == "ETH" and est["estrategia"] == "C"
        assert cli.get("/api/estado?simbolo=DOGEUSDT", headers=H).status_code == 404
        # control humano independiente por activo
        assert cli.post("/api/agente/iniciar?simbolo=ETHUSDT", headers=H).json()["estado"] == "corriendo"
        assert cli.get("/api/estado", headers=H).json()["agente"]["estado"] == "detenido"
        assert cli.post("/api/ciclo?simbolo=ETHUSDT", headers=H).json()["resultado"] == "completo"
        assert cli.post("/api/ciclo", headers=H).json()["resultado"] == "omitido"        # BTC sigue detenido
        assert dos_activos["BTCUSDT"].db.consultar("SELECT COUNT(*) AS n FROM ciclos")[0]["n"] == 0
        assert dos_activos["ETHUSDT"].db.consultar("SELECT COUNT(*) AS n FROM ciclos")[0]["n"] == 1
        m = cli.get("/api/metricas?simbolo=ETHUSDT", headers=H).json()
        assert m["simbolo"] == "ETHUSDT" and set(m["carteras"]) == {"sin_llm", "con_llm", "comprar_y_mantener"}
        e = cli.get("/api/escaner", headers=H).json()
        assert {p["simbolo"] for p in e["pares"] if p["operable"]} == {"BTCUSDT", "ETHUSDT"}
        assert cli.get("/api/red?simbolo=ETHUSDT", headers=H).json()["estrategia"] == "C"
        assert cli.get("/api/sistema?simbolo=ETHUSDT", headers=H).json()["simbolo"] == "ETHUSDT"
        assert cli.get("/api/activos").status_code == 401


def test_programador_corre_los_activos_uno_tras_otro(dos_activos):
    for a in dos_activos.values():
        a.iniciar()
    p = Programador(list(dos_activos.values()), 60, 5)
    p.vela_esperada = lambda ahora=None: dos_activos["BTCUSDT"].mercado.velas[-1].fecha
    r = p.revisar()
    assert list(r) == ["BTCUSDT", "ETHUSDT"] and all(x["resultado"] == "completo" for x in r.values())
    assert p.revisar() == {}                                                       # ya procesadas: nada que hacer


def test_error_inesperado_en_un_activo_no_detiene_a_los_demas(dos_activos):
    for a in dos_activos.values():
        a.iniciar()
    dos_activos["BTCUSDT"].ciclo_vivo = lambda **_: 1 / 0
    p = Programador(list(dos_activos.values()), 60, 5)
    p.vela_esperada = lambda ahora=None: dos_activos["ETHUSDT"].mercado.velas[-1].fecha
    r = p.revisar()
    assert r["BTCUSDT"]["resultado"] == "error" and dos_activos["BTCUSDT"].db.estado()["estado"] == "pausado"
    assert r["ETHUSDT"]["resultado"] == "completo" and dos_activos["ETHUSDT"].db.estado()["estado"] == "corriendo"


# ---------- modelos reales (solo si los archivos están en la carpeta) ----------
@pytest.mark.parametrize("simbolo", ["ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT", "LTCUSDT", "TRXUSDT", "DOGEUSDT", "MXUSDT", "FILUSDT", "BCHUSDT", "ZECUSDT", "NEARUSDT", "DOTUSDT"])
def test_modelo_real_repite_predicciones_de_te(cfg_completa, simbolo):
    a = next(x for x in activos_de(cfg_completa) if x["mercado"]["simbolo"] == simbolo)
    base = (RAIZ / a["modelo"]["config_congelada"]).parent.parent           # activos_extra[_loteN]/<SIMBOLO>
    if not (RAIZ / a["modelo"]["config_congelada"]).exists() or not (base / "datos/procesados").exists():
        pytest.skip("archivos del activo no disponibles en esta copia")
    m = ModeloPronostico(a["modelo"])
    assert m.version["huellas_verificadas"] and m.estrategia in ("C", "D")
    ventanas = pd.read_csv(base / f"datos/procesados/{simbolo}_1d_ejemplos_ventanas.csv")
    te = ventanas[ventanas["conjunto"] == "TE"].merge(
        pd.read_csv(base / "resultados/predicciones_TE.csv")[["fecha_emision", "rendimiento_estimado"]], on="fecha_emision")
    variables = [f"ret_lag_{i}" for i in range(20)]
    for _, fila in te.iloc[[0, len(te) // 2, -1]].iterrows():               # tres fechas de TE (inicio, mitad, fin)
        assert abs(m._funcion(fila[variables].tolist()) - fila["rendimiento_estimado"]) < 1e-6


@pytest.mark.parametrize("simbolo", ["ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT", "LTCUSDT", "TRXUSDT", "DOGEUSDT", "MXUSDT", "FILUSDT", "BCHUSDT", "ZECUSDT", "NEARUSDT", "DOTUSDT"])
def test_variables_en_vivo_reproducen_el_pronostico_futuro_del_notebook(cfg_completa, simbolo):
    """Mismo camino que un ciclo en vivo (velas de MEXC → calcular_variables → ensamble → señal) contra prediccion_futura.csv."""
    from app.mexc import DIA_MS, Vela
    a = next(x for x in activos_de(cfg_completa) if x["mercado"]["simbolo"] == simbolo)
    base = (RAIZ / a["modelo"]["config_congelada"]).parent.parent
    recientes = sorted((base / "datos/originales").glob(f"{simbolo}_1d_mexc_recientes_*.csv")) if base.exists() else []
    if not recientes or not (RAIZ / a["modelo"]["config_congelada"]).exists():
        pytest.skip("archivos del activo no disponibles en esta copia")
    fut = pd.read_csv(base / "resultados/prediccion_futura.csv").iloc[0]
    df = pd.read_csv(recientes[-1])
    df["fecha"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    df = df[df["fecha"] <= fut["fecha_corte"]]
    velas = [Vela(f.fecha, int(f.open_time), int(f.open_time) + DIA_MS, f.open, f.high, f.low, f.close, f.volume)
             for f in df.itertuples()]
    obs = ModeloPronostico(a["modelo"]).completar(calcular_variables(velas))
    assert obs.fecha_vela == fut["fecha_corte"] and obs.cierre == pytest.approx(fut["cierre_en_corte"])
    assert obs.pronostico == pytest.approx(fut["rendimiento_estimado"], abs=1e-6)
    assert obs.senal == fut["senal"] and obs.cierre_sobre_sma20 == bool(fut["cierre_sobre_SMA20"])


# ---------- v1.6: decimales del precio por activo ----------
def test_decimales_del_precio_en_el_texto_del_llm(cfg_completa, tmp_path, gateway):
    activos = {a["mercado"]["simbolo"]: a for a in activos_de(cfg_completa)}
    doge = activos["DOGEUSDT"]
    config_congelada(tmp_path, doge, "D", 0.002779)
    from dataclasses import replace
    f = 0.06 / 70_000                                                       # velas de prueba llevadas a un precio tipo DOGE
    velas = [replace(v, open=v.open * f, high=v.high * f, low=v.low * f, close=v.close * f) for v in generar_velas(semilla=5)]
    a = agente_de(doge, tmp_path, gateway, velas=velas)
    obs = a.modelo.completar(calcular_variables(velas))
    txt = a._indicadores_texto(obs)
    assert txt["precio_cierre"] == f"{obs.cierre:.5f} USDT" and txt["sma20"] == f"{obs.sma20:.5f} USDT"
    btc = agente_de(activos["BTCUSDT"], tmp_path, gateway, nombre_db="btc.sqlite3")
    obs_b = btc.modelo.completar(calcular_variables(btc.mercado.velas))
    assert btc._indicadores_texto(obs_b)["precio_cierre"] == f"{obs_b.cierre:.2f} USDT"      # igual que en la v1.0–v1.5


def test_motivo_del_stop_con_decimales_del_activo():
    from app.riesgo import LimitesRiesgo, evaluar
    lim = LimitesRiesgo(1.0, 0.03, 2.0, 26)
    d = evaluar("MANTENER", en_posicion=True, cierre=0.05819, stop=0.06012, patrimonio_actual=1, patrimonio_previo=1,
                bloqueo_vigente=False, limites=lim, decimales=5)
    assert d.accion == "VENDER" and "cierre 0.05819 < stop 0.06012" in d.motivos[0]
    d2 = evaluar("MANTENER", en_posicion=True, cierre=61000.0, stop=61937.57, patrimonio_actual=1, patrimonio_previo=1,
                 bloqueo_vigente=False, limites=lim)
    assert "cierre 61,000.00 < stop 61,937.57" in d2.motivos[0]                              # BTC: formato de siempre
