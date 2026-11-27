# Deep Learning para Finanzas — práctica y laboratorio de señales con IA

Este repositorio reúne la **práctica** del curso, con el modelo de pronóstico de BTC/USDT, y el **proyecto final**: un sistema de IA que analiza cada día 15 pares de MEXC con el modelo LSTM de cada activo, un LLM local (Ollama), controles de riesgo deterministas y una interfaz web.

> **Versión actual: v2.3, laboratorio de señales.** Por indicación del profesor, el sistema no maneja saldos: en realidad no compra nada. Cuando el modelo de un activo da señal de compra (o de venta) y pasa los controles de riesgo, **envía un aviso por correo** para que el usuario decida si compra a mano en MEXC. Ver [Laboratorio de señales y avisos por correo](#laboratorio-de-señales-y-avisos-por-correo-v20). La pestaña **PnL simulado** (v2.1) muestra cómo le habría ido a la señal, marcada como simulación: no son compras reales. Desde la v2.2, **Señales** muestra un activo a la vez con sus gráficos e indicadores financieros, y **Mercado** permite comparar los 15 pares. La v2.3 agrega a cada señal un plan sugerido para la compra manual (stop, take profit y tamaño con Kelly fraccional) y el [análisis complementario](Analisis_Complementario.md) pedido en la rúbrica.
>
> El sistema **no envía órdenes reales**. Solo lee datos públicos de MEXC; la simulación Paper sigue por dentro para evaluar la señal. Las claves y las direcciones de correo no están en el repositorio.

**Informe del proyecto final:** [`Informe_Proyecto_Final_Agente_IA.md`](Informe_Proyecto_Final_Agente_IA.md) (o en PDF: [`Informe_Proyecto_Final_Agente_IA.pdf`](Informe_Proyecto_Final_Agente_IA.pdf)).

**Presentación ejecutiva:** [`Presentacion_Ejecutiva_Agente_IA.pdf`](Presentacion_Ejecutiva_Agente_IA.pdf).

**Evaluación frente a la rúbrica:** [`Evaluacion_Rubrica.md`](Evaluacion_Rubrica.md) (qué cumple el sistema, qué se agregó en la v2.3 y por qué no lo demás) · **Análisis complementario:** [`Analisis_Complementario.md`](Analisis_Complementario.md) (métricas completas, líneas base, costos, régimen y deriva).

---

## Cumplimiento de la entrega

| Indicación de la entrega | Dónde se cumple |
|---|---|
| 1. Presentación ejecutiva del sistema | [`Presentacion_Ejecutiva_Agente_IA.pdf`](Presentacion_Ejecutiva_Agente_IA.pdf) |
| 2. Git con el código del sistema | Este repositorio: [`agente/backend/`](agente/backend/) (FastAPI), [`agente/frontend/`](agente/frontend/) (React + TypeScript), modelos, notebooks y datos |
| 3. README completo con versiones y avances | Este archivo: [Versiones de la app](#versiones-de-la-app) y [Avances del proyecto](#avances-del-proyecto); detalle en [`agente/CHANGELOG.md`](agente/CHANGELOG.md) |
| 4. Datos reales de MEXC | [Datos reales de MEXC](#datos-reales-de-mexc): velas diarias, reglas del par y precio actual leídos de la API pública de MEXC |
| 5. Operaciones y PnL | [Operaciones y PnL](#operaciones-y-pnl): operaciones y PnL de la simulación interna con la que se evalúa la señal. En la interfaz, pestaña **PnL simulado** (v2.1), marcada como simulación con capital virtual (no son compras reales); diseño de la pestaña en la [captura de la v1.9](agente/evidencia/capturas/02_operaciones_paper.png) |
| Indicación del 26 nov: quitar saldos y avisar cuándo se puede comprar a mano | [Laboratorio de señales y avisos por correo](#laboratorio-de-señales-y-avisos-por-correo-v20) (v2.0) |

---

## Laboratorio de señales y avisos por correo (v2.0)

Desde el 26 nov 2026 el sistema funciona como **laboratorio**: no compra ni maneja saldos, y avisa cuándo se podría comprar.

1. Cada día, después del cierre de la vela de 00:00 UTC, analiza los 15 pares con su modelo LSTM y los controles de riesgo.
2. Si la estrategia del modelo de un activo **compra**, llega un correo con el activo, la vela, el cierre, el pronóstico frente a su umbral δ y un stop móvil sugerido. Si después **vende** (por señal del modelo o por stop), llega el aviso de venta con el motivo.
3. El usuario decide si compra o vende a mano en MEXC. El LLM no dispara avisos: en vivo no aportó valor (ver resultados).

Ejemplo del aviso (formato real, con las cifras de LTC del 25 nov):

```
Asunto: Laboratorio DL · señal de COMPRA en LTCUSDT (vela 2026-11-25)

Laboratorio DL · señal de COMPRA
LTCUSDT · vela 2026-11-25 (UTC)
Cierre: 42.80 USDT
Pronóstico del modelo: +0.197 % (umbral 0.086 %)
Stop móvil sugerido: 39.98 USDT.
Operación manual opcional en MEXC. El laboratorio no envía órdenes.
```

**Primer aviso real** (vela del 26 nov, ciclo de las 7:04 pm, hora de México): la estrategia del modelo compró ZECUSDT a 682.27 y el correo llegó con el stop móvil sugerido de 602.52 (remitente oculto en la captura).

![Correo de señal de compra de ZECUSDT, vela 2026-11-26](agente/evidencia/capturas/08_correo_senal_ZEC_vela26.png)

- **Servicio:** correo por Gmail (SMTP con TLS) con una contraseña de aplicación. Configuración en [`agente/README.md`](agente/README.md#avisos-por-correo-v20). Primero se intentó WhatsApp; se cambió a correo porque el bot gratuito (CallMeBot) tenía el cupo lleno y la API de Meta necesita una plantilla aprobada. El código de WhatsApp se conserva como alternativa deshabilitada.
- **Seguridad:** el usuario, la contraseña de aplicación y el destino solo viven en `agente/.env`; el backend solo se conecta a servidores SMTP permitidos con TLS y nunca guarda la contraseña ni las direcciones completas en la bitácora.
- **Sin duplicados ni efectos en el ciclo:** cada aviso se guarda en la base del activo y no se repite para la misma vela; si el correo falla, el agente sigue igual y lo registra.
Pestaña **Señales** de la v2.2 (27 nov): un activo a la vez, aquí TRX, con su acción de hoy, pronóstico frente a δ, distancia a la SMA20, volatilidad, señal activa y la gráfica de precio con SMA20, SMA50 y Bandas de Bollinger. Debajo siguen el pronóstico por ciclo, el RSI, la tabla de indicadores financieros y el historial de señales y avisos del activo.

![Pestaña Señales de la v2.2, TRXUSDT](agente/evidencia/capturas/10_pestana_senales_v22.png)

Pestaña **Señales** de la v2.1 (antes de mostrar un activo a la vez), después del ciclo del 26 nov: ZEC con señal de compra y aviso enviado; LTC y BCH con señales activas (precio de entrada y stop sugerido); abajo, el historial de avisos.

![Pestaña Señales de la v2.1, vela 2026-11-26](agente/evidencia/capturas/09_pestana_senales_v21.png)

- **Interfaz:** nueva pestaña **Señales** con las señales del día, las señales activas, el estado de los avisos (con aviso de prueba) y el historial de avisos. Se quitaron los saldos de la barra, del Resumen y de Estrategia; desde la v2.1 la pestaña **PnL simulado** muestra la evaluación de la señal, con un aviso de que no son compras reales ni saldos de una cuenta.

---

## Evaluación de la señal en vivo (simulación interna, 15 activos, datos al 26 nov 2026)

El laboratorio no compra, pero el protocolo (bloque 16) pide comparar la estrategia sin LLM, con LLM y comprar y mantener. Para eso se conserva la simulación Paper por dentro. Cada activo tiene tres carteras simuladas de 50,000 USDT con el mismo periodo y costos:

| Cartera | Saldo final (USDT) | PnL neto (USDT) | Rendimiento neto | Drawdown máx. | Órdenes | Win Rate |
|---|---|---|---|---|---|---|
| Sin LLM (estrategia del modelo + riesgo) | 754,536.87 | **+4,536.87** | **+0.60 %** | −0.93 % | 14 | 80 % (4 de 5) |
| Con LLM (propuesta del LLM + el mismo riesgo) | 706,813.40 | **−43,186.60** | **−5.76 %** | −7.47 % | 34 | 0 % (0 de 10) |
| Comprar y mantener | 716,353.46 | **−33,646.54** | **−4.49 %** | −7.04 % | 15 | — |

Capital virtual inicial: 750,000 USDT por cartera (15 activos × 50,000). Costo 0 %, como pide el protocolo. Son cifras simuladas: nadie compró nada.

En este periodo el LLM no aportó valor:
- Nunca propuso vender.
- Propuso comprar sin señal del modelo en 21 de 129 ciclos.
- Todas sus salidas fueron por stop.

El motor de riesgo lo contuvo: rechazó 22 compras no permitidas y forzó 10 ventas por stop. El detalle por activo y el análisis de las justificaciones del LLM están en el [informe](Informe_Proyecto_Final_Agente_IA.md).

**Meta de +20 %:** no se alcanzó; los periodos evaluados fueron bajistas y el protocolo solo permite comprar o estar en efectivo. Lo que sí se logró:
- El modelo profundo superó a la regresión lineal: en TE, −3.25 % frente a −27.98 %, con un RMSE menor.
- Protegió el capital frente a comprar y mantener: −3.25 % frente a −31.57 % en TE de BTC, mejor en 12 de 15 activos.
- En vivo, la cartera del modelo fue la única positiva (+0.60 %).

Ver la sección 10 del [informe](Informe_Proyecto_Final_Agente_IA.md).

### Capturas de la interfaz

Las capturas de la pestaña **Señales** (v2.2 y v2.1) y la del aviso por correo están en la sección [Laboratorio de señales](#laboratorio-de-señales-y-avisos-por-correo-v20). Las de abajo son de la v1.9 (25 nov); su pestaña Operaciones es la que en la v2.1 se llama **PnL simulado**, ahora con el aviso de que son cifras simuladas.

| Operaciones (v1.9, 15 activos, modo Paper) | Cerebro (flujo de módulos) |
|---|---|
| ![Operaciones](agente/evidencia/capturas/02_operaciones_paper.png) | ![Cerebro](agente/evidencia/capturas/05_sistema_cerebro.png) |
| **Control humano, observación y propuesta del LLM** | **Red neuronal en vivo** |
| ![Resumen](agente/evidencia/capturas/01_resumen_control_y_propuesta.png) | ![Red neuronal](agente/evidencia/capturas/06_red_neuronal.png) |

Más capturas (decisiones y órdenes, salud del sistema, auditoría y bitácora) en [`agente/evidencia/capturas/`](agente/evidencia/capturas/).

---

## Datos reales de MEXC

El backend consume la API pública de MEXC (`https://api.mexc.com`), sin clave de trading:

| Endpoint | Uso | Dónde se ve |
|---|---|---|
| `GET /api/v3/klines` | Velas diarias cerradas (00:00 UTC) de los 15 pares: entrada del modelo, SMA20, volatilidad y precio de ejecución Paper | Pestañas Resumen, Mercado, Escáner y Estrategia; columna `fecha_vela` de [`ciclos.csv`](agente/registros/ciclos.csv) |
| `GET /api/v3/exchangeInfo` | Paso de cantidad, precisión y monto mínimo de cada par, que respeta el simulador | Validación de cada orden Paper |
| `GET /api/v3/ticker/price` | Precio actual de los 15 pares (en caché 30 s), solo informativo | Pestaña PnL simulado (precio actual y PnL a precio actual) |
| `GET /api/v3/ping`, `GET /api/v3/time` | Salud de la conexión y hora del servidor | Sistema → Salud |

Cada ciclo guarda la fecha de la vela usada y la antigüedad del dato; si el dato tiene más de 26 h, el agente no opera.

**Cuenta demo de MEXC:** pendiente de revisión con el profesor. La API de MEXC no ofrece cuenta de prueba (sandbox): se conecta directo a la cuenta real, y la demo de MEXC solo existe en la web de futuros. Por eso, y porque el protocolo pide no enviar órdenes reales, las compras y ventas se ejecutan en el simulador Paper propio con precios reales de MEXC.

---

## Operaciones y PnL

> **No son compras reales.** Son las operaciones de la **simulación interna** con la que se evalúa la señal: lo que habría pasado al seguir cada señal con un capital virtual de 50,000 USDT por activo y precios reales de MEXC. El laboratorio no compra ni vende; solo avisa por correo.

En la interfaz se ven en la pestaña **PnL simulado** (v2.1; antes Operaciones), que lo indica con un aviso al inicio. Abre en la cartera Sin LLM, que es la que dispara los avisos. Los datos también están en [`agente/registros/`](agente/registros/) y en la API (`GET /api/operaciones`). La pestaña suma los 15 activos de la cartera elegida y muestra:
- saldo total, PnL neto, PnL realizado y no realizado, efectivo e invertido;
- posiciones abiertas, con fecha y precio de compra, precio actual de MEXC, stop móvil y PnL;
- historial de operaciones cerradas, con motivo de salida y PnL.

PnL simulado al cierre de la vela del 26 nov 2026 (datos en vivo):

| Cartera | PnL realizado (USDT) | PnL no realizado (USDT) | PnL neto (USDT) |
|---|---|---|---|
| Sin LLM | +1,997.13 | +2,539.74 | **+4,536.87** |
| Con LLM | −45,732.79 | +2,546.19 | **−43,186.60** |
| Comprar y mantener | 0.00 | −33,646.54 | **−33,646.54** |

Operaciones cerradas en vivo:

| Activo | Cartera | Compra | Precio compra | Venta | Precio venta | PnL (USDT) | Salida |
|---|---|---|---|---|---|---|---|
| SOLUSDT | Sin LLM | 17 nov | 75.19 | 20 nov | 68.88 | −4,196.02 | Stop móvil |
| BNBUSDT | Sin LLM | 20 nov | 540.91 | 21 nov | 548.62 | +712.68 | Señal del modelo |
| ETHUSDT | Sin LLM | 20 nov | 1,623.12 | 21 nov | 1,685.70 | +1,927.76 | Señal del modelo |
| ZECUSDT | Sin LLM | 20 nov | 759.52 | 21 nov | 780.22 | +1,362.70 | Señal del modelo |
| ZECUSDT | Sin LLM | 24 nov | 739.71 | 25 nov | 771.25 | +2,190.01 | Señal del modelo |
| BTCUSDT | Con LLM | 14 nov | 64,142.08 | 20 nov | 58,954.52 | −4,043.80 | Stop móvil |
| ETHUSDT | Con LLM | 17 nov | 1,824.97 | 20 nov | 1,623.12 | −5,530.23 | Stop móvil |
| SOLUSDT | Con LLM | 17 nov | 75.19 | 20 nov | 68.88 | −4,196.02 | Stop móvil |
| BNBUSDT | Con LLM | 19 nov | 580.15 | 20 nov | 540.91 | −3,381.86 | Stop móvil |
| NEARUSDT | Con LLM | 19 nov | 3.2077 | 20 nov | 2.8508 | −5,563.18 | Stop móvil |
| ZECUSDT | Con LLM | 19 nov | 894.37 | 20 nov | 759.52 | −7,538.79 | Stop móvil |
| DOTUSDT | Con LLM | 19 nov | 0.7130 | 21 nov | 0.6526 | −4,235.62 | Stop móvil |
| FILUSDT | Con LLM | 19 nov | 0.5766 | 21 nov | 0.5203 | −4,882.07 | Stop móvil |
| TRXUSDT | Con LLM | 19 nov | 0.3105 | 25 nov | 0.3041 | −1,030.59 | Stop móvil |
| ZECUSDT | Con LLM | 21 nov | 780.22 | 26 nov | 682.27 | −5,330.63 | Stop móvil |

Posiciones simuladas abiertas de la cartera Sin LLM al 26 nov: BCH (compra 206.30), LTC (42.80), SOL (70.30) y ZEC (682.27, la señal del primer aviso por correo).

Todas las órdenes (ejecutadas y rechazadas), con fecha, precio, monto y motivo, están en [`ordenes.csv`](agente/registros/ordenes.csv); las operaciones cerradas, incluida la del replay, en [`operaciones_cerradas.csv`](agente/registros/operaciones_cerradas.csv); el saldo diario de cada cartera, en [`serie_patrimonio_total.csv`](agente/registros/serie_patrimonio_total.csv).

---

## Versiones de la app

Cada modificación al programa sube la versión. El número está en [`agente/config/agente.json`](agente/config/agente.json), aparece en la barra superior de la interfaz y se guarda en cada ciclo. Detalle completo en [`agente/CHANGELOG.md`](agente/CHANGELOG.md).

| Versión | Fecha | Cambios principales | Pruebas |
|---|---|---|---|
| v1.0 | 15 nov 2026 | Versión base: backend FastAPI con API key, ensamble LSTM de BTC, LLM local en Ollama detrás de un gateway, motor de riesgo, simulador Paper, SQLite, tres carteras y la interfaz con sus 7 pestañas. Primer ciclo en vivo: vela del 14 nov | 43 |
| v1.1 | 16 nov 2026 | Instancia de demostración separada (`AGENTE_CONFIG`) para probar los nueve errores sin tocar los ciclos en vivo | 44 |
| v1.2 | 16 nov 2026 | Base propia para la demostración de JSON inválido | 44 |
| v1.3 | 17 nov 2026 | Multi-activo: ETH, SOL y XRP con modelo, base, carteras y control propios; huellas SHA-256 de modelos; selector de activo | 62 |
| v1.4 | 17 nov 2026 | XRP retirado tras fallar su primer ciclo (Ollama no respondió); el agente se pausó sin operar | 60 |
| v1.5 | 19 nov 2026 | Límite de 400 tokens en las respuestas del LLM (causa del fallo de XRP); XRP regresa | 68 |
| v1.6 | 19 nov 2026 | Diez activos más elegidos por regla de volumen (14 pares); decimales de precio por activo | 90 |
| v1.7 | 19 nov 2026 | DOT reemplaza al token respaldado por oro elegido por error: 15 pares | 92 |
| v1.8 | 20 nov 2026 | Pestaña Operaciones rediseñada: saldo total, PnL, posiciones abiertas, historial y precio actual de MEXC | 96 |
| v1.9 | 20 nov 2026 | Botón «Rearmar todos los bloqueados» y regla diaria de rearme del límite de pérdida | 97 |
| v2.0 | 26 nov 2026 | **Laboratorio de señales:** avisos por correo cuando el modelo compra o vende (WhatsApp queda como alternativa); pestaña Señales; la interfaz ya no muestra saldos (indicación del profesor). La simulación sigue por dentro solo para evaluar | 119 |
| v2.1 | 26 nov 2026 | Pestaña **PnL simulado** (la antigua Operaciones) para presentar operaciones y PnL, marcada como simulación con capital virtual: no son compras reales ni saldos de una cuenta. Solo cambia la interfaz | 119 |
| v2.2 | 27 nov 2026 | Por revisión del profesor: **Señales** muestra solo el activo elegido, con gráfica de precio (SMA20, SMA50, Bollinger), pronóstico frente a δ, RSI, tabla de indicadores financieros e historial de su señal y avisos; **Mercado** agrega la comparación de los 15 pares (rendimiento base 100, tabla ordenable y correlaciones). Ruta nueva de solo lectura `GET /api/historial_senal` | 120 |
| **v2.3** | 27 nov 2026 | De la rúbrica del profesor: **plan sugerido** en cada señal (stop, take profit 1.5:1 y tamaño con ½ Kelly de validación) en Señales y en el correo; **análisis complementario** (Sharpe, Sortino, Wilson, líneas base al azar y técnicas, costos, régimen, deriva); **bitácora con hash encadenado**; **CI** en GitHub Actions; diagramas y tabla de la API en el README. No cambia el modelo, las señales ni la simulación | 122 |

---

## Avances del proyecto

| Fecha | Avance |
|---|---|
| 5 nov 2026 | Avance 1 (capítulo 7): descarga de BTC/USDT de MEXC, auditoría, partición TR/VA/TE y referencias. Avance 2 (capítulo 8): MLP y LSTM entrenados en GPU T4 |
| 6 nov 2026 | Avance 3 (capítulo 9): ventanas expansivas y umbrales |
| 7 nov 2026 | Avance 4 (capítulo 10): especificación del entorno del agente y pruebas de abuso |
| 12 nov 2026 | Avance 5 (capítulo 11): indicadores, estrategia D, configuración congelada y evaluación única en TE; informe de la práctica |
| 15 nov 2026 | Agente v1.0; replay histórico de BTC (5–14 nov) y primer ciclo en vivo |
| 16 nov 2026 | Demostración de los nueve escenarios de error (v1.1–v1.2) |
| 17 nov 2026 | Agente multi-activo con ETH, SOL y XRP (v1.3–v1.4) |
| 19 nov 2026 | 15 activos (v1.5–v1.7) |
| 20 nov 2026 | Pestaña Operaciones y rearme de bloqueos (v1.8–v1.9) |
| 14–26 nov 2026 | Ciclos diarios en vivo: 129 ciclos válidos en los 15 activos, más 10 de replay en BTC |
| 25 nov 2026 | Exportación de registros, evidencia de Ollama local y pruebas, capturas, informe final y repositorio público |
| 26 nov 2026 | Presentación ejecutiva; README con versiones, avances, datos de MEXC, operaciones y PnL. Por indicación del profesor, v2.0: laboratorio de señales sin saldos y con avisos por correo. La conexión con la cuenta demo de MEXC queda pendiente (en revisión con el profesor). Primer aviso real por correo (compra de ZEC, vela del 26 nov). v2.1: pestaña PnL simulado. Evaluación frente a la rúbrica del profesor |
| 27 nov 2026 | Revisión del profesor. v2.2: Señales por activo con sus gráficos e indicadores financieros, y Mercado para comparar los 15 pares. v2.3: lo que se pudo agregar de la rúbrica (plan sugerido, análisis complementario, bitácora encadenada y CI) |

Las fechas de los avances de la práctica son las de su ejecución en Colab T4 (UTC), registradas en [`evidencia_t4/`](evidencia_t4/).

---

## Cómo funciona el agente

```
React + TypeScript (5173) ──X-API-Key──▶ Backend FastAPI (127.0.0.1:8000)
     ├─ MEXC API pública: velas diarias (solo lectura; sin rutas de órdenes reales)
     ├─ Un agente por activo: ensamble de 3 LSTM + escaladores versionados
     ├─ Gateway propio (8001) ──X-API-Key──▶ Ollama local (llama3.2:3b)
     ├─ Motor de riesgo determinista (el LLM no puede saltarlo)
     ├─ Simulador Paper (saldo, tamaño mínimo y precisión del par)
     └─ SQLite: ciclos, decisiones, órdenes, patrimonio y eventos
```

Una vez al día, después del cierre de la vela de 00:00 UTC, cada activo:
1. Consulta las velas cerradas de MEXC y valida la fecha y la antigüedad del dato.
2. Calcula los 20 rezagos y obtiene el pronóstico del modelo.
3. Pide al LLM una propuesta en JSON (comprar, mantener o vender) con una justificación breve.
4. Valida la propuesta y aplica los controles de riesgo:
   - límite de exposición;
   - pérdida diaria máxima de 3 %;
   - stop móvil;
   - antigüedad máxima del dato de 26 h.
5. Ejecuta en la simulación Paper interna, guarda todo y muestra la señal en la interfaz.
6. Desde la v2.0, si la estrategia del modelo compra o vende, envía el aviso por correo.

Si falla una dependencia (MEXC, Ollama, clave incorrecta, JSON inválido, dato atrasado, etc.), el agente reintenta con espera creciente y se pausa sin operar. Los nueve escenarios de error del protocolo están demostrados en [`agente/evidencia/demostracion_errores.md`](agente/evidencia/demostracion_errores.md).

### Activos

BTC, ETH, SOL, XRP, BNB, ADA, LTC, TRX, DOGE, MX, FIL, BCH, ZEC, NEAR y DOT contra USDT.
- Cada uno tiene su propio modelo, entrenado y validado con sus datos (TR/VA/TE 70/15/15).
- La estrategia de cada uno (C o D) se eligió con el conjunto de validación.
- Los activos extra se eligieron con una regla de volumen fijada antes de entrenar.

---

## Arquitectura y flujo de decisión

Diagrama de componentes. El navegador solo habla con el backend; el backend es el único que llama a MEXC, al LLM y al correo.

```mermaid
flowchart LR
  subgraph Navegador
    UI["Interfaz React + TypeScript<br/>(Vite, 127.0.0.1:5173)"]
  end
  subgraph Mac["Computadora del usuario"]
    API["Backend FastAPI<br/>127.0.0.1:8000 · X-API-Key"]
    AG["Agente por activo ×15<br/>(ciclo diario)"]
    MOD["Ensambles LSTM<br/>(huellas SHA-256)"]
    RIE["Motor de riesgo<br/>determinista"]
    SIM["Simulador Paper<br/>(evaluación interna)"]
    DB[("SQLite por activo<br/>bitácora")]
    GW["Gateway del LLM<br/>127.0.0.1:8001 · X-API-Key"]
    OLL["Ollama local<br/>llama3.2:3b"]
  end
  MEXC[("API pública de MEXC<br/>solo lectura")]
  MAIL[("Gmail SMTP<br/>TLS")]
  UI -- "REST (JSON) cada 5–60 s" --> API
  API --> AG
  AG -- "velas cerradas 1d" --> MEXC
  AG --> MOD
  AG --> GW --> OLL
  AG --> RIE --> SIM --> DB
  AG -- "aviso de compra/venta" --> MAIL
  API --> DB
```

Flujo de decisión de cada ciclo (una vez al día, 5 minutos después del cierre de 00:00 UTC):

```mermaid
flowchart TD
  A["Vela diaria cerrada de MEXC"] --> B{"¿Dato válido y con<br/>menos de 26 h?"}
  B -- no --> X["Pausa sin operar<br/>(evento de error)"]
  B -- sí --> C["20 rezagos, SMA20, vol20"]
  C --> D["Ensamble LSTM:<br/>pronóstico del día siguiente"]
  D --> E{"¿Pronóstico > δ?<br/>(D: y cierre > SMA20)"}
  E -- sí --> F["Señal del modelo: COMPRAR"]
  E -- no --> G["Señal del modelo: efectivo"]
  C --> L["LLM local propone<br/>(JSON validado)"]
  F --> R{"Motor de riesgo:<br/>stop móvil, pérdida diaria,<br/>posición, dato fresco"}
  G --> R
  L --> R
  R -- "veta o fuerza venta" --> S["Acción final por cartera"]
  R -- aprueba --> S
  S --> P["Simulación Paper y bitácora (SQLite)"]
  S --> Q{"¿La señal del modelo<br/>compra o vende?"}
  Q -- sí --> M["Correo con stop, take profit<br/>y tamaño sugeridos"]
  Q -- no --> N["Sin aviso"]
```

### API del backend

Todas las rutas piden la cabecera `X-API-Key` (salvo `/api/salud`) y aceptan `?simbolo=ETHUSDT` cuando son de un activo; la documentación interactiva (OpenAPI) está en `http://127.0.0.1:8000/docs` con el backend corriendo.

| Método y ruta | Qué devuelve o hace |
|---|---|
| `GET /api/salud` | Estado del backend (sin clave) |
| `GET /api/estado` | Estado del activo: último ciclo, decisiones, carteras, riesgo, modelo y versión |
| `GET /api/activos` | Resumen de los 15 activos (selector y tabla) |
| `GET /api/senales` | Señal del modelo de cada activo, señal activa, aviso y niveles sugeridos (stop, take profit, tamaño) |
| `GET /api/historial_senal` | Señal del modelo de un activo en cada ciclo (v2.2) |
| `GET /api/notificaciones` · `POST /api/notificaciones/prueba` | Historial de avisos · envía un aviso de prueba |
| `GET /api/mercado` | Velas de MEXC, SMA20 y órdenes simuladas del activo |
| `GET /api/escaner` | Variables de los 15 pares (caché de 5 min) |
| `GET /api/operaciones` | Operaciones y PnL de la simulación interna (pestaña PnL simulado) |
| `GET /api/decisiones` · `GET /api/ordenes` · `GET /api/patrimonio` · `GET /api/eventos` · `GET /api/metricas` | Bitácora y métricas del activo |
| `GET /api/red` · `GET /api/sistema` · `GET /api/evidencia` · `GET /api/config` | Red neuronal en vivo, salud, evidencia y configuración (sin secretos) |
| `POST /api/agente/iniciar` · `pausar` · `detener` · `liquidar` | Control humano del agente (Detener = kill switch) |
| `POST /api/riesgo/rearmar` · `POST /api/riesgo/rearmar_todos` | Rearme del control de pérdida diaria (acción humana registrada) |
| `POST /api/ciclo` · `POST /api/replay` · `GET /api/replay` | Ciclo manual y replay histórico (separado del vivo) |

No existe ninguna ruta de órdenes reales: `mexc.py` solo permite rutas públicas de lectura y `enviar_orden_real` lanza un error (probado).

## Ejecutarlo

Requisitos: Python 3.13, Node.js y [Ollama](https://ollama.com) con el modelo `llama3.2:3b`. Las instrucciones completas están en [`agente/README.md`](agente/README.md).

```bash
# 1. Entorno de Python y claves (una sola vez, desde esta carpeta)
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r agente/backend/requirements.txt
cp agente/.env.example agente/.env      # dos claves propias y, opcional, los datos del correo para los avisos (ver el archivo)
ollama pull llama3.2:3b

# 2. Gateway del LLM y backend (dos terminales, en agente/backend)
uvicorn gateway.main:app --host 127.0.0.1 --port 8001
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. Interfaz (en agente/frontend)
npm install && npm run dev               # http://127.0.0.1:5173

# Pruebas y registros
cd agente/backend && python -m pytest    # 122 pruebas automatizadas
python agente/exportar_registros.py      # exporta las bases a CSV y calcula las métricas del informe
```

---

## Estructura del repositorio

| Carpeta o archivo | Contenido |
|---|---|
| [`Informe_Proyecto_Final_Agente_IA.md`](Informe_Proyecto_Final_Agente_IA.md) · [`Informe_Proyecto_Final_Agente_IA.pdf`](Informe_Proyecto_Final_Agente_IA.pdf) | Informe del proyecto final (bloques 14–16 del protocolo) |
| [`Presentacion_Ejecutiva_Agente_IA.pdf`](Presentacion_Ejecutiva_Agente_IA.pdf) | Presentación ejecutiva del sistema |
| [`Evaluacion_Rubrica.md`](Evaluacion_Rubrica.md) | Evaluación del sistema frente a la rúbrica del profesor (26 nov) y justificación de lo que no se agregó |
| [`agente/`](agente/) | El agente: `backend/` (FastAPI + gateway de Ollama + pruebas), `frontend/` (React + TypeScript), `config/` (configuración de riesgo, LLM, activos y avisos), [`README.md`](agente/README.md) y [`CHANGELOG.md`](agente/CHANGELOG.md) (versiones v1.0 a v2.3) |
| [`agente/registros/`](agente/registros/) | Registros del agente en CSV (ciclos, decisiones, órdenes, patrimonio y eventos) y métricas calculadas |
| [`agente/evidencia/`](agente/evidencia/) | Verificación de los modelos en la computadora local, replay histórico de BTC y demostración de los nueve errores |
| [`notebooks/`](notebooks/) | Notebooks de Colab: avances de la práctica (`practica/`) y entrenamiento de los activos extra |
| [`modelos/`](modelos/) | Modelos y escaladores de la práctica (BTC); el agente usa los de `modelos/cap11/` |
| [`activos_extra/`](activos_extra/), [`activos_extra_lote2/`](activos_extra_lote2/), [`activos_extra_lote3/`](activos_extra_lote3/) | Modelos, escaladores, resultados y figuras de los 14 activos extra |
| [`datos/`](datos/), [`resultados/`](resultados/), [`figuras/`](figuras/), [`evidencia_t4/`](evidencia_t4/), [`bitacora/`](bitacora/) | Datos de MEXC, resultados, figuras, evidencia del entrenamiento en GPU T4 y bitácora de la práctica |
| [`Informe/`](Informe/) | Informe final de la práctica y anexos |

---

## Dónde está cada entregable del protocolo

### Práctica (avances 1 a 5, capítulos 7 a 11)

Los notebooks conservan sus salidas y se pueden abrir en Colab (solo lectura) desde los enlaces.

| Avance | Notebook | Abrir en Colab | Resultados principales |
|---|---|---|---|
| 1 · Capítulo 7: datos, partición y referencias | [`DLF_Cap08_Avance1.ipynb`](notebooks/practica/DLF_Cap08_Avance1.ipynb) | [Colab](https://colab.research.google.com/github/prisfig/agente_dl/blob/main/notebooks/practica/DLF_Cap08_Avance1.ipynb) | [`ficha_activo.json`](resultados/ficha_activo.json), [`diccionario_datos.csv`](resultados/diccionario_datos.csv), [`auditoria_datos.csv`](resultados/auditoria_datos.csv), [`particiones.csv`](resultados/particiones.csv), [`comparacion_modelos_cap7_VA.csv`](resultados/comparacion_modelos_cap7_VA.csv), [`hipotesis_tecnica.json`](resultados/hipotesis_tecnica.json) |
| 2 · Capítulo 8: MLP y LSTM en T4 | [`DLF_Cap08_Avance2.ipynb`](notebooks/practica/DLF_Cap08_Avance2.ipynb) | [Colab](https://colab.research.google.com/github/prisfig/agente_dl/blob/main/notebooks/practica/DLF_Cap08_Avance2.ipynb) | [`busqueda_configuraciones_cap8.csv`](resultados/busqueda_configuraciones_cap8.csv), [`resumen_semillas_cap8.csv`](resultados/resumen_semillas_cap8.csv), [`seleccion_cap8.json`](resultados/seleccion_cap8.json), curvas en [`figuras/`](figuras/) |
| 3 · Capítulo 9: ventanas expansivas y umbrales | [`DLF_Cap09_Avance3.ipynb`](notebooks/practica/DLF_Cap09_Avance3.ipynb) | [Colab](https://colab.research.google.com/github/prisfig/agente_dl/blob/main/notebooks/practica/DLF_Cap09_Avance3.ipynb) | [`ventanas_expansivas_cap9.csv`](resultados/ventanas_expansivas_cap9.csv), [`errores_por_ventana_cap9.csv`](resultados/errores_por_ventana_cap9.csv), [`umbrales_probados_cap9_VA.csv`](resultados/umbrales_probados_cap9_VA.csv), [`regla_seleccionada_cap9.json`](resultados/regla_seleccionada_cap9.json), [`diferenciacion_fraccionaria_TR_cap9.csv`](resultados/diferenciacion_fraccionaria_TR_cap9.csv) |
| 4 · Capítulo 10: entorno del agente | [`DLF_Cap10_Avance4.ipynb`](notebooks/practica/DLF_Cap10_Avance4.ipynb) | [Colab](https://colab.research.google.com/github/prisfig/agente_dl/blob/main/notebooks/practica/DLF_Cap10_Avance4.ipynb) | [`especificacion_entorno_cap10.json`](resultados/especificacion_entorno_cap10.json), [`transicion_manual_cap10.csv`](resultados/transicion_manual_cap10.csv), [`pruebas_abuso_entorno_cap10.csv`](resultados/pruebas_abuso_entorno_cap10.csv) |
| 5 · Capítulo 11: indicadores, TE y pronóstico futuro | [`DLF_Cap11_Avance5.ipynb`](notebooks/practica/DLF_Cap11_Avance5.ipynb) | [Colab](https://colab.research.google.com/github/prisfig/agente_dl/blob/main/notebooks/practica/DLF_Cap11_Avance5.ipynb) | [`comparacion_A_vs_B_VA_cap11.csv`](resultados/comparacion_A_vs_B_VA_cap11.csv), [`comparacion_C_D_VA_cap11.csv`](resultados/comparacion_C_D_VA_cap11.csv), [`indicadores_documentacion_cap11.csv`](resultados/indicadores_documentacion_cap11.csv), [`resultados_finales_TR_VA_TE.csv`](resultados/resultados_finales_TR_VA_TE.csv) |

| Entregable de la carpeta de entrega (sección 10) | Archivo |
|---|---|
| Datos originales y procesados | [`datos/originales/`](datos/originales/), [`datos/procesados/`](datos/procesados/) |
| Evidencia de entrenamiento en T4 (`nvidia-smi`, dispositivo, versiones) | [`evidencia_t4/`](evidencia_t4/) |
| Modelo final y escaladores | [`modelos/cap11/`](modelos/cap11/), [`configuracion_final_congelada.json`](resultados/configuracion_final_congelada.json) |
| `experimentos.csv` | [`resultados/experimentos.csv`](resultados/experimentos.csv) |
| `predicciones_TE.csv` | [`resultados/predicciones_TE.csv`](resultados/predicciones_TE.csv) |
| `prediccion_futura.csv` | [`resultados/prediccion_futura.csv`](resultados/prediccion_futura.csv) |
| `simulacion.csv` | [`resultados/simulacion.csv`](resultados/simulacion.csv), con el resumen en [`resultados_trading_TE.csv`](resultados/resultados_trading_TE.csv) |
| Cuatro fallos provocados y bitácora de errores | [`pruebas_controladas_errores.csv`](resultados/pruebas_controladas_errores.csv), [`bitacora/bitacora_errores.csv`](bitacora/bitacora_errores.csv) |
| Informe de la práctica y anexos | [`Informe/`](Informe/) |

### Proyecto final (bloques 14 a 16)

| Requisito | Dónde |
|---|---|
| Frontend React + TypeScript | [`agente/frontend/`](agente/frontend/); capturas en [`agente/evidencia/capturas/`](agente/evidencia/capturas/) |
| Backend autenticado (FastAPI) y gateway de Ollama con API key | [`agente/backend/`](agente/backend/) |
| LLM realmente local (modelo, versión, hardware, tiempo, consulta sin internet) | [`agente/evidencia/ollama_local.txt`](agente/evidencia/ollama_local.txt) |
| README de instalación y ejecución | [`agente/README.md`](agente/README.md) |
| `.env.example` sin valores | [`agente/.env.example`](agente/.env.example) |
| Modelo y escalador versionados | Rutas y huellas en [`agente/config/agente.json`](agente/config/agente.json); verificación en [`agente/evidencia/`](agente/evidencia/) |
| Configuración del LLM y de riesgo | [`agente/config/agente.json`](agente/config/agente.json) |
| Base o exportación de registros | [`agente/registros/`](agente/registros/) |
| Pruebas automatizadas de controles | [`agente/backend/tests/`](agente/backend/tests/); salida en [`agente/evidencia/pytest_resultado.txt`](agente/evidencia/pytest_resultado.txt) |
| Al menos 20 ciclos válidos (replay separado) | [`agente/registros/ciclos.csv`](agente/registros/ciclos.csv) (columna `modo`) y [`agente/evidencia/replay_v2_2026-11-05_a_14.csv`](agente/evidencia/replay_v2_2026-11-05_a_14.csv) |
| Nueve errores demostrados | [`agente/evidencia/demostracion_errores.md`](agente/evidencia/demostracion_errores.md) |
| Comparación sin LLM / con LLM / comprar y mantener | [`Informe_Proyecto_Final_Agente_IA.md`](Informe_Proyecto_Final_Agente_IA.md) y [`agente/registros/metricas_por_activo.csv`](agente/registros/metricas_por_activo.csv) |
| Informe breve | [`Informe_Proyecto_Final_Agente_IA.md`](Informe_Proyecto_Final_Agente_IA.md) · [`Informe_Proyecto_Final_Agente_IA.pdf`](Informe_Proyecto_Final_Agente_IA.pdf) |

---

## Práctica: modelo de pronóstico de BTC/USDT

- **Datos:** velas diarias de BTC/USDT de MEXC, de septiembre de 2018 a noviembre de 2026.
- **División:** entrenamiento (TR), validación (VA) y prueba (TE), en orden cronológico.
- **Modelo final:** ensamble de 3 LSTM (semillas 42, 123 y 2024) con 20 rezagos del rendimiento diario.
- **Estrategia D:** compra si el pronóstico supera δ = 0.0866 % y el cierre está por encima de la SMA20.
- **Congelado antes del TE:** la configuración se fijó con VA y se guardó con su SHA-256 en [`resultados/configuracion_final_congelada.json`](resultados/configuracion_final_congelada.json). El TE se usó una sola vez: −3.25 % frente a −31.57 % de comprar y mantener.

El agente reutiliza ese modelo sin reentrenarlo y comprueba con [`agente/verificar_modelo.py`](agente/verificar_modelo.py) que en esta computadora da las mismas predicciones que en Colab.

---

## Seguridad

- Las claves viven solo en `agente/.env`, que no se sube al repositorio. Se entrega [`agente/.env.example`](agente/.env.example) sin valores.
- La interfaz no guarda claves en el código ni en variables `VITE`.
- Iniciar, detener y cambiar la configuración requieren la clave del backend.
- El LLM no recibe claves, no puede cambiar la configuración y sus acciones no válidas se rechazan.
- No hay ninguna ruta que envíe órdenes reales a MEXC, y no se usa una clave de trading.
- Los avisos solo salen a servidores SMTP permitidos (Gmail) con TLS; el usuario y la contraseña de aplicación viven solo en `agente/.env`.
