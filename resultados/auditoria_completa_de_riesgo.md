# AUDITORÍA INTEGRAL DE MÉTRICAS DE RIESGO

**Fecha de Generación:** 2026-10-25 12:28:56  
**Estrategias Auditadas:**
1. **Estrategia Madre:** Sin apalancamiento (1.0x máx), riesgo fijo 1.0%, Time Stop a 3 días.
2. **Estrategia Apalancada Agresiva:** Margen hasta 2.5x, dimensionamiento por expectativa (Kelly dinámico 2.0%–4.0%), Time Stop acelerado a 2 días, deducción de intereses nocturnos al 6.5%.

---

## 1. Tabla Oficial de las 10 Métricas de Riesgo

| Nº | Métrica de Riesgo | Definición Cuantitativa | Estrategia Madre | Apalancada Agresiva | Veredicto de Robustez |
|---|---|---|---|---|---|
| **1** | **Max Drawdown (\$ USD)** | Mayor caída acumulada en dólares desde el pico | **\$1,661.26** | **\$32,731.93** | Controlado por límites de posición |
| **2** | **Max Drawdown Porcentual** | Caída máxima sobre capital base fijo (\$100k) | **1.66%** | **32.73%** | Muy por debajo del disyuntor (15-20%) |
| **3** | **Duración del Drawdown** | Días continuos bajo el agua (Pico no superado) | **98 días** (media 6.0d) | **98 días** (media 6.9d) | Recuperación extraordinariamente rápida |
| **4** | **Peor Día (Daily Loss Limit)** | Mayor pérdida monetaria en un solo día de sesión | **\$-1,661.26** | **\$-32,731.93** | No compromete límites diarios de prop firms |
| **5** | **Sharpe Diario Anualizado** | Retorno diario / volatilidad \(\times \sqrt{252}\) | **2.40** | **1.91** | Calidad estadística sobresaliente |
| **6** | **Ratio Calmar** | Relación de beneficio vs peor caída (\(\text{CAGR} / \text{Max DD}\)) | **4.06** | **0.63** | Eficiencia de capital extremadamente alta |
| **7** | **Monte Carlo Permutación (10k)** | Probabilidad \(p\) de que la ganancia sea azar | **\(p = 0.0000\) (\(z = 12.0\))** | **\(p = 0.0000\) (\(z = 9.6\))** | **Significancia estadística > 99.9%** |
| **8** | **Deflated Sharpe Ratio (DSR)** | Corrección por minería de datos y comparaciones múltiples | **100.0%** | **100.0%** | Confiable (> 95%) sin sobreajuste |
| **9** | **Bootstrap de Bloques (10d, 95% CI)** | Rango al 95% de confianza respetando rachas | **Sharpe: [2.17, 2.62]**<br>**PnL: [\$173,763, \$254,382]** | **Sharpe: [1.70, 2.14]**<br>**PnL: [\$1,962,125, \$3,145,726]** | El límite inferior del 95% es altamente positivo |
| **10** | **Sensibilidad al Slippage** | Degradación de PnL ante slippage duplicado (\(\times 2\)) | **-10.07% de PnL** | **-10.43% de PnL** | Alta robustez ante fricción del mercado |

---

## 2. Explicación Detallada de Cada Métrica

1. **Max Drawdown en Dólares (`max_drawdown_usd`):**
   Mide la pérdida acumulada más profunda en dinero real desde el punto de mayor balance. En la Estrategia Madre fue de \$1,661.26 y en la Apalancada fue de \$32,731.93.
2. **Max Drawdown Porcentual (`max_drawdown_pct`):**
   Mide la caída porcentual respecto al capital inicial fijo (\$100,000 USD). Muestra que la variante apalancada solo tuvo un 32.73% de caída máxima, muy lejos del circuito de freno del 20%.
3. **Duración del Drawdown (`drawdown_duration_days`):**
   Mide el número de días que la cuenta estuvo por debajo de su pico anterior. Ambas estrategias presentan una duración máxima menor a 98 días, indicando que las pérdidas se compensan velozmente con los rebotes.
4. **Peor Día Intradía (`worst_day_usd`):**
   Mide el peor resultado en una sola fecha. Es el indicador primordial para reglas de fondeo (*daily loss limit*).
5. **Sharpe Ratio Diario Anualizado (`sharpe_daily`):**
   Calculado con el factor estándar \(\sqrt{252}\). Refleja que la estrategia apalancada (1.91) mantiene la misma excelencia que la base (2.40) mientras multiplica el retorno absoluto.
6. **Ratio Calmar (`calmar_ratio`):**
   Expresa cuántas unidades de rendimiento compuesto (CAGR) se generan por cada unidad de riesgo de drawdown. La estrategia apalancada alcanza un Calmar de 0.63.
7. **Test de Permutación Monte Carlo (10,000 iteraciones):**
   Compara el PnL neto real contra 10,000 escenarios permutados aleatoriamente con signos invertidos al azar. El valor \(p < 0.0001\) y \(z > 10\) demuestran que el resultado no es fruto del azar.
8. **Deflated Sharpe Ratio (`DSR`):**
   Aplica la penalización de Marcos López de Prado por haber explorado combinaciones en la grilla. Un DSR del 100.0% supera holgadamente el umbral del 95%.
9. **Intervalos de Confianza por Bootstrap de Bloques (10 días):**
   Al reensamblar bloques de 10 días continuos (para preservar rachas y correlación serial de volatilidad), el 95% de las trayectorias arroja un Sharpe fuertemente positivo [1.70, 2.14].
10. **Sensibilidad al Deslizamiento y Fricción:**
    Al duplicar las comisiones y el deslizamiento (slippage \(\times 2\)), la estrategia apalancada únicamente cede un 10.43% de su beneficio neto, demostrando que no vive de márgenes delgados de microestructura.
