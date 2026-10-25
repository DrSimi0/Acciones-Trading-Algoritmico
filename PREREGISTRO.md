# DOCUMENTO DE PREREGISTRO Y PROTOCOLO CONGELADO

**Estrategia:** Rebote tras caída por noticia (Event-Driven Mean Reversion, solo largos)  
**Fecha de Congelación:** 2026-10-25T17:48:23.641208Z  
**Hash SHA-256 de Validación:** `e8145e66344951272fef888e0fe3b8c80dec4a94913912d4b75ffc5cf3b3a9d3`  

---

## 1. Parámetros Congelados de la Estrategia (Invariables para OOS)

| Parámetro | Valor Congelado | Justificación Cuantitativa |
|---|---|---|
| **Umbral de Caída (\(X\))** | **10%** | Óptimo en In-Sample con mayor significancia estadística |
| **Take Profit** | **50% de recuperación** | Captura rebote medio sin sobre-exposición al drift |
| **Stop Loss** | **Mínimo entre \(-1.5 	imes 	ext{ATR}(14)\) y \(-8\%\)** | Control estricto de riesgo con modelado de gaps reales |
| **Time Stop** | **Día 3 al cierre** | Cierre forzoso para evitar estancamiento del capital |
| **Filtro de Aceleración** | **Cancelar si \(t+1\) abre \(< -5\%\)** | Evita entrar en caídas en cascada no contenidas |
| **Riesgo por Operación** | **1.0% del capital** | Dimensionamiento basado en stop loss |
| **Límite de Concurrencia** | **Máximo 5 posiciones (100% bruto)** | Diversificación de eventos sin apalancamiento |
| **Disyuntor de Portafolio** | **Pausa si drawdown \(> 15\%\)** | Protección del capital ante rachas anómalas |
| **Costos Modelados** | **\$0.005/acción + 10-30 pb slippage** | Costos realistas institucionales y ejecución al open |

---

## 2. Métricas Obtenidas en In-Sample (2010–2019)
- **Sharpe Anualizado:** 0.42
- **Profit Factor Neto:** 1.43
- **Nº de Operaciones:** 107
- **Deflated Sharpe Ratio (DSR):** 0.7% de significancia estadística

---

## 3. Criterios de Aprobación Formales para el Out-of-Sample (OOS 2023–hoy)

> [!IMPORTANT]
> Estos criterios fueron registrados y bloqueados de forma **previa e inviolable** antes de acceder al bloque de datos Out-of-Sample.

1. **Muestra Estadística:** Al menos **35 operaciones** en el período OOS (150 en el acumulado total).
2. **Profit Factor Neto:** \(	ext{PF} \ge \mathbf{1.30}\) tras deducir todas las comisiones y deslizamientos de evento.
3. **Consistencia Anual:** Rendimiento positivo en al menos el **70%** de los años evaluados.
4. **Degradación Máxima IS \(	o\) OOS:** El Sharpe anualizado en OOS no debe ser inferior al 50% del Sharpe de In-Sample (Umbral mínimo: \(	ext{Sharpe} \ge \mathbf{0.21}\)).
5. **Aporte de Valor del Filtro de Noticias:** El sistema con filtro de noticias debe superar en rentabilidad ajustada al riesgo al caso control (a) sin filtro de noticias.

---
**Firma:** Antigravity Quant Engine — Protocolo Criptográfico Versionado.
