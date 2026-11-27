# Evaluación del sistema frente a la rúbrica «Proyecto de App de Trading con IA»

**Actualizado el 27 nov (v2.3).** Después de la revisión del profesor se agregaron, sin cambiar el modelo ni las reglas de la simulación: niveles sugeridos de take profit y tamaño (Kelly fraccional con datos de validación), métricas completas, líneas base al azar y técnicas, sensibilidad a costos, análisis por régimen, monitor de deriva, diagramas de arquitectura y de decisión, tabla de la API, bitácora con hash encadenado e integración continua. Los indicadores marcados abajo ya lo reflejan; lo que sigue faltando conserva su justificación.

El 26 de noviembre de 2026 el profesor compartió la rúbrica «Proyecto de App de Trading con IA» y pidió evaluar si el sistema cumple con ella. También aclaró que no es obligatorio cumplir todo. Este documento revisa cada indicador contra lo que ya está en el repositorio. Donde falta algo, explica por qué **no se agregó** antes de la entrega del 27 de noviembre.

Versión evaluada: **v2.3** (laboratorio de señales con avisos por correo y pestaña PnL simulado), con datos hasta la vela del 26 nov 2026.

## Por qué no se agregan los puntos que siguen faltando

1. **Las reglas se fijaron antes de ver los resultados.** La estrategia de cada activo (C o D), el umbral δ, el stop y el tamaño se eligieron con el conjunto de validación (VA), y el conjunto de prueba (TE) se usó una sola vez. Cambiar ahora la estrategia (meter un take profit, Kelly o nuevos indicadores en la simulación) sería ajustarla después de conocer el TE y los ciclos en vivo: lo que la rúbrica llama «mirar el futuro». Por eso el take profit y el tamaño de la v2.3 son **sugerencias para la compra manual** (el Kelly usa solo validación) y los indicadores nuevos son de referencia: la simulación evaluada no cambia.
2. **El protocolo del curso fija varias condiciones.** Pide operar solo en un simulador propio (sin órdenes reales), solo compras o efectivo (sin cortos ni apalancamiento), exposición máxima del 100 %, capital de 50,000 USDT por activo y un costo de 0 % en la simulación del agente. Varios indicadores de la rúbrica piden lo contrario (cortos, Kelly, órdenes bracket u OCO con un broker). Se siguió el protocolo, porque es el documento con el que se planeó el proyecto.
3. **La rúbrica es general para todo el grupo.** Menciona acciones, Alpaca, cuentas con margen y velas intradía. Este sistema opera cripto spot en MEXC con velas diarias y una decisión al día, así que algunos indicadores (WebSocket, expiración de órdenes, horario de mercado, costo de préstamo) no cambian ninguna decisión.
4. **No arriesgar lo que ya funciona un día antes.** El agente lleva 129 ciclos en vivo sin errores en 15 activos, con 119 pruebas automatizadas. Cambiar el motor, el esquema de las bases o el modelo la noche anterior a la entrega pondría en riesgo los ciclos y la evidencia ya registrados.

Leyenda: **Cumple**, **Parcial** (está, pero le falta una parte del nivel más alto) y **No** (no está; se explica por qué).

## 1 · App: FrontEnd y BackEnd

| Indicador | Estado | Qué tiene el sistema | Por qué no se completa |
|---|---|---|---|
| Arquitectura | Cumple | Frontend React + TypeScript, backend FastAPI, gateway propio del LLM y MEXC como fuente, en capas separadas; el navegador nunca llama a MEXC. Diagramas Mermaid de componentes y del flujo de decisión en el README (sección «Arquitectura y flujo de decisión») | — |
| FrontEnd | Parcial | Datos en vivo de MEXC; Señales por activo con gráfica de precio (SMA20, SMA50, Bollinger), pronóstico frente a δ, RSI e indicadores; Mercado compara los 15 pares; mensajes de «sin conexión», clave incorrecta y error de la API | No hay gráfico de velas japonesas: el modelo decide solo con cierres diarios. La interfaz está pensada para escritorio |
| BackEnd / API | Cumple | Tabla de rutas en el README y documentación OpenAPI en `/docs`; cada orden simulada se valida (saldo, paso de cantidad y monto mínimo); reintentos con espera creciente; nueve escenarios de error demostrados | — |
| Tiempo real | No | La interfaz consulta al backend cada 5 a 30 s | La señal se calcula una vez al día, 5 minutos después del cierre de 00:00 UTC. Un WebSocket de precios por segundo no cambia ninguna decisión y agrega un punto de falla |
| Seguridad | Cumple | Claves solo en `agente/.env` (fuera de Git); `.env.example` sin valores; gateway del LLM con su propia clave; no existe ninguna ruta de órdenes reales y el bloqueo está probado (`enviar_orden_real` lanza error y las rutas no permitidas se rechazan) | La clave de acceso a la app se escribe en el navegador al entrar y vive solo en esa pestaña. No es una clave del broker: el sistema no usa ninguna clave de MEXC |
| Persistencia y trazabilidad | Cumple | Base SQLite por activo exportada a CSV; **hash encadenado** de toda la bitácora (`agente/bitacora_hash.py`, `registros/cadena_hash.csv`): si se altera una fila, la verificación falla; SHA-256 de la configuración en cada ciclo y de cada modelo al cargarlo | — |
| Calidad y entrega | Parcial | README con instalación, ejecución y pruebas; 122 pruebas; **CI en GitHub Actions** (`.github/workflows/ci.yml`): tipos y compilación de la interfaz, compilación del backend, verificación de la bitácora y pytest en cada push | El arranque usa tres terminales (gateway, backend e interfaz), no un solo comando |

## 2 · Consideraciones financieras

| Indicador | Estado | Qué tiene el sistema | Por qué no se completa |
|---|---|---|---|
| Velas y datos | Cumple | Velas diarias OHLCV de MEXC; solo velas cerradas de 00:00 UTC; antigüedad máxima de 26 h; validación de fechas y de orden; no se rellenan velas perdidas | — |
| Análisis técnico | Parcial | SMA20 (filtro de la estrategia D) y volatilidad de 20 días (stop) en el modelo; en la interfaz, además, SMA50, Bandas de Bollinger, RSI (14) y ATR (14), cada uno con su lectura y marcado como referencia | Los indicadores de referencia no tienen pruebas automatizadas propias ni entran al modelo, porque no se validaron en la práctica |
| Métricas de desempeño | Cumple | Rendimiento neto, drawdown, Win Rate con **intervalo de Wilson**, **Sharpe**, **Sortino**, **expectativa por operación**, profit factor, operaciones, exposición, acciones rechazadas y latencia ([`Analisis_Complementario.md`](Analisis_Complementario.md)) | — |
| Costos | Cumple | TE con comisión de 0.10 % y **sensibilidad** a comisión de 0 a 0.30 % y deslizamiento de 0.05 %, con el **costo de equilibrio** (0.036 % por operación) | En vivo el costo es de 0 % por protocolo |
| Stop Loss y Take Profit | Cumple | Cada señal trae stop (2 × vol20) y **take profit sugerido** con relación 1.5:1 sobre el stop, en la pestaña Señales y en el correo | La simulación del protocolo sigue saliendo por señal o stop; el take profit es para la compra manual |
| Tamaño de posición (Kelly) | Cumple | **Tamaño sugerido = ½ Kelly** con el acierto de la estrategia de cada activo en **validación**, tope de 25 % y mínimo de 15 operaciones; si el Kelly sale negativo, sugiere 0 % (BTC, LTC y BCH) | La simulación conserva la exposición de 100 % que fija el protocolo |
| Gestión de riesgo | Parcial | Pérdida diaria máxima de 3 % con bloqueo de compras y rearme manual registrado; botón Detener (kill switch) que bloquea nuevas órdenes; stop móvil; antigüedad máxima del dato; una sola posición por activo; validación de acciones | No hay límite de drawdown total ni de racha de pérdidas. Los límites se fijaron en la configuración antes de la prueba y no se cambian a mitad de ella |

## 3 · Aprendizaje (ML / DL) y predicciones

| Indicador | Estado | Qué tiene el sistema | Por qué no se completa |
|---|---|---|---|
| Problema y objetivo | Cumple | El modelo pronostica el rendimiento del día siguiente, y la regla de trading compra solo si ese pronóstico supera el umbral δ elegido en VA | — |
| Datos y features | Cumple | 20 rezagos del rendimiento diario, calculados solo con datos pasados; escaladores ajustados solo con el entrenamiento; fuente, periodo y partición documentados (`ficha_activo.json`, `particiones.csv`) | — |
| Validación | Parcial | Partición cronológica TR/VA/TE; ventanas expansivas en el capítulo 9; TE usado una sola vez; el Kelly sugerido usa solo VA | No se dejaron días de separación entre entrenamiento y prueba: exige reentrenar y usar de nuevo el TE |
| Comparación con línea base | Cumple | Regresión lineal, SGD, media, pronóstico cero, comprar y mantener, **regla técnica pura (cierre > SMA20)**, **cruce de medias** y **operar al azar** con la misma exposición (10,000 permutaciones: la estrategia D supera al 94 %, p = 0.06). Hallazgo reportado: en el TE de BTC la estrategia D coincidió con la regla técnica pura | — |
| Modelos (ML y DL) | Cumple | ML clásico (regresión lineal y SGD) frente a DL (MLP y LSTM), comparados en los capítulos 7 y 8; se eligió el ensamble de 3 LSTM por su desempeño en VA | — |
| Calibración y probabilidad | No | El modelo da un rendimiento esperado, no una probabilidad; el umbral δ para operar se eligió en VA (capítulo 9) | El modelo es de regresión. Convertirlo en un clasificador con probabilidades calibradas exige entrenar otro modelo y usar de nuevo el TE |
| Del modelo al PnL | Cumple | Simulación del TE con comisiones; **monitor de deriva** (RMSE en vivo frente al del TE y acierto direccional por activo) y **regla de reentrenamiento** escrita | Con 7 a 12 ciclos evaluados por activo la muestra es corta |

## 4 · IA como cerebro de operaciones

| Indicador | Estado | Qué tiene el sistema | Por qué no se completa |
|---|---|---|---|
| Arquitectura de agentes | No | Un LLM local (`llama3.2:3b`) propone; el modelo LSTM y el motor de riesgo deciden | El protocolo pide un LLM local que proponga en JSON. La Mac del proyecto (8 GB) tarda unos 12 s por consulta, así que varios agentes LLM por activo no caben en el ciclo diario. Además, el LLM no aportó valor en vivo (sección 8 del informe), así que multiplicarlo no tiene sentido |
| Salida estructurada | Parcial | JSON con esquema validado (formato restringido de Ollama y validación con Pydantic), temperatura 0, semilla fija y reintentos | No hay campo de confianza de 0 a 1. Los campos son los que define el protocolo: acción, símbolo, fecha de la vela y justificación |
| Jerarquía y vetos | Cumple | El motor de riesgo determinista tiene la última palabra: rechazó 22 compras no permitidas del LLM y forzó 10 ventas por stop. El LLM no puede cambiar tamaños, límites ni configuración, y no existe ninguna ruta de órdenes reales | — |
| Robustez | Parcial | Tiempo máximo de 90 s, reintentos con espera creciente, límite de 400 tokens y modelo local | Si el LLM falla, el ciclo de ese activo se pausa sin operar, en lugar de seguir con una decisión de respaldo. Es lo que piden los escenarios de error del protocolo (Ollama detenido, JSON inválido) |
| Trazabilidad (Reflejo) | Parcial | Cada decisión guarda la observación completa (rezagos, pronóstico, SMA20, volatilidad), la propuesta, la justificación, los motivos del riesgo y la acción final; pestaña Auditoría; detector de números inventados | No hay evidencia por agente ni acuerdos o conflictos, porque hay un solo agente |
| Aprendizaje de pesos | No | — | No aplica: no hay varios agentes que ponderar |
| Seguridad del prompt | Parcial | El prompt está en el código y se versiona con la app; los datos externos se tratan como datos; las herramientas del LLM son de solo lectura; el LLM no recibe claves | No hay un filtro de instrucciones peligrosas, porque el prompt solo recibe números de MEXC y del modelo, no texto externo |

## 5 · Trading: Entry, Long y Short

| Indicador | Estado | Qué tiene el sistema | Por qué no se completa |
|---|---|---|---|
| Tesis de la estrategia | Cumple | Seguir el impulso de corto plazo con filtro de tendencia; **análisis por régimen** en el TE de BTC: en régimen alcista +3.91 % (comprar y mantener +4.73 %), en bajista −1.93 % frente a −37.00 %. Funciona como protección en mercados bajistas | — |
| Entry | Parcial | Condiciones objetivas y medibles (pronóstico > δ, cierre > SMA20 en D); orden a mercado al cierre diario, que en MEXC es igual a la apertura siguiente | No hay órdenes límite ni expiración, porque se decide una vez al día con la vela cerrada |
| Long | Cumple | Señal, confirmación (SMA20 en la estrategia D), stop móvil y take profit sugerido | Sin tiempo máximo en la posición |
| Short | Cumple | Solo compras, justificado: cripto spot sin préstamo de activos y un protocolo que permite solo compras o efectivo | — |
| Salidas | Parcial | Señal contraria, stop móvil con prioridad sobre la señal y el LLM, y take profit sugerido para la compra manual | Sin tiempo máximo |
| Ejecución | Parcial | Órdenes simuladas a mercado, redondeadas al paso del par, con monto mínimo y saldo; el aviso trae stop y take profit para armar la orden a mano | No hay órdenes bracket u OCO porque no hay broker: el protocolo prohíbe órdenes reales y la demo de MEXC sigue en revisión |
| Consistencia backtest ↔ paper | Parcial | Las mismas reglas y el mismo modelo en el TE y en vivo; el modelo de BTC da en la Mac las mismas predicciones que en Colab (diferencia máxima 7.2e-10 en 444 pronósticos) | El deslizamiento real no se puede medir, porque no hay ejecución real |

## Lista de verificación de la rúbrica

| Punto | Estado |
|---|---|
| Las claves no aparecen en el repositorio ni en el navegador | Cumple. Las claves están solo en `.env`; en el navegador solo se escribe la clave de acceso a la app, que no se guarda en el código |
| La app rechaza el endpoint real | Cumple. No existe ruta de órdenes reales y el bloqueo está probado |
| Ninguna decisión usa la vela en curso ni datos futuros | Cumple. Solo velas cerradas, con antigüedad máxima de 26 h |
| Toda operación tiene SL, TP y tamaño calculado antes de entrar | Cumple en cada aviso: stop, take profit y tamaño sugeridos. La simulación interna usa stop y el tamaño del protocolo |
| Las métricas incluyen comisiones y deslizamiento | Cumple. TE con 0.10 % y sensibilidad con deslizamiento en `Analisis_Complementario.md`; en vivo, 0 % por protocolo |
| El modelo supera a una línea base fuera de muestra | Cumple. En TE supera a la regresión lineal y a comprar y mantener |
| La IA no puede enviar órdenes ni saltar el riesgo | Cumple |
| Cada decisión se puede reconstruir desde la bitácora | Cumple. Observación, propuesta, motivos y acción final de cada ciclo en SQLite y CSV |

## Entregables de la rúbrica

| Entregable | Dónde está |
|---|---|
| Repositorio Git con README, `.env.example` y CI | [README](README.md), [`agente/.env.example`](agente/.env.example) y [CI](.github/workflows/ci.yml) |
| Diagrama de arquitectura y del flujo de decisión | Diagramas Mermaid en el README («Arquitectura y flujo de decisión») |
| Informe de la estrategia | [Informe del proyecto final](Informe_Proyecto_Final_Agente_IA.md) e [informe de la práctica](Informe/) |
| Notebook o reporte del modelo | [Notebooks de la práctica](notebooks/practica/): validación temporal y líneas base; sin calibración (ver arriba) |
| Demo en vivo en paper con una decisión trazada | Se puede hacer en clase con la interfaz: cada decisión se sigue en las pestañas Señales, Estrategia y Auditoría, desde la vela de MEXC hasta el aviso por correo |
