"""Script de ejecución de la Etapa 6: Validación (2020-2022), Comparativos y Robustez."""
import json
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import ExitConfig, StrategyConfig
from src.analysis.comparatives import BenchmarkComparisons
from src.analysis.metrics import compute_portfolio_metrics
from src.analysis.robustness import RobustnessAnalyzer
from src.backtest.engine import EventBacktestEngine
from src.data.generator import generate_market_environment
from src.data.prices import PriceDataManager


def main():
    print("=================================================================")
    print("ETAPA 6: VALIDACIÓN (2020-2022), COMPARATIVOS Y ROBUSTEZ")
    print("=================================================================")

    # 1. Cargar parámetros congelados de In-Sample
    params_file = "reports/best_in_sample_params.json"
    if os.path.exists(params_file):
        with open(params_file, "r", encoding="utf-8") as f:
            best_params = json.load(f)
    else:
        best_params = {
            "drop_pct_threshold": 0.10,
            "rebound_target_pct": 0.50,
            "time_stop_days": 5,
        }
    print(f"\nParámetros seleccionados en In-Sample: {best_params}")

    # 2. Cargar entorno y aislar bloque de Validación (2020-2022)
    print("\n[1/3] Aislanto bloque de Validación (2020-01-01 a 2022-12-31)...")
    stocks_dict, spy_df, metadata_df, news_mgr = generate_market_environment(seed=42)

    price_mgr = PriceDataManager()
    val_stocks = {}
    for ticker, df in stocks_dict.items():
        val_stocks[ticker] = price_mgr.filter_by_split(df, "validation")

    val_spy = price_mgr.filter_by_split(spy_df, "validation")

    cfg = StrategyConfig(
        exit=ExitConfig(
            rebound_target_pct=best_params["rebound_target_pct"],
            time_stop_days=best_params["time_stop_days"],
        )
    )

    # 3. Ejecutar comparativos obligatorios
    print("\n[2/3] Ejecutando comparativos obligatorios...")
    comparisons = BenchmarkComparisons(cfg, news_mgr)
    comp_results = comparisons.run_all_comparatives(
        stocks_data=val_stocks,
        spy_df=val_spy,
        drop_pct_threshold=best_params["drop_pct_threshold"],
    )

    print("\n--- COMPARATIVOS OBLIGATORIOS (VALIDACIÓN 2020-2022) ---")
    stk_m = comp_results["strategy_with_news"]
    no_news_m = comp_results["control_a_no_news_filter"]
    spy_m = comp_results["benchmark_b_spy_buy_and_hold"]
    rand_m = comp_results["control_c_random_entry"]

    print(f"Estrategia con filtro de noticias : Sharpe: {stk_m['sharpe_annualized']:.2f} | PF: {stk_m['profit_factor']:.2f} | Trades: {stk_m['n_trades']} | Ret: {stk_m['total_return_pct']*100:.1f}%")
    print(f"Control (a) - SIN filtro noticias : Sharpe: {no_news_m['sharpe_annualized']:.2f} | PF: {no_news_m['profit_factor']:.2f} | Trades: {no_news_m['n_trades']} | Ret: {no_news_m['total_return_pct']*100:.1f}%")
    print(f"Benchmark (b) - Buy & Hold SPY    : Sharpe: {spy_m['sharpe_annualized']:.2f} | MaxDD: {spy_m['max_drawdown_pct']*100:.1f}% | Ret: {spy_m['total_return_pct']*100:.1f}%")
    print(f"Control (c) - Entradas Aleatorias : Sharpe: {rand_m['mean_sharpe_annualized']:.2f} | PF: {rand_m['mean_profit_factor']:.2f} | Ret: {rand_m['mean_total_return_pct']*100:.1f}%")

    print(f"\nEvaluación del filtro de noticias: {comp_results['news_filter_added_value_check']['comment']}")

    # 4. Pruebas de estrés y robustez
    print("\n[3/3] Ejecutando batería de pruebas de robustez...")
    robustness = RobustnessAnalyzer(cfg, news_mgr)
    rob_results = robustness.evaluate_all_stress_tests(
        stocks_data=val_stocks,
        metadata_df=metadata_df,
        drop_pct_threshold=best_params["drop_pct_threshold"],
    )

    print("\n--- RESULTADOS DE ESTRÉS Y SENSIBILIDAD ---")
    base_m = rob_results["base_case"]
    slip2_m = rob_results["slippage_x2"]
    no20_m = rob_results["excluding_2020"]
    top10_m = rob_results["excluding_top_10_trades"]

    print(f"Caso Base Validación        : Sharpe: {base_m['sharpe_annualized']:.2f} | PF: {base_m['profit_factor']:.2f} | MaxDD: {base_m['max_drawdown_pct']*100:.1f}%")
    print(f"Estrés Slippage x2          : Sharpe: {slip2_m['sharpe_annualized']:.2f} | PF: {slip2_m['profit_factor']:.2f} | Ret: {slip2_m['total_return_pct']*100:.1f}%")
    print(f"Exclusión de 2020 (Covid)   : Sharpe: {no20_m['sharpe_annualized']:.2f} | PF: {no20_m['profit_factor']:.2f} | Ret: {no20_m['total_return_pct']*100:.1f}%")
    print(f"Exclusión Top 10 Trades     : PF: {top10_m.get('profit_factor', 0.0):.2f} | WinRate: {top10_m.get('win_rate', 0.0)*100:.1f}% | Restantes: {top10_m.get('remaining_trades', 0)}")

    print("\nAtribución por Sector:")
    for sec, stats in rob_results.get("sector_breakdown", {}).items():
        print(f"  - {sec:12s}: Trades: {stats['n_trades']:2d} | PF: {stats['profit_factor']:5.2f} | PnL: ${stats['total_net_pnl_usd']:,.2f}")

    # Guardar reporte
    val_export = {
        "best_params": best_params,
        "comparatives": comp_results,
        "robustness": rob_results,
    }
    with open("reports/validation_results.json", "w", encoding="utf-8") as f:
        json.dump(val_export, f, indent=4, default=str)

    print("\nResultados completos de validación exportados a 'reports/validation_results.json'.")


if __name__ == "__main__":
    main()
