# Informe del agente de IA financiero — DL para Finanzas

**Proyecto final (bloques 14–16 del protocolo).** Datos al cierre de la vela del **25 de noviembre de 2026**; versión actual **v2.0** (laboratorio de señales con avisos por correo, sección 4.1); las velas hasta el 25 nov se procesaron con la v1.9.
Todas las cifras salen de las bases SQLite del agente y se regeneran con `python agente/exportar_registros.py` (carpeta `agente/registros/`).

## 1. Resumen

El agente observa velas diarias de MEXC para 15 pares contra USDT, consulta el ensamble LSTM de cada activo, pide una propuesta a un LLM local (Ollama, `llama3.2:3b`), aplica controles de riesgo deterministas, ejecuta en un simulador Paper propio y registra todo en SQLite. Cada activo tiene tres carteras de 50,000 USDT con el mismo periodo y costos: **sin LLM** (estrategia del modelo + riesgo), **con LLM** (propuesta del LLM + el mismo riesgo) y **comprar y mantener**.

| Cartera (15 activos, en vivo) | Patrimonio | Rendimiento neto | Drawdown máx. | Órdenes | Cerradas (ganadas) | Win Rate | Acciones rechazadas |
|---|---|---|---|---|---|---|---|
| Sin LLM | 751,975.51 | **+0.26 %** | −0.93 % | 13 | 5 (4) | 80 % | 1 |
| Con LLM | 707,218.32 | **−5.70 %** | −7.47 % | 32 | 9 (0) | 0 % | 23 |
| Comprar y mantener | 716,919.76 | **−4.41 %** | −7.04 % | 15 | 0 | — | 0 |

Capital inicial: 750,000 (15 × 50,000). Cada activo cuenta como 50,000 en efectivo antes de su primer ciclo.

**Conclusión:** en este periodo el LLM **no aporta valor**. La cartera con LLM quedó por debajo de la estrategia del modelo y también de comprar y mantener. El motor de riesgo sí cumplió su función: rechazó 18 compras no permitidas y forzó 9 ventas por stop. El protocolo no exige que el LLM mejore el resultado; aquí se documenta por qué no lo hizo.

**Meta de +20 %:** no se alcanzó en ningún periodo. Lo que sí se demostró es que el modelo profundo supera a la regresión lineal y protege el capital frente a comprar y mantener en un mercado bajista. El detalle está en la sección 10.

## 2. Arquitectura y componentes obligatorios

```
React + TypeScript (5173) ──X-API-Key──▶ Backend FastAPI (127.0.0.1:8000)
     ├─ MEXC API pública: velas diarias y reglas del par (solo lectura; rutas de órdenes reales bloqueadas)
     ├─ Un agente por activo: ensamble LSTM de 3 semillas + escaladores versionados (huellas SHA-256 al cargar)
     ├─ Gateway propio (127.0.0.1:8001) ──X-API-Key──▶ Ollama local (11434), llama3.2:3b
     ├─ Motor de riesgo determinista (el LLM no puede saltarlo ni cambiar la configuración)
     ├─ Simulador Paper (saldo, paso de cantidad y monto mínimo del par, costo 0 %, deslizamiento 0 %)
     └─ SQLite por activo: ciclos, decisiones, órdenes, patrimonio, eventos y estado
```

| Componente del protocolo | Cómo se cumple | Evidencia |
|---|---|---|
| LLM local con Ollama | `llama3.2:3b` en Ollama 0.40.16, MacBook Air M1 (8 GB). Sin inferencia en la nube: con el Wi‑Fi apagado, el modelo respondió una consulta en 11.9 s (11.3 s fueron la carga del modelo) | `agente/evidencia/ollama_local.txt`; latencia guardada en cada ciclo |
| API privada del LLM | Gateway propio con `X-API-Key`; rechaza claves ausentes o incorrectas (HTTP 401) | Escenarios de clave incorrecta en `agente/evidencia/demostracion_errores.md` |
| UI React y TypeScript | Activo, fecha de la vela, pronóstico, indicadores, propuesta, motivo, riesgo, posición y patrimonio; iniciar, pausar y detener | `agente/frontend/`; capturas en `agente/evidencia/capturas/` |
| Backend | FastAPI: carga modelo y escaladores, valida entradas, coordina el ciclo, API documentada en `/docs` | `agente/backend/` |
| MEXC y modo Paper | Datos públicos de MEXC; compras y ventas solo en el simulador propio | `agente/backend/app/paper.py`; sección 4 |
| Modelo de la práctica | Ensamble y transformaciones congelados, con versión, contrato de variables y huellas | `agente/verificar_modelo.py`, `agente/evidencia/verificacion_*.json` |
| Pruebas automatizadas | 119 pruebas: riesgo, simulador, autenticación, nueve errores, multi-activo y avisos | `cd agente/backend && python -m pytest`; salida en `agente/evidencia/pytest_resultado.txt` |

### Ciclo de cada activo (una vez al día, 5 minutos después del cierre de 00:00 UTC)

1. Consulta las velas cerradas de MEXC y valida el activo, la frecuencia, el orden de las fechas y la antigüedad (máximo 26 h).
2. Calcula los 20 rezagos con la misma definición del entrenamiento y obtiene el pronóstico del ensamble.
3. Consulta al LLM con datos estructurados y herramientas de solo lectura con permisos definidos (por ejemplo, `consultar_indicadores`).
4. Exige un JSON con acción, símbolo, fecha de la vela y justificación. Rechaza símbolos, fechas o acciones no permitidas: sin posición solo puede COMPRAR o MANTENER, y con posición solo MANTENER o VENDER.
5. Aplica los controles de riesgo a las tres carteras.
6. Ejecuta en Paper, guarda la decisión y actualiza efectivo, posición y patrimonio. Una vela no se procesa dos veces.
7. Muestra el resultado en la interfaz y espera la siguiente vela.

## 3. Periodo, ciclos y replay

| Activos | Ciclos en vivo | Periodo |
|---|---|---|
| BTCUSDT | 12 | 14 al 25 nov |
| ETHUSDT, SOLUSDT | 9 cada uno | 17 al 25 nov |
| Los otros 12 | 7 cada uno | 19 al 25 nov |

Hay **114 ciclos de decisión en vivo**: 12 + 2 × 9 + 12 × 7. Todos terminaron sin errores y sin velas duplicadas. La única falla en vivo fue el primer ciclo de XRP (17 nov): el LLM generó 2,328 tokens sin cerrar el JSON y el gateway agotó el tiempo de espera. El agente se pausó sin operar, XRP se retiró en la v1.4 y regresó en la v1.5 con un límite de 400 tokens por respuesta. Desde entonces ningún ciclo necesitó reintento.

**Replay (separado de la conexión en vivo).** BTC tiene además 10 ciclos de replay (velas del 5 al 14 nov), guardados con `modo = 'replay'` en su propia sección de la base. El replay no puede empezar dentro del conjunto de prueba (TE) de un activo. En BTC, el TE termina el 4 nov. La vela del 14 nov está tanto en el replay como en el primer ciclo en vivo, así que BTC suma **22 ciclos de decisión y 21 velas distintas** (≥ 20 en ambos casos).

Los otros 14 activos no tienen replay. Su periodo posterior al TE (desde el 17 o el 19 nov) coincide con sus ciclos en vivo, y un replay de esas velas duplicaría observaciones. No se aceleró la frecuencia diaria.

| Replay BTC (5–14 nov) | Rendimiento neto | Drawdown máx. | Órdenes |
|---|---|---|---|
| Sin LLM | 0.00 % | 0.00 % | 0 |
| Con LLM | −6.07 % | −6.07 % | 2 (salida por stop) |
| Comprar y mantener | −15.70 % | −15.70 % | 1 |

## 4. Datos de MEXC y simulador Paper

- **Datos:** `GET /api/v3/klines` diario de MEXC spot; solo se usan velas cerradas de 00:00 UTC. Las reglas del par (paso de cantidad y monto mínimo) se leen de `/api/v3/exchangeInfo`.
- **Ejecución:** la señal se calcula al cierre de t y se ejecuta en la apertura de t+1, que en MEXC es igual al cierre de t. Costo de 0 % por compra o venta y deslizamiento supuesto de 0 % (configurable en `config/agente.json`). Sin apalancamiento ni ventas en corto. Exposición máxima del 100 % del patrimonio de cada cartera.
- **Órdenes reales bloqueadas:** el backend no tiene ninguna ruta que envíe órdenes a MEXC y no usa clave de trading. La cuenta demo de MEXC no se usó por tres razones:
  - MEXC solo ofrece demo para futuros perpetuos, desde su web.
  - Su API se conecta directamente al entorno real y no tiene sandbox, según la FAQ de API de MEXC citada en el protocolo.
  - El protocolo pide ejecutar solo en un simulador propio, con las condiciones de capital y costo indicadas.

  El 26 nov el profesor pidió revisar la conexión con la cuenta demo de MEXC; queda pendiente, en revisión con él. La única vía automática hoy sería un token de sesión del navegador con endpoints no oficiales, y no se usó por seguridad.

### 4.1 Laboratorio de señales con avisos por correo (v2.0, 26 nov)

Por indicación del profesor, la interfaz dejó de mostrar saldos, porque el sistema en realidad no compra nada. Desde la v2.0 funciona como laboratorio:

- Después de cada ciclo en vivo, si la estrategia del modelo de un activo (la cartera sin LLM, tras el motor de riesgo) compra o vende, el backend envía un aviso por correo. El aviso incluye el activo, la vela, el cierre, el pronóstico frente a δ y el stop sugerido (compra) o el motivo (venta). El usuario decide si opera a mano en MEXC.
- El correo sale por Gmail (SMTP con TLS) con una contraseña de aplicación. Solo se permiten servidores SMTP conocidos, y el usuario, la contraseña y el destino viven en `.env`.
- Primero se intentó WhatsApp: CallMeBot tenía el cupo lleno y la API oficial de Meta exige una plantilla aprobada (hasta 24 h) para escribir fuera de la ventana de 24 h. Ese código se conserva como alternativa deshabilitada.
- Cada aviso queda en la tabla `notificaciones` de la base del activo, con un único aviso por vela y tipo. Un fallo del correo no pausa el agente ni cambia sus decisiones.
- El LLM no dispara avisos, porque en vivo no aportó valor (sección 8).
- La simulación Paper se conserva por dentro solo para la comparación que pide el bloque 16; las cifras de las secciones 7 a 10 salen de ella.
- Hay 22 pruebas nuevas (119 en total).

## 5. Riesgo y control humano

Los límites están fijados en `config/agente.json` antes de la prueba. El LLM no puede modificarlos, y el SHA-256 de la configuración se guarda en cada ciclo.

| Control | Regla | Activaciones en vivo |
|---|---|---|
| Stop móvil | Nivel = cierre × (1 − 2 × vol20); solo sube; se revisa al cierre | 10 ventas forzadas: 9 con LLM y 1 sin LLM (SOL, 20 nov) |
| Pérdida diaria máxima | Caída de 3 % o más del patrimonio entre dos cierres → se bloquean las compras hasta rearmar | 22 carteras-día: 20 nov (15), 21 nov (1) y 24 nov (6) |
| Antigüedad máxima del dato | 26 h | Ninguna (las velas tenían de 0.08 a 20.3 h; la de 20.3 h fue el primer ciclo de BTC, el 15 nov) |
| Validación de acciones | Acción no permitida → MANTENER | 18 compras del LLM con posición ya abierta |
| Detener ≠ liquidar | Detener bloquea nuevas órdenes y conserva las posiciones; liquidar es una acción aparte | Escenario del botón de detención (sección 6) |

**Regla de rearme** (fijada el 20 nov, antes de ver los ciclos posteriores): después de cada ciclo se rearman todos los activos bloqueados con el botón «Rearmar todos los bloqueados». Cada rearme queda como evento de control (`origen: rearmar_todos`); hubo 19 rearmes por activo, en tres días.

## 6. Errores y persistencia

Los nueve escenarios (aquí en el orden del protocolo; el archivo de evidencia los numera distinto) se demostraron el 16 nov con una instancia separada, para no alterar los ciclos en vivo. Cada uno se provocó con un fallo real: Ollama cerrado, Wi‑Fi apagado, clave equivocada, límite de tokens, etc. El detalle está en `agente/evidencia/demostracion_errores.md`.

| # | Escenario | Respuesta | ¿Operación indebida? |
|---|---|---|---|
| 1 | API sin respuesta / límite de solicitudes | 3 intentos con espera creciente y pausa (el 429 está cubierto con una prueba automatizada) | No |
| 2 | Dato atrasado | Rechazado antes de decidir; pausa | No |
| 3 | Ollama detenido | 3 intentos (2 s, 4 s), gateway 502, pausa | No |
| 4 | JSON inválido | Respuesta cruda guardada, 3 intentos, pausa | No |
| 5 | Clave incorrecta (backend y gateway) | HTTP 401; el agente no se inicia | No |
| 6 | Saldo insuficiente | Orden registrada como rechazada; acción final MANTENER | No |
| 7 | Evento duplicado | Segundo ciclo de la misma vela rechazado | No (2 órdenes, no 4) |
| 8 | Reinicio del backend | Estado y posiciones recuperados de SQLite sin duplicar | No |
| 9 | Botón de detención | Nuevas órdenes bloqueadas y posiciones conservadas | No |

**Persistencia:** cada activo tiene su base SQLite con velas procesadas (ciclos), decisiones de las tres carteras, órdenes Paper con su costo, patrimonio diario y eventos. Su exportación a CSV está en `agente/registros/`. Los datos externos se tratan como datos, nunca como instrucciones.

## 7. Evaluación por activo (en vivo, mismo periodo y costos dentro de cada activo)

| Activo | Velas en vivo | Sin LLM | Con LLM | Comprar y mantener | DD sin LLM | DD con LLM | DD comprar y mantener |
|---|---|---|---|---|---|---|---|
| BTCUSDT | 14 a 25 nov (12) | 0.00 % | −7.72 % | −5.75 % | 0.00 % | −10.36 % | −9.79 % |
| ETHUSDT | 17 a 25 nov (9) | +3.86 % | −10.69 % | −7.24 % | 0.00 % | −11.36 % | −11.06 % |
| SOLUSDT | 17 a 25 nov (9) | −8.14 % | −8.14 % | −6.25 % | −9.12 % | −9.12 % | −8.39 % |
| XRPUSDT | 19 a 25 nov (7) | 0.00 % | −2.32 % | −2.32 % | 0.00 % | −5.13 % | −5.13 % |
| BNBUSDT | 19 a 25 nov (7) | +1.43 % | −5.84 % | −4.50 % | 0.00 % | −6.78 % | −6.76 % |
| ADAUSDT | 19 a 25 nov (7) | 0.00 % | −3.95 % | −3.95 % | 0.00 % | −5.73 % | −5.73 % |
| LTCUSDT | 19 a 25 nov (7) | 0.00 % | +1.16 % | +1.16 % | 0.00 % | −5.91 % | −5.91 % |
| TRXUSDT | 19 a 25 nov (7) | 0.00 % | −2.06 % | −2.06 % | 0.00 % | −2.71 % | −2.71 % |
| DOGEUSDT | 19 a 25 nov (7) | 0.00 % | −3.78 % | −3.78 % | 0.00 % | −6.53 % | −6.53 % |
| MXUSDT | 19 a 25 nov (7) | 0.00 % | −0.18 % | −0.18 % | 0.00 % | −0.70 % | −0.70 % |
| FILUSDT | 19 a 25 nov (7) | 0.00 % | −10.81 % | −4.89 % | 0.00 % | −12.81 % | −9.76 % |
| BCHUSDT | 19 a 25 nov (7) | −0.29 % | −0.29 % | −0.29 % | −5.57 % | −5.57 % | −5.57 % |
| ZECUSDT | 19 a 25 nov (7) | +7.11 % | −16.05 % | −13.77 % | 0.00 % | −19.49 % | −17.29 % |
| NEARUSDT | 19 a 25 nov (7) | 0.00 % | −6.18 % | −4.77 % | 0.00 % | −11.24 % | −11.13 % |
| DOTUSDT | 19 a 25 nov (7) | 0.00 % | −8.71 % | −7.56 % | 0.00 % | −9.19 % | −8.47 % |

| Activo | Órdenes sin / con LLM | Cerradas (ganadas) sin LLM | Cerradas (ganadas) con LLM | Rechazadas con LLM | LLM propone COMPRAR | …sin señal del modelo | Latencia LLM media / máx. |
|---|---|---|---|---|---|---|---|
| BTCUSDT | 0 / 3 | 0 | 1 (0) | 1 | 2 de 12 | 2 | 16.7 / 23.9 s |
| ETHUSDT | 2 / 3 | 1 (1) | 1 (0) | 1 | 3 de 9 | 2 | 11.9 / 19.8 s |
| SOLUSDT | 3 / 3 | 1 (0) | 1 (0) | 7 | 9 de 9 | 0 | 10.9 / 13.6 s |
| XRPUSDT | 0 / 1 | 0 | 0 | 0 | 1 de 7 | 1 | 11.0 / 14.7 s |
| BNBUSDT | 2 / 3 | 1 (1) | 1 (0) | 1 | 3 de 7 | 2 | 11.5 / 16.2 s |
| ADAUSDT | 0 / 1 | 0 | 0 | 0 | 1 de 7 | 1 | 10.4 / 11.9 s |
| LTCUSDT | 1 / 1 | 0 | 0 | 1 | 2 de 7 | 1 | 10.8 / 12.8 s |
| TRXUSDT | 0 / 2 | 0 | 1 (0) | 1 | 1 de 7 | 1 | 11.0 / 12.9 s |
| DOGEUSDT | 0 / 1 | 0 | 0 | 0 | 1 de 7 | 1 | 11.8 / 13.0 s |
| MXUSDT | 0 / 1 | 0 | 0 | 0 | 1 de 7 | 1 | 10.9 / 11.6 s |
| FILUSDT | 0 / 3 | 0 | 1 (0) | 1 | 2 de 7 | 2 | 10.8 / 11.1 s |
| BCHUSDT | 1 / 1 | 0 | 0 | 6 | 7 de 7 | 0 | 11.9 / 13.5 s |
| ZECUSDT | 4 / 3 | 2 (2) | 1 (0) | 2 | 4 de 7 | 2 | 11.9 / 14.0 s |
| NEARUSDT | 0 / 3 | 0 | 1 (0) | 1 | 2 de 7 | 2 | 11.8 / 12.8 s |
| DOTUSDT | 0 / 3 | 0 | 1 (0) | 1 | 2 de 7 | 2 | 13.3 / 28.1 s |

**Latencia:** el LLM tardó 12.0 s de media por ciclo (mediana 11.1 s, mínimo 8.9 s, máximo 28.1 s). Los 15 activos se procesan uno tras otro en unos 3 minutos.

**Interpretación.**
- **Sin LLM:** el mercado cayó en todo el periodo; en los 114 ciclos el cierre estuvo por debajo de la SMA20. El modelo dio solo 21 señales de compra en 114 ciclos, concentradas en SOL (9) y BCH (7). Por eso la cartera sin LLM pasó la mayor parte del tiempo en efectivo y evitó la caída de 4 % a 15 % del 20 nov. Sus 5 operaciones cerradas dieron 4 ganancias (BNB, ETH y dos de ZEC) y una pérdida por stop (SOL).
- **Con LLM:** en el primer ciclo de cada activo el LLM propuso COMPRAR, así que hasta el 19 nov su cartera fue idéntica a comprar y mantener. En XRP, ADA, LTC, DOGE, MX y BCH sigue siéndolo; en TRX lo fue hasta que el stop vendió el 25 nov. El 20 nov los stops vendieron en 6 activos en el punto bajo. Al día siguiente el LLM volvió a comprar en los 6 a precios más altos: BTC de 58,954.52 a 60,212.44, ETH de 1,623.12 a 1,685.70, SOL de 68.88 a 70.30, BNB de 540.91 a 548.62, ZEC de 759.52 a 780.22 y NEAR de 2.8508 a 2.8935. Esa combinación de stop y recompra explica por qué la cartera con LLM quedó por debajo de comprar y mantener. Sus 9 operaciones cerradas terminaron todas por stop y con pérdida.
- **Comprar y mantener:** refleja la caída del mercado (−4.41 % en total, −5.75 % en BTC desde el 14 nov).
- **Muestra pequeña:** con 7 a 12 ciclos por activo y 14 operaciones cerradas en total, el Win Rate y el profit factor no son estadísticamente concluyentes. Solo describen este periodo.

## 8. ¿El LLM aporta valor? Análisis de sus propuestas y justificaciones

Se comparó cada justificación guardada con los datos del ciclo, que también están guardados en la columna `observacion` de `ciclos.csv`.

- **Nunca propuso VENDER.** En 114 ciclos propuso 41 veces COMPRAR, 73 veces MANTENER y ninguna vez VENDER. Todas las salidas de la cartera con LLM fueron por stop.
- **Sesgo a COMPRAR.** Propuso COMPRAR en los 21 ciclos con señal de compra del modelo y en 20 ciclos sin ella (49 % de sus compras). El caso más claro es la vela del 19 nov, primer ciclo de 12 activos (los 10 del lote 2, DOT y XRP): propuso COMPRAR en los 12, aunque el modelo solo daba compra en BCH. En 18 ocasiones propuso COMPRAR con la posición ya abierta, una acción no permitida que la validación cambió a MANTENER.
- **Comparaciones falsas con números reales.** Ejemplos:
  - BCH: «200.60 es mayor que 224.73 → tendencia subida» (23 nov).
  - ETH: «1710.95 es mayor que 1949.66 → ascendente» (23 nov).
  - ZEC: «777.13 es mayor que 996.44 → subir» (23 nov).
  - DOT: «0.6637 es mayor que 0.8287» (20 nov).
  - NEAR: «2.851 es mayor que 3.528» (20 nov).
- **«Cerca de la SMA20» con distancias grandes.** Lo dijo de FIL estando 26 % abajo (20 nov) y 22.9 % abajo (22 nov), y de BTC estando 17 % abajo (20 nov).
- **Calificaciones contradictorias.** Llamó «baja» a una volatilidad de 4.27 % en FIL y «moderada» a una de 4.50 %. Llamó «alta» a una de 2.77 % en BNB y «moderada» a una de 2.73 %.
- **Números inventados y caracteres raros.** En BTC escribió «cierre ´5412.44 mayor al SMA20 ·0193.41» (21 nov); los datos reales eran 60,212.44 y 70,193.41. En SOL y DOGE aparecieron «ÓDelta» y «°0.2779%». El detector de números inventados marcó 4 justificaciones de 114 en vivo (y 3 de 10 en replay). El detector no reconoce comparaciones falsas hechas con números reales, y en MX marcó dos redondeos.
- **Repetición.** En BTC y DOGE el texto se repite casi palabra por palabra de un día a otro aunque cambien los datos.

**Conclusión:** `llama3.2:3b` no razona de forma confiable sobre los datos que recibe. No agrega información que el modelo no tenga y su sesgo a comprar empeora el resultado. El diseño lo contiene: el LLM no recibe claves, no puede saltarse el motor de riesgo ni cambiar la configuración, y sus acciones no válidas se rechazan. No se cambió de modelo ni de prompt durante la prueba, para no ajustar el agente a los resultados observados.

## 9. Modelos y resultados de prueba (TE) de los 15 activos

Cada activo se entrenó y validó con sus propios datos (TR/VA/TE 70/15/15), con la metodología de BTC. La estrategia (C o D) y el umbral δ se eligieron con VA; el TE se usó una sola vez.

| Activo | Estrategia | TE sistema | TE comprar y mantener | | Activo | Estrategia | TE sistema | TE comprar y mantener |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT | D | −3.25 % | −31.57 % | | MXUSDT | C | −28.39 % | −45.93 % |
| ETHUSDT | C | −38.75 % | −59.63 % | | FILUSDT | D | −23.28 % | −55.70 % |
| SOLUSDT | C | +6.74 % | −43.23 % | | BCHUSDT | C | −67.70 % | −64.53 % |
| XRPUSDT | C | −15.26 % | −67.69 % | | ZECUSDT | C | +12.70 % | +206.79 % |
| BNBUSDT | C | −29.29 % | −41.71 % | | NEARUSDT | D | +6.73 % | +112.57 % |
| ADAUSDT | C | −17.23 % | −78.34 % | | DOTUSDT | C | −5.18 % | −62.61 % |
| LTCUSDT | C | −47.15 % | −62.35 % | | | | | |
| TRXUSDT | C | −10.05 % | −11.56 % | | | | | |
| DOGEUSDT | D | −50.89 % | −78.92 % | | | | | |

- En TE la estrategia superó a comprar y mantener en 12 de 15 activos. Fue positiva en SOL, ZEC y NEAR, y quedó por debajo de comprar y mantener en BCH, ZEC y NEAR.
- En el lote 1, VA eligió la estrategia C en ETH, SOL y XRP, pero en TE la D habría sido mejor. No se cambió porque el TE ya se había usado.
- En VA, la LSTM no superó al pronóstico cero por más que el ruido en BNB, LTC, MX, FIL, BCH y NEAR (`resumen_lstm_VA.csv` del lote 2). Se mantuvieron porque la regla de selección se fijó antes de entrenar; es una limitación del modelo, no del agente.
- **Selección de activos.** Los lotes 2 y 3 se eligieron con una regla de volumen de 24 h fijada antes de entrenar. GOLD(PAXG)USDT salió elegido por un error en el filtro de tokens respaldados por oro (MEXC lo nombra `GOLD(PAXG)`) y se excluyó antes de ver sus resultados. DOTUSDT lo reemplazó con la regla corregida. Hay una nota en `activos_extra_lote2/resultados/correccion_seleccion.md`.

## 10. Meta de rentabilidad (+20 %) y lo que sí se logró

La sección 2 del protocolo pide «rentabilidad positiva +20 %» y verificar que el modelo profundo supere a la regresión lineal. Los bloques 14 y 16 indican que no se exige rentabilidad positiva y que no se exige que el LLM mejore el resultado. Aun así, se reporta sin ambigüedad: **la meta de +20 % no se alcanzó en ningún periodo**.

| Periodo | Mejor resultado del sistema | Comprar y mantener |
|---|---|---|
| TE de BTC (ago 2025 – nov 2026, costo 0.10 %) | −3.25 % (estrategia D) | −31.57 % |
| Replay de BTC (5–14 nov) | 0.00 % (sin LLM) | −15.70 % |
| En vivo, 15 activos (14–25 nov, costo 0 %) | +0.26 % (sin LLM) | −4.41 % |

**Por qué no se llegó.** Los tres periodos coincidieron con un mercado bajista. En TE, BTC cayó 31.6 %, y en los 114 ciclos en vivo el cierre estuvo por debajo de su SMA20. El protocolo solo permite posiciones compradas o efectivo (sin ventas en corto ni apalancamiento). Con esa restricción, en un mercado que cae lo mejor que puede hacer una estrategia es quedarse en efectivo, no ganar 20 %.

**Lo que sí funcionó:**
- **El modelo profundo superó a la regresión lineal**, que es la otra mitad del requisito de la sección 2:
  - Error en TE: RMSE de la LSTM 0.022319 frente a 0.022362 de la regresión lineal.
  - Trading en TE con los mismos costos: −3.25 % frente a −27.98 %, con drawdown de −25.4 % frente a −39.1 % (`resultados/resultados_trading_TE.csv`).
  - Sin costos, la misma estrategia D habría ganado +1.91 % en TE.
- **El sistema protegió el capital frente a comprar y mantener:**
  - En TE de BTC perdió 28.3 puntos menos (−3.25 % frente a −31.57 %).
  - En TE superó a comprar y mantener en 12 de 15 activos, y fue positivo en SOL (+6.74 %), ZEC (+12.70 %) y NEAR (+6.73 %).
  - En el replay evitó la caída de −15.70 %.
- **En vivo, la cartera del modelo sin LLM fue la única positiva:** +0.26 % frente a −4.41 % de comprar y mantener, con drawdown de −0.93 % frente a −7.04 %. Ganó 4 de sus 5 operaciones cerradas (80 %) y evitó la caída de 4 % a 15 % del 20 nov al estar en efectivo.
- **El motor de riesgo funcionó como se diseñó:**
  - Rechazó las 18 compras no permitidas del LLM y forzó las ventas por stop.
  - Bloqueó compras tras pérdidas de 3 % o más.
  - Ningún error produjo operaciones indebidas.
- **La ingeniería del agente cumple todos los componentes del protocolo:** datos de MEXC, modelo versionado, LLM local con API privada, UI, persistencia, nueve errores demostrados y 119 pruebas automatizadas.

## 11. Limitaciones

- El periodo en vivo es corto (7 a 12 ciclos por activo) y estuvo dominado por un mercado bajista, así que los resultados no se pueden generalizar.
- Los activos empezaron en fechas distintas (14, 17 o 19 nov). La comparación entre carteras es justa dentro de cada activo; el total suma periodos distintos.
- El costo es de 0 % y el deslizamiento supuesto de 0 %, como pide el protocolo. Con costos reales, la cartera con LLM, que opera más (32 órdenes frente a 13), saldría aún peor.
- Se usó un LLM pequeño (3 mil millones de parámetros) por el hardware de 8 GB. Un modelo mayor podría razonar mejor, pero se mantuvo el mismo durante toda la prueba.
- La cartera con LLM usa el mismo control de riesgo que la del modelo. Por eso la diferencia entre ambas mide la decisión de entrada del LLM, no un riesgo distinto.

## 12. Reproducción

Instalación, ejecución, pruebas y verificación de los modelos: ver `agente/README.md`. Resumen:

```bash
source .venv/bin/activate
cd agente/backend && python -m pytest                      # 119 pruebas
python agente/verificar_modelo.py                          # BTC contra Colab (desde agente_dl)
python agente/exportar_registros.py                        # regenera agente/registros/ y las cifras de este informe
```

Archivos de `agente/registros/`:
- `metricas_totales.csv` y `metricas_por_activo.csv`: rendimiento neto, drawdown, órdenes, Win Rate y acciones rechazadas.
- `llm_por_activo.csv`: propuestas del LLM, acuerdo con el modelo, avisos y latencia.
- `operaciones_cerradas.csv`: cada compra con su venta, su resultado y su motivo de salida.
- `serie_patrimonio_total.csv`: patrimonio diario de cada cartera.
- `ciclos.csv`, `decisiones.csv`, `ordenes.csv`, `eventos.csv` y `patrimonio.csv`: los registros completos.

El historial de cambios del agente (v1.0 a v2.0) está en `agente/CHANGELOG.md`. La versión con la que se procesó cada vela queda guardada en su ciclo.
