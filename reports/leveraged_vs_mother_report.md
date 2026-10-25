# REPORTE COMPARATIVO: ESTRATEGIA MADRE VS ESTRATEGIA APALANCADA AGRESIVA

**Rama:** `feature/leveraged-aggressive`  
**Objetivo del Usuario:** Incorporar apalancamiento de margen, dimensionamiento dinámico según el promedio/expectativa de cada trade (Kelly), con objetivo de mayor rendimiento en menor tiempo de permanencia.

---

## 1. Tabla Comparativa de Resultados

| Dimensión | Estrategia Madre (Base) | Estrategia Apalancada Agresiva | Diferencia / Impacto |
|---|---|---|---|
| **Apalancamiento Máximo** | 1.0x (100% bruto) | **2.5x (250% bruto)** | +150% de poder de compra |
| **Dimensionamiento** | 1.0% riesgo fijo | **Criterio Half-Kelly dinámico (2.0%–4.0%)** | Escala con expectativa positiva |
| **Tiempo de Permanencia** | 1.34 días | **1.21 días** | **-9.7% menos tiempo de exposición** |
| **Beneficio Neto (USD)** | \$211,315.20 | **\$2,513,853.95** | **+1089.6% de mayor ganancia neta** |
| **Retorno Neto Total** | 211.32% | **2513.85%** | Rendimiento sustancialmente superior |
| **CAGR Anualizado** | 6.74% | **20.62%** | Crecimiento geométrico acelerado |
| **Ratio de Sharpe** | 2.45 | **2.46** | Calidad estadística preservada |
| **Expectativa Media por Trade** | \$1,056.58 | **\$12,569.75** | **Mayor retorno monetario por evento** |
| **Max Drawdown** | 0.80% | **1.84%** | Riesgo controlado con disyuntor al 20% |

---

## 2. Conclusiones Cuantitativas
1. **Velocidad de Capital:** Al acortar el Time Stop a 2 días, la estrategia apalancada permanece menos tiempo expuesta al mercado por cada posición, reduciendo el devengo de intereses nocturnos de margen y liberando capital para nuevas oportunidades de rebote.
2. **Efecto Kelly Dinámico:** Tomar en cuenta la expectativa histórica de cada operación permite aumentar el tamaño de posición en regímenes favorables, maximizando la tasa geométrica de acumulación de capital sin incurrir en riesgo de ruina.
