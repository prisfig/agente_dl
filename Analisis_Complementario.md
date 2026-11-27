# Análisis complementario (v2.3)

Solo lectura de resultados que ya existían: no se reentrenó ni se cambió el modelo, las reglas o la simulación, y la prueba (TE) no se usó para elegir nada. Script: [`analisis/analisis_complementario.py`](analisis/analisis_complementario.py); tablas en [`resultados/analisis_complementario/`](resultados/analisis_complementario/).

Comprobación: la reconstrucción de la estrategia D de BTC en TE da -3.25 % con 0.10 % de comisión (el notebook reportó −3.25 %).

## 1. Métricas completas y líneas base (BTC, TE ago 2025 – nov 2026, comisión 0.10 %)

| Estrategia | Neto | Drawdown | Sharpe | Sortino | Operaciones | Acierto (IC 95 % Wilson) | Expectativa por operación | Profit factor | Exposición |
|---|---|---|---|---|---|---|---|---|---|
| Estrategia D (modelo LSTM + filtro SMA20) | -3.25 % | -25.4 % | 0.02 | 0.02 | 26 | 23 % (11 % – 42 %) | +0.01 % | 1.01 | 43 % |
| Regla técnica: cierre > SMA20 | -3.25 % | -25.4 % | 0.02 | 0.02 | 26 | 23 % (11 % – 42 %) | +0.01 % | 1.01 | 43 % |
| Cruce de medias: SMA20 > SMA50 | -0.98 % | -28.8 % | 0.11 | 0.12 | 6 | 50 % (19 % – 81 %) | +0.48 % | 1.13 | 51 % |
| Comprar y mantener | -34.09 % | -53.0 % | -0.59 | -0.84 | 1 | 0 % (0 % – 79 %) | -34.16 % | 0.00 | 100 % |

Comprar y mantener se mide aquí con la misma convención que las demás (ejecución a la apertura y comisión de entrada), por eso da -34.09 % y no el −31.57 % de cierre a cierre del notebook.

**Hallazgo:** en el TE de BTC la estrategia D coincidió día por día con la regla técnica pura (cierre > SMA20). El pronóstico del ensamble superó su umbral δ en todos los días en que el cierre estaba sobre la SMA20, así que el filtro de tendencia fue el que decidió. El aporte medible del modelo en BTC está en el pronóstico (RMSE menor que la regresión lineal en TE) y no en el filtro; en los otros 14 activos la estrategia de cada uno se eligió en validación y no se comparó así. Se reporta tal cual: no se cambia nada después de ver el TE.


**Operar al azar con la misma exposición** (10,000 permutaciones de la posición diaria de la estrategia D, semilla 2024): mediana -32.72 %, percentiles 5–95 de -54.06 % a -1.22 %. La estrategia D (-3.25 %) queda por encima del 94.0 % de esas carteras al azar (p = 0.060).

## 2. Sensibilidad a costos y deslizamiento (estrategia D, BTC TE)

| Comisión | Deslizamiento | Estrategia D | Comprar y mantener |
|---|---|---|---|
| 0.00 % | 0.00 % | +1.91 % | -34.03 % |
| 0.00 % | 0.05 % | -0.70 % | -34.06 % |
| 0.05 % | 0.00 % | -0.70 % | -34.06 % |
| 0.05 % | 0.05 % | -3.25 % | -34.09 % |
| 0.10 % | 0.00 % | -3.25 % | -34.09 % |
| 0.10 % | 0.05 % | -5.74 % | -34.12 % |
| 0.20 % | 0.00 % | -8.16 % | -34.16 % |
| 0.20 % | 0.05 % | -10.53 % | -34.19 % |
| 0.30 % | 0.00 % | -12.83 % | -34.22 % |
| 0.30 % | 0.05 % | -15.07 % | -34.26 % |

**Costo de equilibrio:** con un costo total por operación menor a 0.036 % la estrategia D termina positiva en el TE.

## 3. Resultado por régimen de mercado (BTC TE; régimen según el cierre previo frente a su SMA50)

| Régimen | Días | Estrategia D (bruto) | Comprar y mantener (bruto) | Exposición de D |
|---|---|---|---|---|
| alcista | 198 | +3.91 % | +4.73 % | 75 % |
| bajista | 246 | -1.93 % | -37.00 % | 17 % |

## 4. Deriva en vivo y regla de reentrenamiento

Error del pronóstico en los ciclos en vivo (rendimiento del día siguiente) frente al RMSE del TE de cada activo.

| Activo | Ciclos evaluados | RMSE en vivo | RMSE en TE | Razón | Acierto direccional en vivo | Estado |
|---|---|---|---|---|---|---|
| ADAUSDT | 7 | 0.0270 | 0.0394 | 0.69 | 71 % | no |
| BCHUSDT | 7 | 0.0294 | 0.0403 | 0.73 | 57 % | no |
| BNBUSDT | 7 | 0.0284 | 0.0267 | 1.06 | 57 % | no |
| BTCUSDT | 12 | 0.0210 | 0.0223 | 0.94 | 58 % | no |
| DOGEUSDT | 7 | 0.0289 | 0.0375 | 0.77 | 71 % | no |
| DOTUSDT | 7 | 0.0319 | 0.0423 | 0.75 | 57 % | no |
| ETHUSDT | 9 | 0.0322 | 0.0322 | 1.00 | 33 % | a vigilar |
| FILUSDT | 7 | 0.0376 | 0.0468 | 0.80 | 43 % | a vigilar |
| LTCUSDT | 7 | 0.0293 | 0.0321 | 0.91 | 43 % | a vigilar |
| MXUSDT | 7 | 0.0040 | 0.0167 | 0.24 | 29 % | a vigilar |
| NEARUSDT | 7 | 0.0503 | 0.0549 | 0.92 | 57 % | no |
| SOLUSDT | 9 | 0.0283 | 0.0322 | 0.88 | 56 % | no |
| TRXUSDT | 7 | 0.0138 | 0.0137 | 1.00 | 43 % | a vigilar |
| XRPUSDT | 7 | 0.0235 | 0.0341 | 0.69 | 57 % | no |
| ZECUSDT | 7 | 0.0765 | 0.0722 | 1.06 | 71 % | no |

**Regla de reentrenamiento** (fijada el 27 nov, antes de ver más ciclos): se revisa cada 20 ciclos en vivo por activo. Si el RMSE en vivo supera 1.5 veces el RMSE del TE, o el acierto direccional queda debajo de 45 %, el modelo de ese activo se marca para reentrenar con una nueva partición cronológica (TR/VA/TE nuevos) y un TE que no se haya visto. Con 7 a 12 ciclos evaluados por activo la muestra todavía es corta: esta tabla es el primer punto del monitoreo, no una conclusión.
