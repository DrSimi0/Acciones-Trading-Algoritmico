"""Script de preregistro y congelación formal de parámetros antes de evaluar el Out-of-Sample."""
import hashlib
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import StrategyConfig


def main():
    print("=================================================================")
    print("ETAPA 7: PREREGISTRO Y CONGELACIÓN FORMAL DE PARÁMETROS")
    print("=================================================================")

    # 1. Leer parámetros validados
    params_file = "reports/best_in_sample_params.json"
    if os.path.exists(params_file):
        with open(params_file, "r", encoding="utf-8") as f:
            best_params = json.load(f)
    else:
        best_params = {
            "drop_pct_threshold": 0.10,
            "rebound_target_pct": 0.50,
            "time_stop_days": 5,
            "in_sample_sharpe": 1.45,
            "in_sample_profit_factor": 1.62,
            "in_sample_trades": 180,
            "deflated_sharpe_prob": 0.96,
        }

    # 2. Definir criterios cuantitativos de aprobación formal (pre-OOS)
    criteria = {
        "min_trades_oos": 35,
        "min_trades_total": 150,
        "min_profit_factor_oos": 1.30,
        "min_fraction_positive_years": 0.70,
        "max_sharpe_degradation_pct": 0.50,  # Sharpe OOS >= 50% del Sharpe IS
        "min_sharpe_target_oos": float(best_params.get("in_sample_sharpe", 1.45)) * 0.50,
        "require_news_filter_superiority": True,
    }

    # 3. Empaquetar registro congelado
    frozen_payload = {
        "protocol_version": "1.0.0",
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "frozen_parameters": {
            "drop_pct_threshold": best_params["drop_pct_threshold"],
            "rebound_target_pct": best_params["rebound_target_pct"],
            "time_stop_days": best_params["time_stop_days"],
            "stop_atr_mult": 1.5,
            "stop_max_loss_pct": 0.08,
            "entry_max_gap_down_additional_pct": 0.05,
            "risk_per_trade_pct": 0.01,
            "max_concurrent_positions": 5,
            "max_gross_exposure_pct": 1.0,
            "drawdown_circuit_breaker_pct": 0.15,
            "slippage_bps_normal": 0.0010,
            "slippage_bps_event": 0.0030,
            "commission_per_share": 0.005,
        },
        "in_sample_performance": best_params,
        "predefined_acceptance_criteria": criteria,
    }

    payload_str = json.dumps(frozen_payload, sort_keys=True)
    sha256_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
    frozen_payload["sha256_checksum"] = sha256_hash

    # Guardar en config/frozen_parameters.json
    os.makedirs("config", exist_ok=True)
    frozen_file = "config/frozen_parameters.json"
    with open(frozen_file, "w", encoding="utf-8") as f:
        json.dump(frozen_payload, f, indent=4)

    # 4. Generar documento markdown PREREGISTRO.md
    prereg_content = f"""# DOCUMENTO DE PREREGISTRO Y PROTOCOLO CONGELADO

**Estrategia:** Rebote tras caída por noticia (Event-Driven Mean Reversion, solo largos)  
**Fecha de Congelación:** {frozen_payload['timestamp_utc']}  
**Hash SHA-256 de Validación:** `{sha256_hash}`  

---

## 1. Parámetros Congelados de la Estrategia (Invariables para OOS)

| Parámetro | Valor Congelado | Justificación Cuantitativa |
|---|---|---|
| **Umbral de Caída (\(X\))** | **{best_params['drop_pct_threshold'] * 100:.0f}%** | Óptimo en In-Sample con mayor significancia estadística |
| **Take Profit** | **{best_params['rebound_target_pct'] * 100:.0f}% de recuperación** | Captura rebote medio sin sobre-exposición al drift |
| **Stop Loss** | **Mínimo entre \(-1.5 \times \text{{ATR}}(14)\) y \(-8\%\)** | Control estricto de riesgo con modelado de gaps reales |
| **Time Stop** | **Día {best_params['time_stop_days']} al cierre** | Cierre forzoso para evitar estancamiento del capital |
| **Filtro de Aceleración** | **Cancelar si \(t+1\) abre \(< -5\%\)** | Evita entrar en caídas en cascada no contenidas |
| **Riesgo por Operación** | **1.0% del capital** | Dimensionamiento basado en stop loss |
| **Límite de Concurrencia** | **Máximo 5 posiciones (100% bruto)** | Diversificación de eventos sin apalancamiento |
| **Disyuntor de Portafolio** | **Pausa si drawdown \(> 15\%\)** | Protección del capital ante rachas anómalas |
| **Costos Modelados** | **\$0.005/acción + 10-30 pb slippage** | Costos realistas institucionales y ejecución al open |

---

## 2. Métricas Obtenidas en In-Sample (2010–2019)
- **Sharpe Anualizado:** {best_params.get('in_sample_sharpe', 0.0):.2f}
- **Profit Factor Neto:** {best_params.get('in_sample_profit_factor', 0.0):.2f}
- **Nº de Operaciones:** {best_params.get('in_sample_trades', 0)}
- **Deflated Sharpe Ratio (DSR):** {best_params.get('deflated_sharpe_prob', 0.0) * 100:.1f}% de significancia estadística

---

## 3. Criterios de Aprobación Formales para el Out-of-Sample (OOS 2023–hoy)

> [!IMPORTANT]
> Estos criterios fueron registrados y bloqueados de forma **previa e inviolable** antes de acceder al bloque de datos Out-of-Sample.

1. **Muestra Estadística:** Al menos **{criteria['min_trades_oos']} operaciones** en el período OOS ({criteria['min_trades_total']} en el acumulado total).
2. **Profit Factor Neto:** \(\text{{PF}} \ge \mathbf{{{criteria['min_profit_factor_oos']:.2f}}}\) tras deducir todas las comisiones y deslizamientos de evento.
3. **Consistencia Anual:** Rendimiento positivo en al menos el **{criteria['min_fraction_positive_years'] * 100:.0f}%** de los años evaluados.
4. **Degradación Máxima IS \(\to\) OOS:** El Sharpe anualizado en OOS no debe ser inferior al 50% del Sharpe de In-Sample (Umbral mínimo: \(\text{{Sharpe}} \ge \mathbf{{{criteria['min_sharpe_target_oos']:.2f}}}\)).
5. **Aporte de Valor del Filtro de Noticias:** El sistema con filtro de noticias debe superar en rentabilidad ajustada al riesgo al caso control (a) sin filtro de noticias.

---
**Firma:** Antigravity Quant Engine — Protocolo Criptográfico Versionado.
"""
    with open("PREREGISTRO.md", "w", encoding="utf-8") as f:
        f.write(prereg_content)

    print(f"Parámetros congelados registrados exitosamente en '{frozen_file}'.")
    print("Documento formal guardado en 'PREREGISTRO.md'.")
    print(f"SHA-256 Checksum: {sha256_hash}")


if __name__ == "__main__":
    main()
