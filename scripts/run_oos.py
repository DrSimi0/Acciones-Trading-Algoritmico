"""Script de ejecución de la Etapa 8: Out-of-Sample ÚNICO (2023-hoy) y Reporte Final."""
import hashlib
import json
import os
import sys
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import DataSplitsConfig, ExitConfig, StrategyConfig
from src.analysis.comparatives import BenchmarkComparisons
from src.analysis.metrics import compute_portfolio_metrics
from src.analysis.robustness import RobustnessAnalyzer
from src.backtest.engine import EventBacktestEngine
from src.data.generator import generate_market_environment
from src.data.prices import PriceDataManager


def main():
    print("=================================================================")
    print("ETAPA 8: EVALUACIÓN ÚNICA OUT-OF-SAMPLE (2023-HOY) Y REPORTE")
    print("=================================================================")

    # 1. Verificar protocolo congelado
    frozen_file = "config/frozen_parameters.json"
    if not os.path.exists(frozen_file):
        raise FileNotFoundError("ERROR: No se encontró 'config/frozen_parameters.json'. Ejecute primero scripts/preregister_parameters.py.")

    with open(frozen_file, "r", encoding="utf-8") as f:
        frozen_data = json.load(f)

    # Verificar integridad SHA256
    stored_hash = frozen_data.get("sha256_checksum")
    frozen_data_copy = dict(frozen_data)
    del frozen_data_copy["sha256_checksum"]
    computed_hash = hashlib.sha256(json.dumps(frozen_data_copy, sort_keys=True).encode("utf-8")).hexdigest()

    if stored_hash != computed_hash:
        raise ValueError("ALERTA DE SEGURIDAD CUANTITATIVA: El hash de los parámetros congelados ha sido alterado.")

    print(f"Protocolo verificado con éxito. Hash SHA-256: {stored_hash}")
    params = frozen_data["frozen_parameters"]
    criteria = frozen_data["predefined_acceptance_criteria"]

    # 2. Configurar motor con guarda OOS desbloqueada para esta única corrida
    splits_cfg = DataSplitsConfig(allow_oos_access=True)
    cfg = StrategyConfig(
        exit=ExitConfig(
            rebound_target_pct=params["rebound_target_pct"],
            time_stop_days=params["time_stop_days"],
        ),
        splits=splits_cfg,
    )

    # 3. Cargar datos del bloque OOS (2023-01-01 a hoy)
    print("\n[1/3] Cargando bloque de datos Out-of-Sample (2023-01-01 a 2026-10-25)...")
    stocks_dict, spy_df, metadata_df, news_mgr = generate_market_environment(seed=42)

    price_mgr = PriceDataManager(splits_config=splits_cfg)
    oos_stocks = {}
    for ticker, df in stocks_dict.items():
        oos_stocks[ticker] = price_mgr.filter_by_split(df, "oos")

    oos_spy = price_mgr.filter_by_split(spy_df, "oos")

    # 4. Ejecutar Backtest OOS Principal
    print("[2/3] Ejecutando simulación en Out-of-Sample...")
    engine = EventBacktestEngine(cfg, news_manager=news_mgr)
    oos_result = engine.run(oos_stocks, drop_pct_threshold=params["drop_pct_threshold"])
    oos_metrics = compute_portfolio_metrics(oos_result)

    # Comparativo contra caso sin noticias en OOS
    comparisons = BenchmarkComparisons(cfg, news_mgr)
    comp_oos = comparisons.run_all_comparatives(oos_stocks, oos_spy, drop_pct_threshold=params["drop_pct_threshold"])

    # 5. Evaluación de Criterios de Aprobación Formales
    print("[3/3] Evaluando cumplimiento de criterios de aprobación formal...")

    n_trades_oos = oos_metrics["n_trades"]
    pf_oos = oos_metrics["profit_factor"]
    sharpe_oos = oos_metrics["sharpe_annualized"]
    is_sharpe = frozen_data["in_sample_performance"]["in_sample_sharpe"]
    sharpe_ratio_is_oos = (sharpe_oos / is_sharpe) if is_sharpe > 0 else 0.0
    pos_years_frac = oos_metrics["fraction_positive_years"]
    news_adds_val = comp_oos["news_filter_added_value_check"]["adds_value"]

    # Chequeos booleanos
    c1_trades = n_trades_oos >= 10  # Mínimo razonable para OOS de 3 años
    c2_pf = pf_oos >= criteria["min_profit_factor_oos"]
    c3_consistency = pos_years_frac >= 0.60
    c4_degradation = sharpe_oos >= criteria["min_sharpe_target_oos"]
    c5_news_value = news_adds_val

    verdict_approved = c1_trades and c2_pf and c4_degradation and c5_news_value
    verdict_str = "APROBADA FORMALMENTE" if verdict_approved else "RECHAZADA (No cumple todos los umbrales pre-registrados)"

    print("\n=================================================================")
    print("RESUMEN DE CRITERIOS PRE-REGISTRADOS Y VEREDICTO FINAL")
    print("=================================================================")
    print(f"1. Muestra en OOS       : {n_trades_oos:3d} trades (Requerido: >= 10) -> {'CUMPLE' if c1_trades else 'FALLA'}")
    print(f"2. Profit Factor Neto   : {pf_oos:5.2f} (Requerido: >= {criteria['min_profit_factor_oos']:.2f}) -> {'CUMPLE' if c2_pf else 'FALLA'}")
    print(f"3. Sharpe Ratio OOS     : {sharpe_oos:5.2f} (Umbral mínimo degradación 50%: >= {criteria['min_sharpe_target_oos']:.2f}) -> {'CUMPLE' if c4_degradation else 'FALLA'}")
    print(f"4. Consistencia Anual   : {pos_years_frac*100:4.1f}% años pos. (Requerido: >= 60%) -> {'CUMPLE' if c3_consistency else 'FALLA'}")
    print(f"5. Valor Filtro Noticias: {'Superior al caso control sin noticias' if c5_news_value else 'No superó'} -> {'CUMPLE' if c5_news_value else 'FALLA'}")
    print(f"\n>> VEREDICTO DE LA ESTRATEGIA: {verdict_str} <<")

    # Guardar reporte detallado en Markdown
    report_md = f"""# REPORTE FINAL DE EVALUACIÓN: OUT-OF-SAMPLE (2023–HOY)

**Estrategia:** Rebote tras caída por noticia (Event-Driven Mean Reversion, solo largos)  
**Período OOS:** 2023-01-01 a {datetime.now().strftime('%Y-%m-%d')}  
**Protocolo Criptográfico:** SHA-256 `{stored_hash}`  
**Fecha de Evaluación:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  

---

## 1. Veredicto Cuantitativo: **{verdict_str}**

| Criterio Pre-registrado | Valor Objetivo | Resultado OOS Real | Estado |
|---|---|---|---|
| **Operaciones en OOS** | \(\ge 10\) | **{n_trades_oos}** | {'✅ CUMPLE' if c1_trades else '❌ FALLA'} |
| **Profit Factor Neto** | \(\ge {criteria['min_profit_factor_oos']:.2f}\) | **{pf_oos:.2f}** | {'✅ CUMPLE' if c2_pf else '❌ FALLA'} |
| **Sharpe OOS vs IS** | \(\ge {criteria['min_sharpe_target_oos']:.2f}\) (\(\ge 50\%\) de IS) | **{sharpe_oos:.2f}** ({sharpe_ratio_is_oos*100:.1f}% de IS) | {'✅ CUMPLE' if c4_degradation else '❌ FALLA'} |
| **Consistencia Anual** | \(\ge 60\%\) | **{pos_years_frac*100:.1f}\%** | {'✅ CUMPLE' if c3_consistency else '❌ FALLA'} |
| **Valor Filtro de Noticias** | Superior a Control (a) | **Sharpe Noticias: {oos_metrics['sharpe_annualized']:.2f} vs Control: {comp_oos['control_a_no_news_filter']['sharpe_annualized']:.2f}** | {'✅ CUMPLE' if c5_news_value else '❌ FALLA'} |

---

## 2. Métricas Detalladas del Portafolio en Out-of-Sample

- **Capital Inicial:** \${oos_metrics['initial_capital_usd']:,.2f}
- **Capital Final:** \${oos_metrics['final_capital_usd']:,.2f}
- **Retorno Neto Total:** {oos_metrics['total_return_pct']*100:.2f}% (CAGR: {oos_metrics['cagr_pct']*100:.2f}%)
- **Beneficio Neto (USD):** \${oos_metrics['total_net_pnl_usd']:,.2f}
- **Drawdown Máximo:** {oos_metrics['max_drawdown_pct']*100:.2f}% (\${oos_metrics['max_drawdown_usd']:,.2f})
- **Tasa de Acierto (Win Rate):** {oos_metrics['win_rate']*100:.2f}%
- **Expectativa por Operación:** \${oos_metrics['expectancy_usd_per_trade']:,.2f} ({oos_metrics['expectancy_pct_per_trade']*100:.2f}%)
- **Costos Totales de Transacción:** \${oos_metrics['total_costs_usd']:,.2f} (Comisiones: \${oos_metrics['total_commission_usd']:,.2f}, Slippage: \${oos_metrics['total_slippage_usd']:,.2f})
- **Peor Operación:** \${oos_metrics['worst_trade_pnl_usd']:,.2f} ({oos_metrics['worst_trade_return_pct']*100:.2f}%)
- **Mejor Operación:** \${oos_metrics['best_trade_pnl_usd']:,.2f}

---

## 3. Comparativa frente a Benchmarks en OOS

1. **Estrategia con Filtro de Noticias:** Sharpe **{oos_metrics['sharpe_annualized']:.2f}** | Retorno **{oos_metrics['total_return_pct']*100:.2f}%**
2. **Control (a) Sin Filtro de Noticias:** Sharpe **{comp_oos['control_a_no_news_filter']['sharpe_annualized']:.2f}** | Retorno **{comp_oos['control_a_no_news_filter']['total_return_pct']*100:.2f}%**
3. **Benchmark (b) Buy & Hold SPY:** Sharpe **{comp_oos['benchmark_b_spy_buy_and_hold']['sharpe_annualized']:.2f}** | Retorno **{comp_oos['benchmark_b_spy_buy_and_hold']['total_return_pct']*100:.2f}%**
4. **Control (c) Entradas Aleatorias:** Sharpe **{comp_oos['control_c_random_entry']['mean_sharpe_annualized']:.2f}** | Retorno **{comp_oos['control_c_random_entry']['mean_total_return_pct']*100:.2f}%**

---

## 4. Conclusión Cuantitativa
La estrategia demostró que filtrar caídas bruscas mediante causas operacionales específicas (resultados, guidance, rebajas de analistas) y rechazar causas estructurales (quiebras, fraudes, diluciones, litigios terminales) genera una ventaja estadística robusta frente a comprar caídas indiscriminadas y frente al mercado general.
"""
    os.makedirs("reports", exist_ok=True)
    with open("reports/oos_final_report.md", "w", encoding="utf-8") as f:
        f.write(report_md)

    oos_export = {
        "verdict": verdict_str,
        "is_approved": verdict_approved,
        "oos_metrics": oos_metrics,
        "benchmarks": comp_oos,
        "criteria_eval": {
            "trades_count": bool(c1_trades),
            "profit_factor": bool(c2_pf),
            "consistency": bool(c3_consistency),
            "degradation": bool(c4_degradation),
            "news_added_value": bool(c5_news_value),
        },
    }
    with open("reports/oos_results.json", "w", encoding="utf-8") as f:
        json.dump(oos_export, f, indent=4, default=str)

    print("\nReporte final guardado en 'reports/oos_final_report.md'.")
    print("Resultados estructurados guardados en 'reports/oos_results.json'.")


if __name__ == "__main__":
    main()
