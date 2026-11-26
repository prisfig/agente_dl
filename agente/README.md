# Agente de IA financiero — DL para Finanzas

Sistema Paper (sin dinero real) con velas diarias de MEXC para 15 pares contra USDT (BTC desde la v1.0; ETH, SOL y XRP desde la v1.3; diez más en la v1.6; DOT en la v1.7):
datos MEXC → ensamble LSTM congelado del activo → propuesta de Ollama local → controles de riesgo deterministas → simulador Paper → SQLite → API privada → interfaz React.

Cada activo es un agente independiente (su propio modelo, estrategia, base SQLite, carteras de 50,000 USDT y control humano)
dentro del mismo backend. Sus ciclos corren uno tras otro después del cierre diario (BTC primero).

| Activo | Modelo | Estrategia (elegida con VA) | δ | Base de datos |
|---|---|---|---|---|
| BTCUSDT | LSTM 20 × 3 semillas | D: pronóstico > δ y cierre > SMA20 | 0.0866 % | `datos/agente.sqlite3` |
| ETHUSDT | LSTM 10 × 3 semillas | C: pronóstico > δ | 0.4315 % | `datos/agente_ETHUSDT.sqlite3` |
| SOLUSDT | LSTM 20 × 3 semillas | C: pronóstico > δ | 0.1220 % | `datos/agente_SOLUSDT.sqlite3` |
| XRPUSDT | LSTM 10 × 3 semillas | C: pronóstico > δ | 0.3708 % | `datos/agente_XRPUSDT.sqlite3` |
| BNBUSDT | LSTM 10 × 3 semillas | C: pronóstico > δ | 0.1572 % | `datos/agente_BNBUSDT.sqlite3` |
| ADAUSDT | LSTM 20 × 3 semillas | C: pronóstico > δ | 0.3606 % | `datos/agente_ADAUSDT.sqlite3` |
| LTCUSDT | LSTM 10 × 3 semillas | C: pronóstico > δ | 0.0860 % | `datos/agente_LTCUSDT.sqlite3` |
| TRXUSDT | LSTM 40 × 3 semillas | C: pronóstico > δ | 0.2800 % | `datos/agente_TRXUSDT.sqlite3` |
| DOGEUSDT | LSTM 10 × 3 semillas | D: pronóstico > δ y cierre > SMA20 | 0.2779 % | `datos/agente_DOGEUSDT.sqlite3` |
| MXUSDT | LSTM 10 × 3 semillas | C: pronóstico > δ | 0.1516 % | `datos/agente_MXUSDT.sqlite3` |
| FILUSDT | LSTM 10 × 3 semillas | D: pronóstico > δ y cierre > SMA20 | 0.1777 % | `datos/agente_FILUSDT.sqlite3` |
| BCHUSDT | LSTM 10 × 3 semillas | C: pronóstico > δ | 0.1640 % | `datos/agente_BCHUSDT.sqlite3` |
| ZECUSDT | LSTM 20 × 3 semillas | C: pronóstico > δ | 0.1862 % | `datos/agente_ZECUSDT.sqlite3` |
| NEARUSDT | LSTM 10 × 3 semillas | D: pronóstico > δ y cierre > SMA20 | 0.7621 % | `datos/agente_NEARUSDT.sqlite3` |
| DOTUSDT | LSTM 40 × 3 semillas | C: pronóstico > δ | 0.2394 % | `datos/agente_DOTUSDT.sqlite3` |

XRPUSDT se incluyó en la v1.3, se retiró en la v1.4 (su primer ciclo falló: el LLM generó 2,328 tokens sin cerrar el JSON)
y regresó en la v1.5, que limita cada respuesta del LLM a 400 tokens (`llm.max_tokens_respuesta`).

Los diez activos de la v1.6 los eligió una regla de volumen fijada antes de entrenar (`notebooks/DLF_Activos_Extra_Lote2.ipynb`);
GOLD(PAXG)USDT salió elegido por un error de nombre en el filtro de tokens respaldados por oro y se excluyó antes de ver sus resultados. En la v1.7 lo reemplazó DOTUSDT, elegido con la misma regla corregida
(`notebooks/DLF_Activos_Extra_Lote3.ipynb`).

> Estado: backend, gateway, pruebas e interfaz React + TypeScript listos.

## Arquitectura

```
React + TS (5173) ──X-API-Key──▶ Backend FastAPI (127.0.0.1:8000)
                                   ├─ MEXC API pública (solo lectura; rutas de órdenes bloqueadas)
                                   ├─ Un agente por activo: ensamble LSTM (3 semillas) + escaladores propios
                                   ├─ Gateway Ollama (127.0.0.1:8001) ──X-API-Key──▶ Ollama local (11434)
                                   ├─ Motor de riesgo determinista (el LLM no puede saltarlo)
                                   ├─ Simulador Paper (saldo, paso de cantidad y monto mínimo del par)
                                   └─ SQLite: ciclos, decisiones, órdenes, patrimonio, eventos y estado
```

## Instalación (Mac, una sola vez)

Desde la carpeta `agente_dl`, con el entorno de Python 3.13 ya creado (`.venv`):

```bash
source .venv/bin/activate
uv pip install -r agente/backend/requirements.txt
cp agente/.env.example agente/.env
python -c "import secrets; print(secrets.token_urlsafe(32))"   # ejecútalo dos veces y pega cada clave en agente/.env
```

## Ejecución (tres terminales, todas con `source .venv/bin/activate` y en `agente_dl/agente/backend`)

```bash
ollama serve                                                    # si Ollama no está abierto ya
uvicorn gateway.main:app --host 127.0.0.1 --port 8001           # gateway privado de Ollama
uvicorn app.main:app --host 127.0.0.1 --port 8000               # backend del agente
```

Documentación de la API: http://127.0.0.1:8000/docs (las llamadas exigen el encabezado `X-API-Key`).
Todas las rutas aceptan `?simbolo=ETHUSDT` (sin él, BTCUSDT); `GET /api/activos` los resume todos.

Con los 15 activos corriendo, los ciclos diarios tardan en total unos minutos (uno tras otro; el LLM es lo más lento).
Los activos nuevos arrancan *detenidos*: cada uno se inicia desde la interfaz eligiéndolo en el selector de la barra superior.

## Interfaz (React + TypeScript)

```bash
cd agente/frontend
npm install        # solo la primera vez
npm run dev        # abre http://127.0.0.1:5173
```

Al abrirla se escribe la clave `BACKEND_API_KEY` de `agente/.env`; vive solo en la sesión del navegador (no está en el código ni en variables VITE).
Pestañas: Resumen, Mercado, Escáner, Operaciones, Estrategia, Auditoría y Sistema (Salud, Cerebro, Red neuronal en vivo, Ajustes).
El selector de activo (los 15 pares) cambia todas las pestañas al activo elegido; Resumen muestra además una tabla con todos.

**Operaciones** (desde la v1.8) suma los 15 activos de la cartera elegida (Sin LLM, Con LLM o Comprar y mantener):
modo de trading (Paper, precios reales de MEXC, órdenes simuladas), saldo total y PnL realizado y no realizado,
drawdown, acierto, profit factor, panel de riesgo con los límites del motor, posiciones abiertas (cuándo y a qué precio
compró, stop móvil y distancia, PnL al cierre y a precio actual), historial de operaciones cerradas con su motivo de
salida, saldo por activo y las reglas de entrada y salida. Debajo sigue el detalle por ciclo del activo seleccionado.
Lo alimenta `GET /api/operaciones?cartera=con_llm`. El patrimonio oficial se valúa al último cierre diario; el precio
actual de MEXC (`/api/v3/ticker/price`, en caché 30 s) es solo informativo.

**Control de pérdida diaria.** Si el patrimonio de un activo cae 3 % o más entre dos cierres, se bloquean sus compras hasta que
el usuario lo rearme. Regla de operación (fijada el 20 nov): después de cada ciclo se rearman todos los bloqueados con el botón
«Rearmar todos los bloqueados» (Resumen u Operaciones; `POST /api/riesgo/rearmar_todos`, desde la v1.9). Cada rearme queda
como evento de control en la base del activo.

## Pruebas automatizadas

```bash
cd agente/backend && python -m pytest
```

97 pruebas. Cubren los controles de riesgo, el simulador, la autenticación y los nueve escenarios de error del protocolo:
MEXC sin respuesta o con límite de solicitudes, dato atrasado, Ollama detenido, JSON inválido, clave incorrecta,
saldo insuficiente, evento duplicado, reinicio del backend y botón de detención. Desde la v1.3 también el funcionamiento
multi-activo (estrategias C y D, control independiente, ciclos uno tras otro, huellas de los modelos) y que los modelos
reales de los 14 activos extra repiten sus predicciones de TE y el pronóstico del 18 nov del notebook. Desde la v1.8,
que el resumen de operaciones cuadra (saldo = capital + realizado + no realizado = efectivo + invertido) e identifica las salidas por stop.

## Verificación de los modelos en esta computadora

```bash
python agente/verificar_modelo.py            # BTC: 444 pronósticos de TE y pronóstico futuro contra Colab
python agente/verificar_activos_extra.py     # lote 1 (ETH, SOL y XRP): huellas, TE completo, señales y pronóstico futuro
python agente/verificar_activos_extra.py activos_extra_lote2     # lote 2 (los diez de la v1.6)
python agente/verificar_activos_extra.py activos_extra_lote3     # lote 3 (DOT, v1.7)
```

## Decisiones de diseño

- **Configuración** en `config/agente.json`: capital 50,000 USDT, costo 0 %, exposición máxima 100 %, pérdida diaria máxima 3 %,
  stop móvil 2 × volatilidad de 20 días, antigüedad máxima del dato 26 h. El LLM no puede cambiarla; su SHA-256 se guarda en cada ciclo.
- **Ejecución**: señal al cierre de t, ejecución en la apertura de t+1 (en MEXC es igual al cierre de t). Deslizamiento supuesto 0 %.
- **Tres carteras por activo con el mismo periodo y costos**: `sin_llm` (estrategia del activo, C o D, + riesgo),
  `con_llm` (propuesta del LLM + el mismo riesgo) y `comprar_y_mantener`.
- **Activos independientes**: cada uno tiene su capital de 50,000 USDT; no hay una cartera conjunta ni reparto de capital entre activos.
- **Detener ≠ liquidar**: detener bloquea nuevas órdenes y conserva posiciones; liquidar es una acción aparte.
- **Errores**: reintentos limitados con espera creciente; si fallan, el agente se pausa y la vela no se marca como procesada.
- **Replay**: los ciclos históricos se guardan con `modo = 'replay'`, separados de los ciclos en vivo. No puede empezar dentro del
  conjunto de prueba (TE) del activo.
- **Secretos**: solo en `agente/.env` (fuera del repositorio). React nunca recibe la clave del gateway.
