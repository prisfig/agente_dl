# Registro de versiones del agente

Cada modificación al programa sube la versión (1.1, 1.2, …). El número está en `config/agente.json` (`"version"`),
aparece en la barra superior de la interfaz y se guarda en cada ciclo (campo `version` de la observación) y en el evento de arranque.

## v2.1 — 26 de noviembre de 2026 (noche)

**Pestaña «PnL simulado».** La entrega pide presentar operaciones y PnL, y la v2.0 había quitado todos los saldos de la
interfaz porque el sistema no compra. Para cumplir las dos cosas, la antigua pestaña **Operaciones** vuelve como **PnL simulado**,
segunda pestaña después de Señales, y deja claro que no es una cuenta:

- Encabezado «EVALUACIÓN DE LA SEÑAL · NO SON COMPRAS REALES» y chip «No es una cuenta · nadie compró nada · órdenes reales bloqueadas».
- Aviso al inicio: son las cifras de la simulación interna (bloque 16 del protocolo) con capital virtual de 50,000 USDT por
  activo y precios reales de MEXC; no son saldos ni operaciones ejecutadas.
- Abre en la cartera **Sin LLM** (la estrategia que dispara los avisos); Con LLM y Comprar y mantener quedan como referencias.
- Sin cambios en el backend, el modelo, el riesgo ni los avisos: la pestaña usa `GET /api/operaciones`, que nunca se quitó.
  Solo cambian la interfaz (`App.tsx`, `pestanas/Operaciones.tsx`) y el número de versión (configuración, demos y su prueba).

## v2.0 — 26 de noviembre de 2026

**Laboratorio de señales con avisos por correo.** Por indicación del profesor, el sistema deja de presentarse como un agente
con saldos: en realidad no compra nada, así que la interfaz ya no muestra saldos ni carteras. Ahora es un laboratorio que
analiza los 15 pares cada día y **avisa por correo** cuando el modelo da señal de compra (o de venta) en algún activo, para
que el usuario decida si compra a mano en MEXC.

- **Disparador:** la estrategia del modelo de cada activo (la cartera *sin LLM*), después del motor de riesgo. Si compra, llega un
  aviso de compra con el cierre, el pronóstico frente a δ y el stop móvil sugerido; si vende (por señal del modelo o por stop),
  llega un aviso de venta con el motivo. El LLM no dispara avisos (en vivo no aportó valor; ver informe).
- **Canal principal: correo** (`backend/app/notificaciones.py`, `NotificadorCorreo`), por SMTP con TLS a Gmail (`smtp.gmail.com:465`)
  y una contraseña de aplicación. Solo se permiten servidores SMTP conocidos (Gmail y Office 365). Asunto:
  «Laboratorio DL · señal de COMPRA en LTCUSDT (vela 2026-11-25)». Usuario, contraseña de aplicación y destino van solo en `.env`
  (`CORREO_USUARIO`, `CORREO_CONTRASENA_APP`, `CORREO_DESTINO`); nunca en el repositorio, la interfaz ni la bitácora (las
  direcciones se muestran enmascaradas y la contraseña se borra de cualquier respuesta guardada).
- **WhatsApp como alternativa (deshabilitada):** primero se intentó WhatsApp. CallMeBot tenía el cupo lleno y la WhatsApp Cloud API
  de Meta necesita una plantilla aprobada (hasta 24 h) para escribir fuera de la ventana de 24 h, así que se cambió a correo. El
  código de WhatsApp (proveedores `meta` y `callmebot`, con envío como texto si la plantilla aún no está aprobada) se conserva y se
  activa con `notificaciones.whatsapp.habilitado` si el correo está deshabilitado.
- **Sin duplicados:** cada aviso queda en la nueva tabla `notificaciones` de la base del activo, con (modo, vela, tipo) único. Un
  reinicio o un ciclo repetido no manda dos veces el mismo aviso. El replay nunca avisa.
- **Un fallo del aviso no cambia nada del ciclo:** hasta dos intentos con espera creciente (una contraseña o un destinatario
  rechazados no se reintentan); si fallan, se registra el evento `notificacion_fallo`, el aviso queda como *fallido* y el agente
  sigue corriendo con las mismas decisiones.
- **API:** `GET /api/senales` (señal del modelo de cada activo en su último ciclo, señal activa con precio de entrada y stop, y aviso
  de esa vela; sin saldos), `GET /api/notificaciones` (historial de avisos) y `POST /api/notificaciones/prueba` (aviso de prueba).
  Sección `notificaciones` en `config/agente.json`; las configuraciones de demostración no la tienen (avisos deshabilitados).
- **Interfaz:** nueva pestaña **Señales** (la primera): señales de compra y venta del día, señales activas, estado de los avisos,
  botón de aviso de prueba, tabla por activo e historial de avisos. Se quitaron los saldos de la barra superior, las columnas de
  saldo de la tabla de activos, las tarjetas de carteras del Resumen, la curva de patrimonio y la fila de patrimonio final de
  Estrategia, y la pestaña Operaciones deja de mostrarse. La barra dice «LABORATORIO» y «sin órdenes · avisos por correo».
- **Lo que no cambia:** modelos, estrategia, motor de riesgo, LLM y ciclo diario. La simulación Paper sigue por dentro, solo como
  evaluación de la señal (bloque 16 del protocolo: comparación sin LLM, con LLM y comprar y mantener); sus métricas siguen en
  `agente/registros/` y en el informe. Las órdenes reales siguen bloqueadas.
- 119 pruebas automatizadas (22 nuevas en `tests/test_notificaciones.py`: correo, WhatsApp de Meta y CallMeBot, sin red real).

## v1.9 — 20 de noviembre de 2026

Botón **«Rearmar todos los bloqueados»** y regla de operación para el control de pérdida diaria.

- Contexto: en el ciclo de la vela del 20 nov (caída general de 4 % a 15 %) el límite de pérdida diaria de 3 % se activó en
  13 de los 15 activos en la cartera con LLM y en 2 en la cartera sin LLM. Sin rearme, esas carteras no podrían volver a comprar
  en lo que resta del periodo.
- **Regla de operación, fijada el 20 nov antes de ver ciclos posteriores:** después de cada ciclo diario, el usuario rearma
  todos los activos que hayan quedado bloqueados, sin excepciones. Así el bloqueo impide las compras del ciclo en que ocurre
  la caída de 3 % o más. El rearme sigue siendo una acción humana y queda registrada.
- `POST /api/riesgo/rearmar_todos` (`rearmar_bloqueados` en `backend/app/operaciones.py`): hace lo mismo que el botón
  individual en cada activo bloqueado (quita el bloqueo de sus carteras) y registra en la base de cada uno el evento de
  control con `origen: rearmar_todos` y las carteras que estaban bloqueadas. Los activos sin bloqueo no se tocan.
- El botón aparece en Resumen (junto a «Rearmar control de pérdida») y en el panel de Riesgo de Operaciones, que además lista
  los activos bloqueados en cualquier cartera (`riesgo.bloqueados_todas_carteras` en `/api/operaciones`).
- El motor de riesgo, la estrategia y los modelos no cambian.
- 97 pruebas automatizadas (1 nueva).

## v1.8 — 20 de noviembre de 2026

Pestaña **Operaciones** rediseñada para que se vea qué posiciones están abiertas, cuándo y a qué precio compró el agente y
cuál es el saldo total. Solo cambia cómo se presentan los registros: la estrategia, los modelos, el motor de riesgo, el
simulador y las bases de datos de los activos no cambian.

- Suma los 15 activos de la cartera elegida (Sin LLM · estrategia, Con LLM · agente, Comprar y mantener). El selector muestra
  el saldo total y el rendimiento de las tres carteras.
- Modo de trading: Paper, precios reales de MEXC y órdenes simuladas con saldo ficticio; las órdenes reales siguen bloqueadas
  (la API de MEXC no tiene cuenta de prueba y el protocolo pide simulador propio).
- Rendimiento: saldo total (capital inicial 15 × 50,000 USDT), PnL neto, efectivo, invertido, PnL realizado y no realizado,
  drawdown máximo, operaciones cerradas, acierto, profit factor y comisiones.
- Riesgo con barras: peor pérdida del día frente al límite de 3 %, exposición frente a 100 %, activos con compras bloqueadas,
  agentes en pausa y posiciones a menos de 2 % del stop móvil.
- Posiciones abiertas: activo, lado (LONG), fecha y precio de compra, cantidad, invertido, último cierre, precio actual de
  MEXC, stop móvil y distancia, PnL al cierre y a precio actual, días abierta y señal del modelo.
- Historial de operaciones cerradas: compra y venta (fecha y precio), días, motivo de salida (señal del modelo, el LLM
  propuso VENDER, stop móvil o liquidación manual) y PnL.
- Saldo por activo y tarjeta con las reglas de entrada, salida, tamaño, horario y límite diario de la cartera.
- Debajo se conservan las decisiones por ciclo y las órdenes Paper del activo seleccionado.
- Backend: `GET /api/operaciones?modo=vivo&cartera=con_llm` (`backend/app/operaciones.py`) y consulta de solo lectura
  `GET /api/v3/ticker/price` de MEXC (en caché 30 s) para el precio actual, que es solo informativo: el patrimonio oficial
  se sigue valuando al último cierre diario. Si MEXC no responde, la pestaña lo indica y lo demás sigue igual.
- 96 pruebas automatizadas (4 nuevas en `tests/test_operaciones.py`).

## v1.7 — 19 de noviembre de 2026

DOTUSDT reemplaza a GOLD(PAXG)USDT: el agente opera 15 pares.

- **Selección del reemplazo** (`notebooks/DLF_Activos_Extra_Lote3.ipynb`, ejecutado en Colab T4 el 20 nov 03:11 UTC): la misma
  regla del lote 2 con el filtro de tokens respaldados corregido (ahora por patrón: `GOLD`, `PAXG`, `XAUT`, `XAU`, `SILVER`),
  excluyendo los 14 activos del agente y `GOLD(PAXG)USDT`; se toma el primero que cumple. Se revisaron 37 candidatos con el
  volumen de 24 h de ese momento; `GOLD(XAUT)USDT` quedó descartado como respaldado por oro y el elegido fue **DOTUSDT**
  (rango 37). El orden de los primeros 36 coincide con el del lote 2 salvo pequeñas variaciones de volumen.
  Lista y motivos en `activos_extra_lote3/resultados/seleccion_activos.json` y `seleccion_activos_candidatos.csv`.
- DOTUSDT: TR/VA/TE propios 70/15/15 (TE hasta el 19 nov, 339 objetivos), LSTM de 40 neuronas elegida con VA y repetida con
  3 semillas, estrategia C, δ = 0.2394 %, `decimales_precio` 4 (cotiza ~0.71 USDT).
- Verificación: `python agente/verificar_activos_extra.py activos_extra_lote3`
  (reporte en `evidencia/verificacion_activos_extra_lote3_local.json`).
- 92 pruebas automatizadas (las de modelos reales incluyen DOT).

## v1.6 — 19 de noviembre de 2026

Diez activos más: el agente opera 14 pares (BTC, ETH, SOL, XRP, BNB, ADA, LTC, TRX, DOGE, MX, FIL, BCH, ZEC y NEAR).

- **Selección por regla fijada antes de entrenar** (`notebooks/DLF_Activos_Extra_Lote2.ipynb`, sección 0.4, ejecutado en Colab T4
  el 20 nov 02:00 UTC): de los 1,310 pares spot USDT habilitados en MEXC, ordenados por volumen de 24 h, los primeros que no
  estuvieran ya en el agente, no fueran stablecoins, tokens respaldados por oro u otros activos, apalancados ni envueltos, y
  tuvieran al menos 1,560 días de velas diarias. Se revisaron 32 candidatos; lista, motivos y fecha en
  `activos_extra_lote2/resultados/seleccion_activos.json` y `seleccion_activos_candidatos.csv`.
- **GOLD(PAXG)USDT excluido.** La regla excluía los tokens respaldados por oro, pero el filtro buscaba la base `PAXG` y MEXC la
  nombra `GOLD(PAXG)`, así que se eligió por error. Se excluyó al aplicar la regla tal como estaba escrita, **antes de ver
  cualquiera de sus resultados**, y no se sustituyó (eso habría requerido otra selección con un volumen de 24 h distinto).
  Su modelo se entrenó y verificó, pero no se usa. Detalle en `activos_extra_lote2/resultados/correccion_seleccion.md`.
- Cada activo nuevo tiene su propio TR/VA/TE 70/15/15, LSTM elegida con VA (10, 20 o 40 neuronas) y repetida con 3 semillas,
  δ y estrategia (C o D) elegidos con VA y TE evaluado una sola vez; TE termina el 19 nov, así que los ciclos en vivo empiezan
  después. Ninguno quedó excluido por la auditoría ni por el entrenamiento.
- Verificación en esta computadora: `python agente/verificar_activos_extra.py activos_extra_lote2` (el script ahora acepta la
  carpeta; sin argumento revisa el lote 1). Reporte en `evidencia/verificacion_activos_extra_lote2_local.json`.
- **Nuevo `decimales_precio` por activo** para los precios del texto del LLM y los motivos del stop (DOGE 0.05819 se mostraba
  como 0.06). Por defecto 2: BTC, ETH, SOL y XRP no cambian (XRP sigue con 2 aunque cotiza bajo 1 USDT, para no cambiar su
  entrada a mitad de la serie). Nuevos: ADA, TRX y FIL 4; DOGE 5; MX y NEAR 3; el resto 2.
- Interfaz: precios menores a 0.1 con 5 decimales. El Escáner muestra los 14 pares.
- Los activos nuevos arrancan *detenidos*; se inician uno por uno desde la interfaz.
- Arranque con los 14 modelos: ~5 s y ~740 MB de memoria máxima (medido en Linux). 90 pruebas automatizadas.

## v1.5 — 19 de noviembre de 2026

Límite de tokens en las respuestas del LLM y regreso de XRPUSDT. El agente opera BTCUSDT, ETHUSDT, SOLUSDT y XRPUSDT.

- **Causa confirmada del fallo de XRP (17 nov)** en la bitácora de Ollama (`~/.ollama/logs/server-2.log`): la respuesta final
  con formato JSON empezó a las 20:22:24 y a las 20:24:24 llevaba 2,328 tokens sin cerrar el JSON, a velocidad normal
  (20–25 tokens/s); el gateway la cortó a los 2 min y los reintentos repitieron lo mismo (temperatura 0 y semilla fija).
  No fue falta de memoria: Ollama respondió todo el tiempo y la velocidad no cayó. Las respuestas normales miden 37–168 tokens.
- **Nuevo `llm.max_tokens_respuesta` = 400** (opción `num_predict` de Ollama), en las dos fases de la consulta. Con temperatura 0
  la decodificación es voraz: una respuesta que termina antes del límite sale idéntica con o sin él, así que las decisiones
  de las carteras con LLM no cambian; solo se cortan las respuestas desbocadas (en ~20 s en vez de 6 min).
- Una respuesta cortada queda como aviso `respuesta_cortada_por_limite_de_tokens`; el reintento le dice al modelo que
  llegó al límite sin cerrar el JSON. Si se repite en los tres intentos, el error es `json_invalido` y el activo se pausa.
- **XRPUSDT regresa** con su misma base (`datos/agente_XRPUSDT.sqlite3`), que conserva el error del 17 nov. Arranca
  *pausado* por ese error: se reanuda con Iniciar.
- La instancia de demostración de JSON inválido conserva su propio límite de 6 tokens en la respuesta final.
- 68 pruebas automatizadas (6 nuevas para el límite de tokens).

## v1.4 — 17 de noviembre de 2026

Se retira XRPUSDT. El agente opera BTCUSDT, ETHUSDT y SOLUSDT.

- Motivo: el primer ciclo en vivo de XRP (vela 2026-11-17) falló. Ollama respondió a la primera fase (consulta de herramienta,
  3.95 s), pero no a la respuesta final con formato JSON: tres intentos terminaron en `ReadTimeout` (90 s cada uno). El agente
  se pausó solo, no envió órdenes y no marcó la vela como procesada (manejo previsto del error "Ollama no responde").
  ETH y SOL completaron su ciclo de la misma vela en 20 s y 13 s.
- La decisión no se basa en resultados: XRP no llegó a tener ningún ciclo en vivo. Su entrenamiento, evaluación en TE y
  verificación en la Mac siguen reportados (`notebooks/`, `activos_extra/`, `evidencia/verificacion_activos_extra_local.json`).
- `datos/agente_XRPUSDT.sqlite3` se conserva como evidencia del error (eventos de arranque, inicio y `llm_no_disponible`);
  el backend ya no la carga. XRPUSDT pasa a "solo contexto" en el Escáner.
- Hipótesis no comprobada sobre la causa: con salida JSON forzada y sin límite de tokens, el modelo de 3B puede quedarse
  generando sin terminar; con temperatura 0 y semilla fija, los mismos datos repetirían el bloqueo. Nada en la v1.4 cambia
  ese comportamiento para los activos que siguen; si llegara a ocurrir, el agente se pausa igual que con XRP.
- Sin cambios en la lógica del agente. 60 pruebas automatizadas (las de XRP se quitaron de las pruebas parametrizadas).
- Interfaz: si el activo que el navegador tenía elegido ya no está configurado (XRP), vuelve sola a BTCUSDT en vez de
  mostrar "Activo no configurado". Corregido antes del primer ciclo de la v1.4.

## v1.3 — 17 de noviembre de 2026

Backend multi-activo: además de BTCUSDT, el agente opera ETHUSDT, SOLUSDT y XRPUSDT, cada uno con su propio modelo
entrenado y evaluado en `notebooks/DLF_Activos_Extra_ETH_SOL_XRP.ipynb`.

- **Un agente independiente por activo**: modelo congelado propio (neuronas, δ y estrategia elegidos con su VA), base SQLite propia
  (`datos/agente_ETHUSDT.sqlite3`, etc.), tres carteras de 50,000 USDT y control humano propio (iniciar, pausar, detener, liquidar, rearmar).
  Riesgo, Paper, LLM y horario son comunes. La base de BTC es la misma (`datos/agente.sqlite3`): sus ciclos en vivo continúan sin cambios.
- **Estrategia por activo**: C (pronóstico > δ, sin filtro) o D (pronóstico > δ y cierre > SMA20), leída de la configuración congelada.
  BTC sigue con D; ETH, SOL y XRP usan C (la que eligió VA). Neuronas: BTC 20, ETH 10, SOL 20, XRP 10.
- **Huellas SHA-256**: al arrancar, los checkpoints y escaladores de ETH, SOL y XRP se comparan con su configuración congelada;
  si alguno no coincide, el backend no lo carga.
- **Ciclos uno tras otro** (BTC, ETH, SOL, XRP) con un candado compartido, para que Ollama nunca reciba dos solicitudes a la vez.
  Un error en un activo pausa solo ese activo.
- **LLM**: para BTC recibe exactamente los mismos datos, claves y descripciones de herramientas que en la v1.2 (comprobado con una prueba).
  Para los demás activos, los textos usan su símbolo y su estrategia (p. ej., `senal_estrategia_C`, "efectivo, ETH").
- **Replay**: se rechaza si empieza dentro del conjunto de prueba (TE) del activo, para no repetir un periodo ya evaluado.
  Para ETH, SOL y XRP el TE llega hasta el 17 nov, así que su replay solo será posible con velas posteriores.
- **API**: todas las rutas aceptan `?simbolo=ETHUSDT` (sin él se usa BTCUSDT, como antes). Nueva ruta `GET /api/activos`.
- **Interfaz**: selector de activo en la barra superior (con el estado de cada uno), tabla de activos en Resumen y textos
  sin "BTC" fijo (estrategia, unidades, red neuronal con el tamaño real de cada modelo, precios con decimales según el activo).
- La observación guardada en cada ciclo incluye `estrategia` y `senal`; en BTC se conserva también `senal_d`, el nombre anterior.
- `config/agente.json`: nueva lista `activos`. Las configuraciones de demostración siguen siendo de un solo activo (BTC).
- Nuevo `verificar_activos_extra.py`: comprueba en esta computadora que los modelos de ETH, SOL y XRP repiten las predicciones
  de TE y el pronóstico futuro de Colab (reporte en `evidencia/verificacion_activos_extra_local.json`).
- 62 pruebas automatizadas (18 nuevas). Entre ellas: los modelos reales de ETH, SOL y XRP repiten TE, y el camino de un ciclo
  en vivo (velas → variables → ensamble → señal) reproduce el pronóstico del 18 nov del notebook en los tres.

## v1.2 — 16 de noviembre de 2026

- `config/demo/demo_json_invalido.json` usa su propia base (`demo_json.sqlite3`): en la base general de demostración la vela
  del día ya estaba procesada y el escenario se detenía antes de llegar al LLM (evento duplicado).
- Sin cambios en la lógica del agente. Los ciclos en vivo desde esta versión se registran como 1.2.

## v1.1 — 16 de noviembre de 2026

Instancia de demostración separada para probar los nueve escenarios de error sin tocar los ciclos en vivo.

- Nueva variable de entorno `AGENTE_CONFIG`: permite arrancar el backend con otra configuración
  (por defecto sigue usando `config/agente.json`).
- Configuraciones de demostración en `config/demo/` con base de datos propia y sin ciclos automáticos:
  `demo.json` (general), `demo_dato_atrasado.json` (antigüedad máxima 3 min), `demo_json_invalido.json`
  (Ollama limitado a 6 tokens en la respuesta final, lo que produce un JSON cortado real) y `demo_saldo.json`
  (capital de 0.50 USDT, menor al monto mínimo del par).
- La interfaz muestra un aviso rojo cuando el backend corre una configuración de demostración.
- La lógica de decisión, riesgo y Paper no cambió respecto de la v1.0.
- 44 pruebas automatizadas.

## v1.0 — 15 de noviembre de 2026 (versión base)

Primera versión completa, con la que inician los ciclos en vivo (primer ciclo en vivo: vela 2026-11-14).

- Backend FastAPI con API privada (`X-API-Key`), ciclo programado diario y control humano (iniciar, pausar, detener, liquidar, rearmar).
- Ensamble LSTM congelado de la práctica (semillas 42, 123, 2024), verificado en la Mac contra Colab (444 pronósticos de TE, diferencia máxima 7.2e-10).
- LLM local `llama3.2:3b` en Ollama, detrás de un gateway con API key; herramientas de solo lectura; respuesta JSON validada por esquema.
- Motor de riesgo determinista: exposición máxima 100 %, pérdida diaria máxima 3 %, stop móvil 2 × vol20, antigüedad máxima del dato 26 h.
- Simulador Paper (50,000 USDT, costo 0 %) con paso de cantidad y monto mínimo leídos de MEXC; rutas de órdenes reales bloqueadas.
- SQLite con ciclos, decisiones, órdenes, patrimonio y bitácora; sin duplicados al reiniciar.
- Tres carteras con el mismo periodo y costos: sin LLM (estrategia D), con LLM y comprar y mantener. Modo replay separado del vivo.
- Interfaz React + TypeScript: Resumen, Mercado, Escáner, Operaciones, Estrategia, Auditoría y Sistema (Salud, Cerebro, Red neuronal, Ajustes).
- 43 pruebas automatizadas, incluidos los nueve escenarios de error del protocolo.

Ajustes hechos durante el desarrollo de la v1.0 (antes del primer ciclo en vivo):
- Replay v1 → v2: los datos para el LLM pasaron a llevar la unidad ("+0.1783 %") y comparaciones ya resueltas, porque el modelo leía
  0.1783 como 17.83 %. Se agregó un aviso cuando la justificación cita números que no están en los datos. Las acciones propuestas fueron
  idénticas en ambas corridas. Evidencia: `evidencia/replay_v1_2026-11-05_a_14.csv` y `evidencia/replay_v2_2026-11-05_a_14.csv`.
- Vista "Red neuronal": se omite la capa de entrada del modelo guardado al calcular activaciones.
