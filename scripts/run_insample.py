"""Script de ejecución de la Etapa 5: In-Sample (2010-2019), Grilla y Walk-Forward."""
import json
import os
import sys
import pandas as pd

# Añadir raíz al sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import StrategyConfig
from src.analysis.grid_search import GridSearchAnalyzer
from src.analysis.walk_forward import WalkForwardAnalyzer
from src.data.generator import generate_market_environment
from src.data.prices import PriceDataManager


def main():
    print("=================================================================")
    print("ETAPA 5: BÚSQUEDA EN GRILLA IN-SAMPLE (2010-2019) Y WALK-FORWARD")
    print("=================================================================")

    # 1. Cargar entorno de mercado reproducible
    print("\n[1/4] Generando entorno de mercado multi-ticker y benchmark...")
    stocks_dict, spy_df, metadata_df, news_mgr = generate_market_environment(
        start_date="2010-01-01",
        end_date="2026-10-25",
        num_tickers=20,
        seed=42,
    )

    # 2. Filtrar estrictamente datos In-Sample (2010-2019)
    print("[2/4] Aislanto bloque temporal In-Sample (2010-01-01 a 2019-12-31)...")
    price_mgr = PriceDataManager()
    in_sample_stocks = {}
    for ticker, df in stocks_dict.items():
        in_sample_stocks[ticker] = price_mgr.filter_by_split(df, "in_sample")

    base_cfg = StrategyConfig()

    # 3. Ejecutar grilla pre-registrada
    print("[3/4] Evaluando combinaciones de la grilla (X, Take Profit, Time Stop)...")
    grid_analyzer = GridSearchAnalyzer(base_cfg, news_mgr)
    grid_df = grid_analyzer.run_grid(
        in_sample_stocks,
        drop_thresholds=(0.10, 0.15, 0.20),
        rebound_targets=(0.50, 0.75),
        time_stops=(3, 5),
    )

    print("\n--- RESULTADOS DE LA GRILLA (Ordenados por Sharpe) ---")
    cols_display = [
        "drop_pct", "rebound_target", "time_stop_days", "n_trades",
        "win_rate", "profit_factor", "sharpe_annualized", "max_drawdown_pct", "deflated_sharpe_prob"
    ]
    print(grid_df[cols_display].to_string(index=False))

    # Guardar resultados
    os.makedirs("reports", exist_ok=True)
    grid_df.to_csv("reports/insample_grid.csv", index=False)
    print("\nGrilla guardada en 'reports/insample_grid.csv'.")

    # 4. Walk-Forward dentro del In-Sample
    print("\n[4/4] Ejecutando Walk-Forward (3 años train / 1 año test rodante)...")
    wf_analyzer = WalkForwardAnalyzer(base_cfg, news_mgr)
    wf_df = wf_analyzer.run_in_sample_walk_forward(
        in_sample_stocks,
        train_years=3,
        test_years=1,
        start_year=2010,
        end_year=2019,
    )

    print("\n--- RESULTADOS DEL WALK-FORWARD IN-SAMPLE ---")
    if not wf_df.empty:
        wf_cols = [
            "window", "best_drop_pct", "best_rebound_target", "best_time_stop",
            "train_sharpe", "test_sharpe", "wfe_ratio", "test_profit_factor"
        ]
        print(wf_df[wf_cols].to_string(index=False))
        wf_df.to_csv("reports/insample_walk_forward.csv", index=False)
        print("Walk-Forward guardado en 'reports/insample_walk_forward.csv'.")
    else:
        print("Muestra insuficiente para ventanas rodantes.")

    # Parámetro óptimo seleccionado
    best = grid_df.iloc[0]
    best_params = {
        "drop_pct_threshold": float(best["drop_pct"]),
        "rebound_target_pct": float(best["rebound_target"]),
        "time_stop_days": int(best["time_stop_days"]),
        "in_sample_sharpe": float(best["sharpe_annualized"]),
        "in_sample_profit_factor": float(best["profit_factor"]),
        "in_sample_trades": int(best["n_trades"]),
        "deflated_sharpe_prob": float(best["deflated_sharpe_prob"]),
    }
    with open("reports/best_in_sample_params.json", "w", encoding="utf-8") as f:
        json.dump(best_params, f, indent=4)

    print(f"\nParámetros seleccionados formalmente: {best_params}")


if __name__ == "__main__":
    main()
