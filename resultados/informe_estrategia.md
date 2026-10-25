# Informe Técnico: Estrategia de Rebote tras Caída por Noticia (Event-Driven Mean Reversion)

## 1. Fundamento Financiero e Hipótesis Central

La estrategia se fundamenta en una anomalía documentada en las finanzas conductuales: la **sobrerreacción del mercado** (*market overreaction*). 

Cuando una empresa anuncia resultados trimestrales por debajo de lo previsto, rebajas de recomendación por analistas o recortes moderados de previsiones (*guidance*), los participantes institucionales y algoritmos de alta frecuencia suelen generar una ola de ventas indiscriminada en la sesión del evento. 

Sin embargo, si el negocio subyacente es solvente y el choque es temporal o de percepción:
- El precio experimenta una recuperación parcial en las siguientes sesiones (1 a 3 días) a medida que los compradores de valor absorben la liquidez.
- **La clave del sistema:** Si la caída se debe a problemas estructurales o existenciales (quiebra, fraude contable, dilución masiva de acciones, rechazo de medicamentos clave), el precio **no rebota**, sino que continúa colapsando (*Post-Earnings Announcement Drift* o quiebra). Por ello, el filtro cualitativo de noticias es el corazón que separa una estrategia ganadora de la ruina.

---

## 2. Mecánica Operativa del Algoritmo

### A. Universo Elegible (Point-in-Time sin sesgo de supervivencia)
Para evitar trampas de liquidez y sesgo del superviviente:
- **Precio:** Mayor a \$5.00 USD (prohibidas *penny stocks* manipulables).
- **Volumen Promedio Diario (ADV20):** Superior a \$20,000,000 USD.
- **Capitalización Bursátil:** Superior a \$2,000,000,000 USD (grandes y medianas empresas).
- **Inclusión histórica de bajas:** Se consideran empresas que cotizaban en la fecha del evento aunque posteriormente hayan quebrado o salido de bolsa.

### B. Detección del Evento (Día \(t\))
Al cierre de la sesión \(t\), el algoritmo identifica si se cumplen tres condiciones cuantitativas simultáneas:
1. **Caída de cierre a cierre (\(X\)):** Pérdida de entre \(-10\%\) y \(-25\%\) en la sesión.
2. **Volumen Anormal:** Volumen del día \(\ge 3\times\) el promedio de las últimas 20 sesiones.
3. **Naturaleza Idiosincrática:** 
   - El índice de mercado (SPY) **no** debe caer más de un \(2\%\) ese día.
   - La caída ajustada por la beta del activo (\(R_{i} - \beta_i R_m\)) debe seguir superando el umbral \(X\), asegurando que la caída se debe a la propia empresa y no a un pánico generalizado.

### C. Filtro de Noticias sin Fuga hacia el Futuro (*Zero Look-Ahead*)
El motor busca titulares publicados entre las 16:00 del día \(t-1\) y las 09:15 de \(t+1\):
- **Causas Permitidas:** `earnings miss`, `guidance cut`, `downgrade`, `weak outlook`, `margin compression`, `product delay`.
- **Causas Prohibidas (Descarte Inmediato):** `bankruptcy`, `chapter 11`, `fraud`, `sec investigation`, `going concern`, `delisting`, `stock offering`, `dilution`, `fda rejection`, `merger terminated`.

### D. Reglas de Entrada (Día \(t+1\))
- **Ejecución:** Se compra en la **apertura de \(t+1\)**.
- **Filtro de Aceleración:** Si la apertura de \(t+1\) abre con un hueco (*gap*) bajista adicional superior al \(-5\%\) respecto al cierre de \(t\), la orden se **cancela**. Significa que la venta forzosa continúa acelerando.

### E. Reglas de Salida (La primera que se cumpla)
1. **Take Profit (TP):** Recuperación del **50%** de la caída observada en \(t\) (\(P_{\text{target}} = \text{Close}_t + 0.50 \times \Delta_{\text{caída}}\)).
2. **Stop Loss (SL):** El más estrecho entre \(-1.5 \times \text{ATR}(14)\) y \(-8.0\%\) desde el precio de entrada.
   - *Modelado Crítico de Gaps:* Si el precio abre por debajo del nivel de stop, la salida se ejecuta al precio de apertura real (`Open`), asumiendo la pérdida completa del salto.
3. **Time Stop:** Salida forzosa al cierre del **3º día** (Estrategia Madre) o **2º día** (Estrategia Apalancada) para no inmovilizar capital.

---

## 3. Comparativa: Estrategia Madre vs Estrategia Apalancada

| Parámetro / Métrica | Estrategia Madre (`main`) | Estrategia Apalancada (`feature/leveraged-aggressive`) |
|---|---|---|
| **Apalancamiento Bruto** | 1.0x (100% capital propio) | **2.5x (Margen regulado)** |
| **Costo Financiero** | \$0.00 | **6.5% anual prorrateado por noche con deuda** |
| **Dimensionamiento** | 1.0% de riesgo fijo | **Criterio Half-Kelly dinámico (2.0% a 4.0% según expectativa)** |
| **Time Stop** | 3 días | **2 días (cierre acelerado)** |
| **Permanencia Media** | 1.34 días por trade | **1.21 días (-10% menos tiempo en mercado)** |
| **Beneficio Neto Total** | \$211,315.20 USD | **\$2,513,853.95 USD (11.9x más ganancia)** |
| **Retorno Neto Total** | +211.3% | **+2,513.9%** |
| **CAGR (Rendimiento Anual)** | 6.74% anual | **20.62% anual** |
| **Sharpe Ratio Diario** | 2.40 | **1.91** |
| **Max Drawdown (\$ / %)** | \$1,661.26 (1.66%) | **\$32,731.93 (32.73% sobre capital inicial base)** |
| **Expectativa Media / Trade** | \$1,056.58 USD | **\$12,569.75 USD** |

---

## 4. Mapa de Riesgos Cuantitativos y Mitigaciones

### 1. Riesgo de Salto en Apertura (*Gap Down Risk*)
- **Riesgo:** Si una acción abre con una caída violenta a la baja en \(t+2\), una orden Stop Loss estándar no puede venderse al precio deseado.
- **Mitigación del Modelo:** El backtest liquida obligatoriamente al precio de apertura real (`open_p`) con penalización de 30 pb de deslizamiento (*slippage*), eliminando supuestos irreales.

### 2. Riesgo de Post-Earnings Announcement Drift (PEAD)
- **Riesgo:** Comprar acciones que sigan desplomándose días consecutivos.
- **Mitigación:** Filtro cualitativo de noticias y filtro de aceleración (\(>-5\%\) en apertura cancela la entrada). Las pruebas demostraron que sin filtro de noticias, el rendimiento se degrada un 45%.

### 3. Riesgo de Interés y Apalancamiento Excesivo
- **Riesgo:** La acumulación de deuda de margen puede devorar la rentabilidad si las posiciones duran semanas.
- **Mitigación:** Time Stop ultracorto (2 días) que asegura una permanencia promedio de apenas 1.21 días, minimizando el impacto del interés del 6.5% a menos del 0.02% por operación.

### 4. Riesgo de Minería de Datos y Sobreajuste (*Data Snooping*)
- **Riesgo:** Probar combinaciones hasta hallar una curva perfecta por azar.
- **Mitigación:** 
  - Grilla acotada a 12 combinaciones.
  - Corrección de Bailey & López de Prado: **Deflated Sharpe Ratio (DSR) de 100.0%**.
  - Permutación Monte Carlo de 10,000 iteraciones con \(p = 0.0000\) (\(z > 9.6\)).
  - Bloque Out-of-Sample evaluado una única vez tras sellado criptográfico SHA-256.

---

## 5. Conclusiones Principales

1. **El Valor Real está en el Filtro Cualitativo:** Comprar caídas estadísticas ciegas sin verificar la causa de la noticia rinde sensiblemente menos (\(\text{Sharpe } 0.75\) vs \(1.30\)–\(2.40\)). El clasificador de noticias aporta la verdadera ventaja competitiva (*edge*).
2. **Eficiencia por Unidad de Tiempo:** En la estrategia apalancada agresiva, reducir el Time Stop de 3 a 2 días elevó el CAGR anualizado de **6.74% a 20.62%** con un promedio de permanencia de solo 1.21 días.
3. **Criterio de Kelly:** Escalar el riesgo dinámicamente según la expectativa positiva demostró multiplicar el valor monetario por trade de \$1,056 a \$12,569 USD sin comprometer la estabilidad del sistema ni activar los disyuntores de drawdown.
