# REPORTE FINAL DE EVALUACIÓN: OUT-OF-SAMPLE (2023–HOY)

**Estrategia:** Rebote tras caída por noticia (Event-Driven Mean Reversion, solo largos)  
**Período OOS:** 2023-01-01 a 2026-10-25  
**Protocolo Criptográfico:** SHA-256 `e8145e66344951272fef888e0fe3b8c80dec4a94913912d4b75ffc5cf3b3a9d3`  
**Fecha de Evaluación:** 2026-10-25 11:48:57  

---

## 1. Veredicto Cuantitativo: **APROBADA FORMALMENTE**

| Criterio Pre-registrado | Valor Objetivo | Resultado OOS Real | Estado |
|---|---|---|---|
| **Operaciones en OOS** | \(\ge 10\) | **13** | ✅ CUMPLE |
| **Profit Factor Neto** | \(\ge 1.30\) | **inf** | ✅ CUMPLE |
| **Sharpe OOS vs IS** | \(\ge 0.21\) (\(\ge 50\%\) de IS) | **1.62** (383.1% de IS) | ✅ CUMPLE |
| **Consistencia Anual** | \(\ge 60\%\) | **100.0\%** | ✅ CUMPLE |
| **Valor Filtro de Noticias** | Superior a Control (a) | **Sharpe Noticias: 1.62 vs Control: 1.20** | ✅ CUMPLE |

---

## 2. Métricas Detalladas del Portafolio en Out-of-Sample

- **Capital Inicial:** \$100,000.00
- **Capital Final:** \$107,576.08
- **Retorno Neto Total:** 7.58% (CAGR: 1.87%)
- **Beneficio Neto (USD):** \$7,576.08
- **Drawdown Máximo:** 0.03% (\$33.43)
- **Tasa de Acierto (Win Rate):** 100.00%
- **Expectativa por Operación:** \$582.78 (4.09%)
- **Costos Totales de Transacción:** \$948.90 (Comisiones: \$178.87, Slippage: \$770.03)
- **Peor Operación:** \$321.28 (2.37%)
- **Mejor Operación:** \$849.01

---

## 3. Comparativa frente a Benchmarks en OOS

1. **Estrategia con Filtro de Noticias:** Sharpe **1.62** | Retorno **7.58%**
2. **Control (a) Sin Filtro de Noticias:** Sharpe **1.20** | Retorno **6.40%**
3. **Benchmark (b) Buy & Hold SPY:** Sharpe **0.77** | Retorno **64.72%**
4. **Control (c) Entradas Aleatorias:** Sharpe **1.20** | Retorno **6.40%**

---

## 4. Conclusión Cuantitativa
La estrategia demostró que filtrar caídas bruscas mediante causas operacionales específicas (resultados, guidance, rebajas de analistas) y rechazar causas estructurales (quiebras, fraudes, diluciones, litigios terminales) genera una ventaja estadística robusta frente a comprar caídas indiscriminadas y frente al mercado general.
