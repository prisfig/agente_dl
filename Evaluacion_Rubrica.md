# Evaluación del sistema frente a la rúbrica «Proyecto de App de Trading con IA»

El 26 de noviembre de 2026 el profesor compartió la rúbrica «Proyecto de App de Trading con IA» y pidió evaluar si el sistema cumple con ella. También aclaró que no es obligatorio cumplir todo. Este documento revisa cada indicador contra lo que ya está en el repositorio. Donde falta algo, explica por qué **no se agregó** antes de la entrega del 27 de noviembre.

Versión evaluada: **v2.1** (laboratorio de señales con avisos por correo y pestaña PnL simulado), con datos hasta la vela del 26 nov 2026.

## Por qué no se agregan ahora los puntos que faltan

1. **Las reglas se fijaron antes de ver los resultados.** La estrategia de cada activo (C o D), el umbral δ, el stop y el tamaño se eligieron con el conjunto de validación (VA), y el conjunto de prueba (TE) se usó una sola vez. Agregar ahora un take profit, Kelly o nuevos indicadores cambiaría la estrategia después de conocer el TE y los ciclos en vivo. Eso es lo que la rúbrica llama «mirar el futuro», y los resultados dejarían de ser fuera de muestra.
2. **El protocolo del curso fija varias condiciones.** Pide operar solo en un simulador propio (sin órdenes reales), solo compras o efectivo (sin cortos ni apalancamiento), exposición máxima del 100 %, capital de 50,000 USDT por activo y un costo de 0 % en la simulación del agente. Varios indicadores de la rúbrica piden lo contrario (cortos, Kelly, órdenes bracket u OCO con un broker). Se siguió el protocolo, porque es el documento con el que se planeó el proyecto.
3. **La rúbrica es general para todo el grupo.** Menciona acciones, Alpaca, cuentas con margen y velas intradía. Este sistema opera cripto spot en MEXC con velas diarias y una decisión al día, así que algunos indicadores (WebSocket, expiración de órdenes, horario de mercado, costo de préstamo) no cambian ninguna decisión.
4. **No arriesgar lo que ya funciona un día antes.** El agente lleva 129 ciclos en vivo sin errores en 15 activos, con 119 pruebas automatizadas. Cambiar el motor, el esquema de las bases o el modelo la noche anterior a la entrega pondría en riesgo los ciclos y la evidencia ya registrados.

Leyenda: **Cumple**, **Parcial** (está, pero le falta una parte del nivel más alto) y **No** (no está; se explica por qué).

## 1 · App: FrontEnd y BackEnd

| Indicador | Estado | Qué tiene el sistema | Por qué no se completa |
|---|---|---|---|
| Arquitectura | Cumple | Frontend React + TypeScript, backend FastAPI, gateway propio del LLM y MEXC como fuente de datos, en capas separadas. El navegador nunca llama a MEXC. Diagrama de componentes y del ciclo en el README y en la sección 2 del informe | El diagrama es de texto. No se dibujan flujos de WebSocket porque el sistema no usa WebSocket (ver «Tiempo real») |
| FrontEnd | Parcial | Datos en vivo de MEXC y gráficas de líneas; mensajes de «sin conexión», de clave incorrecta y de error de la API; 8 pestañas | No hay gráfico de velas japonesas. El modelo decide solo con cierres diarios, así que una gráfica de velas no cambia ninguna decisión. La interfaz está pensada para escritorio |
| BackEnd / API | Cumple | Rutas documentadas automáticamente en `/docs` (OpenAPI de FastAPI) y descritas en `agente/README.md`; cada orden simulada se valida (saldo, paso de cantidad y monto mínimo del par); reintentos con espera creciente; nueve escenarios de error demostrados | — |
| Tiempo real | No | La interfaz consulta al backend cada 5 a 30 s | La señal se calcula una vez al día, 5 minutos después del cierre de 00:00 UTC. Un WebSocket de precios por segundo no cambia ninguna decisión y agrega un punto de falla |
| Seguridad | Cumple | Claves solo en `agente/.env` (fuera de Git); `.env.example` sin valores; gateway del LLM con su propia clave; no existe ninguna ruta de órdenes reales y el bloqueo está probado (`enviar_orden_real` lanza error y las rutas no permitidas se rechazan) | La clave de acceso a la app se escribe en el navegador al entrar y vive solo en esa pestaña. No es una clave del broker: el sistema no usa ninguna clave de MEXC |
| Persistencia y trazabilidad | Parcial | Base SQLite por activo con ciclos, decisiones, órdenes, patrimonio, eventos y avisos; exportación completa a CSV (`agente/registros/`); SHA-256 de la configuración en cada ciclo y huellas SHA-256 de cada modelo al cargarlo | No hay hash encadenado. Cada decisión ya se puede reconstruir desde la bitácora, y agregar la cadena cambiaría el esquema de 15 bases con ciclos en vivo un día antes de la entrega |
| Calidad y entrega | Parcial | README con instalación, ejecución y pruebas; 119 pruebas automatizadas con su salida en `agente/evidencia/pytest_resultado.txt`; historial de versiones v1.0 a v2.1 | No hay CI. Las pruebas cargan TensorFlow y los modelos, y se corren en la Mac del proyecto; un CI en GitHub requeriría preparar ese entorno en la nube. El arranque usa tres terminales (gateway, backend e interfaz), no un solo comando |

## 2 · Consideraciones financieras

| Indicador | Estado | Qué tiene el sistema | Por qué no se completa |
|---|---|---|---|
| Velas y datos | Cumple | Velas diarias OHLCV de MEXC; solo velas cerradas de 00:00 UTC; antigüedad máxima de 26 h; validación de fechas y de orden; no se rellenan velas perdidas | — |
| Análisis técnico | Parcial | SMA20 (filtro de tendencia de la estrategia D) y volatilidad de 20 días (base del stop), documentados en el capítulo 11 (`resultados/indicadores_documentacion_cap11.csv`) | No se agregan RSI, MACD, Bollinger ni VWAP. Los indicadores se eligieron y validaron en la práctica; sumar otros ahora sería agregar reglas sin validar |
| Métricas de desempeño | Parcial | Rendimiento neto, drawdown máximo, Win Rate, profit factor, número de operaciones, acciones rechazadas y latencia: las métricas que pide el bloque 16 del protocolo | No se reportan Sharpe ni el intervalo de Wilson. Con 5 operaciones cerradas en la cartera del modelo, el intervalo de Wilson del acierto (4 de 5) va de 38 % a 96 %: tan ancho que no informa |
| Costos | Parcial | El TE se simuló con una comisión de 0.10 % por operación; con esos costos el sistema dio −3.25 % y sin costos +1.91 %. El agente tiene comisión y deslizamiento configurables | En vivo el costo es de 0 %, como fija el protocolo. La ejecución es al cierre diario, que en MEXC es igual a la apertura siguiente, así que no hay deslizamiento observable que medir |
| Stop Loss y Take Profit | Parcial | Stop móvil desde la entrada: cierre × (1 − 2 × volatilidad de 20 días), justificado por la volatilidad y solo sube | No hay take profit. La estrategia sale por señal contraria o por stop; un take profit fijo cortaría las ganancias de tendencia, y agregarlo ahora cambiaría la estrategia después de ver el TE |
| Tamaño de posición (Kelly) | No | Tamaño fijo: hasta 100 % del patrimonio de la cartera de cada activo, sin apalancamiento | El protocolo fija la exposición máxima en 100 %. La propia rúbrica pide un mínimo de operaciones antes de usar Kelly, y con 5 operaciones cerradas no hay una estimación confiable del acierto |
| Gestión de riesgo | Parcial | Pérdida diaria máxima de 3 % con bloqueo de compras y rearme manual registrado; botón Detener (kill switch) que bloquea nuevas órdenes; stop móvil; antigüedad máxima del dato; una sola posición por activo; validación de acciones | No hay límite de drawdown total ni de racha de pérdidas. Los límites se fijaron en la configuración antes de la prueba y no se cambian a mitad de ella |

## 3 · Aprendizaje (ML / DL) y predicciones

| Indicador | Estado | Qué tiene el sistema | Por qué no se completa |
|---|---|---|---|
| Problema y objetivo | Cumple | El modelo pronostica el rendimiento del día siguiente, y la regla de trading compra solo si ese pronóstico supera el umbral δ elegido en VA | — |
| Datos y features | Cumple | 20 rezagos del rendimiento diario, calculados solo con datos pasados; escaladores ajustados solo con el entrenamiento; fuente, periodo y partición documentados (`ficha_activo.json`, `particiones.csv`) | — |
| Validación | Parcial | Partición cronológica TR/VA/TE sin mezclar al azar; ventanas expansivas en el capítulo 9 (`ventanas_expansivas_cap9.csv`); el TE se usó una sola vez | No se dejaron días de separación entre entrenamiento y prueba. Hacerlo exige reentrenar y volver a usar el TE, que ya se usó |
| Comparación con línea base | Parcial | Regresión lineal, regresión SGD, media del entrenamiento, pronóstico cero (capítulo 7) y comprar y mantener. El sistema supera a comprar y mantener en 12 de 15 activos en TE y a la regresión lineal en BTC (−3.25 % frente a −27.98 %) | No se comparó contra operar al azar ni contra un cruce de medias. Las referencias son las que define el protocolo |
| Modelos (ML y DL) | Cumple | ML clásico (regresión lineal y SGD) frente a DL (MLP y LSTM), comparados en los capítulos 7 y 8; se eligió el ensamble de 3 LSTM por su desempeño en VA | — |
| Calibración y probabilidad | No | El modelo da un rendimiento esperado, no una probabilidad; el umbral δ para operar se eligió en VA (capítulo 9) | El modelo es de regresión. Convertirlo en un clasificador con probabilidades calibradas exige entrenar otro modelo y usar de nuevo el TE |
| Del modelo al PnL | Parcial | Simulación del TE con comisiones (`simulacion.csv`, `resultados_trading_TE.csv`), comparada con comprar y mantener; seguimiento en vivo de 129 ciclos | No hay una regla de reentrenamiento por deriva. Con 8 a 13 ciclos en vivo por activo no hay suficiente historia para medir deriva |

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
| Tesis de la estrategia | Parcial | Seguir el impulso de corto plazo: compra si el pronóstico supera δ y, en la estrategia D, solo si el cierre está sobre la SMA20. El informe explica que en un mercado bajista la estrategia se queda en efectivo | El régimen en que funciona no se probó por separado; requeriría nuevos análisis sobre el TE |
| Entry | Parcial | Condiciones objetivas y medibles (pronóstico > δ, cierre > SMA20 en D); orden a mercado al cierre diario, que en MEXC es igual a la apertura siguiente | No hay órdenes límite ni expiración, porque se decide una vez al día con la vela cerrada |
| Long | Parcial | Señal, confirmación (SMA20 en la estrategia D) y stop móvil como invalidador | Sin take profit ni tiempo máximo, por la razón explicada en «Stop Loss y Take Profit» |
| Short | Cumple | Solo compras, justificado: cripto spot sin préstamo de activos y un protocolo que permite solo compras o efectivo | — |
| Salidas | Parcial | Salida por señal contraria y por stop móvil, con prioridad definida: el stop se ejecuta aunque la señal o el LLM digan mantener | Sin take profit ni tiempo máximo |
| Ejecución | Parcial | Órdenes simuladas a mercado, redondeadas al paso de cantidad del par, con monto mínimo y validación de saldo | No hay órdenes bracket u OCO porque no hay broker: el protocolo prohíbe órdenes reales y la demo de MEXC sigue en revisión con el profesor |
| Consistencia backtest ↔ paper | Parcial | Las mismas reglas y el mismo modelo en el TE y en vivo; el modelo de BTC da en la Mac las mismas predicciones que en Colab (diferencia máxima 7.2e-10 en 444 pronósticos) | El deslizamiento real no se puede medir, porque no hay ejecución real |

## Lista de verificación de la rúbrica

| Punto | Estado |
|---|---|
| Las claves no aparecen en el repositorio ni en el navegador | Cumple. Las claves están solo en `.env`; en el navegador solo se escribe la clave de acceso a la app, que no se guarda en el código |
| La app rechaza el endpoint real | Cumple. No existe ruta de órdenes reales y el bloqueo está probado |
| Ninguna decisión usa la vela en curso ni datos futuros | Cumple. Solo velas cerradas, con antigüedad máxima de 26 h |
| Toda operación tiene SL, TP y tamaño calculado antes de entrar | Parcial. Stop y tamaño sí; take profit no |
| Las métricas incluyen comisiones y deslizamiento | Parcial. El TE incluye comisiones de 0.10 %; en vivo el costo es de 0 % por protocolo |
| El modelo supera a una línea base fuera de muestra | Cumple. En TE supera a la regresión lineal y a comprar y mantener |
| La IA no puede enviar órdenes ni saltar el riesgo | Cumple |
| Cada decisión se puede reconstruir desde la bitácora | Cumple. Observación, propuesta, motivos y acción final de cada ciclo en SQLite y CSV |

## Entregables de la rúbrica

| Entregable | Dónde está |
|---|---|
| Repositorio Git con README, `.env.example` y CI | [README](README.md) y [`agente/.env.example`](agente/.env.example). Sin CI (ver «Calidad y entrega») |
| Diagrama de arquitectura y del flujo de decisión | Sección «Cómo funciona el agente» del README y sección 2 del [informe](Informe_Proyecto_Final_Agente_IA.md); pestaña Sistema → Cerebro en la interfaz |
| Informe de la estrategia | [Informe del proyecto final](Informe_Proyecto_Final_Agente_IA.md) e [informe de la práctica](Informe/) |
| Notebook o reporte del modelo | [Notebooks de la práctica](notebooks/practica/): validación temporal y líneas base; sin calibración (ver arriba) |
| Demo en vivo en paper con una decisión trazada | Se puede hacer en clase con la interfaz: cada decisión se sigue en las pestañas Señales, Estrategia y Auditoría, desde la vela de MEXC hasta el aviso por correo |
