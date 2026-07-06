# ============================================================
# 検証1: ランダムサンプリング検証 (eval_random_sample.py)
# ============================================================
# 全データからランダムに N 件を抽出し、金額以外のデータから
# 価格を予測。予測値 vs 実際の価格を1件ずつ見比べる。
# ============================================================

import os
import sys

# Windows環境のエンコーディング対策
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import lightgbm as lgb
import matplotlib.pyplot as plt
import japanize_matplotlib  # 日本語フォント用

from config import OUTPUT_DIR, TARGET_COLUMN, RANDOM_SEED
from data_loader import prepare_dataset

def eval_random_sample(n_samples=30, seed=None):
    """
    ランダムに n_samples 件を抽出して予測し、
    1件ずつ「実際の価格 vs 予測価格」を表示 + 全体のMAE/RMSEを算出。
    """
    seed = seed or RANDOM_SEED

    # --- データ準備 ---
    df, feature_cols = prepare_dataset()
    df_valid = df.dropna(subset=feature_cols + [TARGET_COLUMN])

    # --- モデル読み込み ---
    model_path = os.path.join(OUTPUT_DIR, "lightgbm_model.txt")
    if not os.path.exists(model_path):
        print("[エラー] 学習済みモデルが見つかりません。先に train_lightgbm.py を実行してください。")
        return
    model = lgb.Booster(model_file=model_path)

    # --- ランダムサンプリング ---
    sample = df_valid.sample(n=min(n_samples, len(df_valid)), random_state=seed)

    X_sample = sample[feature_cols].values
    y_actual = sample[TARGET_COLUMN].values
    y_pred = model.predict(X_sample)

    # --- 1件ずつ表示 ---
    print("\n" + "=" * 70)
    print(f"  ランダムサンプリング検証 ({len(sample)} 件)")
    print("=" * 70)
    print(f"  {'#':>3}  {'グループ':<14} {'会場':<20} {'実際':>10} {'予測':>10} {'誤差':>10}")
    print("-" * 70)

    errors = []
    for i, (idx, row) in enumerate(sample.iterrows(), 1):
        actual = y_actual[i - 1]
        pred = y_pred[i - 1]
        error = pred - actual
        errors.append(abs(error))

        group = row.get("group_slug", "?")[:12]
        venue = str(row.get("venue", "?"))[:18]

        # 誤差の大きさに応じてマーカーを付ける
        if abs(error) < 3000:
            marker = "◎"
        elif abs(error) < 10000:
            marker = "○"
        elif abs(error) < 30000:
            marker = "△"
        else:
            marker = "✗"

        print(f"  {i:>3}  {group:<14} {venue:<20} {actual:>10,.0f} {pred:>10,.0f} {error:>+10,.0f} {marker}")

    # --- 全体の統計 ---
    mae = np.mean(errors)
    rmse = np.sqrt(np.mean(np.array(errors) ** 2))
    median_ae = np.median(errors)

    print("\n" + "=" * 70)
    print("  サマリー")
    print("=" * 70)
    print(f"  MAE（平均絶対誤差）  : {mae:>10,.0f} 円")
    print(f"  RMSE（二乗平均誤差） : {rmse:>10,.0f} 円")
    print(f"  中央値絶対誤差       : {median_ae:>10,.0f} 円")
    print(f"  平均実売価格         : {np.mean(y_actual):>10,.0f} 円")
    print(f"  誤差率（MAE/平均価格）: {mae / np.mean(y_actual) * 100:.1f}%")
    print()
    print(f"  ◎ 誤差 3千円以内  : {sum(1 for e in errors if e < 3000):>3} 件")
    print(f"  ○ 誤差 1万円以内  : {sum(1 for e in errors if e < 10000):>3} 件")
    print(f"  △ 誤差 3万円以内  : {sum(1 for e in errors if e < 30000):>3} 件")
    print(f"  ✗ 誤差 3万円超    : {sum(1 for e in errors if e >= 30000):>3} 件")
    print("=" * 70)

    # --- グラフの描画 ---
    plt.figure(figsize=(8, 8))
    
    # 散布図のプロット
    plt.scatter(y_actual, y_pred, alpha=0.7, c='dodgerblue', edgecolors='w', s=60, label='予測結果')
    
    # 理想線 (y = x)
    max_val = max(max(y_actual), max(y_pred)) * 1.05
    plt.plot([0, max_val], [0, max_val], 'r--', label='理想的な予測 (誤差0)')
    
    plt.xlim(0, max_val)
    plt.ylim(0, max_val)
    
    plt.title(f'LightGBM 価格予測精度 (ランダム {len(sample)} 件)\nMAE: {mae:,.0f}円', fontsize=14)
    plt.xlabel('実際の価格 (円)', fontsize=12)
    plt.ylabel('予測された価格 (円)', fontsize=12)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(loc='upper left')
    
    # R² 等をテキストで表示
    r2 = 1 - (np.sum((y_actual - y_pred)**2) / np.sum((y_actual - np.mean(y_actual))**2))
    plt.text(max_val*0.05, max_val*0.85, f"R² (決定係数): {r2:.3f}\nRMSE: {rmse:,.0f}円", 
             bbox=dict(facecolor='white', alpha=0.8, edgecolor='gray'))
    
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    eval_random_sample(n_samples=30)
