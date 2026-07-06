# ============================================================
# LightGBM トレーナー (train_lightgbm.py)
# ============================================================
# パターンA: 安定志向の LightGBM 回帰モデル。
# config.py の設定に基づいて学習・評価・お買い得チケット抽出を行う。
# ============================================================

import os
import sys

# Windows環境のエンコーディング対策
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding="utf-8")
import json
import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split, KFold
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

# 同階層のモジュールをインポート
from config import (
    LGBM_PARAMS, TARGET_COLUMN, TEST_SPLIT_RATIO,
    CV_FOLDS, RANDOM_SEED, OUTPUT_DIR, BARGAIN_TOP_N, DEBUG,
)
from data_loader import prepare_dataset


def train_and_evaluate():
    """
    メインの学習・評価パイプライン。
    1. データ準備
    2. Train/Test 分割
    3. LightGBM 学習
    4. 評価指標の算出
    5. 特徴量重要度の表示
    6. お買い得チケットの抽出
    """

    # ===== 1. データ準備 =====
    df, feature_cols = prepare_dataset()

    # 学習対象のデータを限定（price と 特徴量が揃っている行）
    df_valid = df.dropna(subset=feature_cols + [TARGET_COLUMN])
    print(f"\n[学習対象] 有効レコード: {len(df_valid)} 件")

    X = df_valid[feature_cols].values
    y = df_valid[TARGET_COLUMN].values

    # ===== 2. Train/Test 分割 =====
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SPLIT_RATIO, random_state=RANDOM_SEED
    )
    print(f"  Train: {len(X_train)} 件 / Test: {len(X_test)} 件")

    # ===== 3. LightGBM 学習 =====
    print("\n" + "=" * 50)
    print("  LightGBM 学習開始")
    print("=" * 50)

    params = {k: v for k, v in LGBM_PARAMS.items() if k not in ("n_estimators", "early_stopping_rounds")}
    
    train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
    valid_data = lgb.Dataset(X_test, label=y_test, feature_name=feature_cols, reference=train_data)

    callbacks = [
        lgb.log_evaluation(period=100),
        lgb.early_stopping(stopping_rounds=LGBM_PARAMS.get("early_stopping_rounds", 50)),
    ]

    model = lgb.train(
        params,
        train_data,
        num_boost_round=LGBM_PARAMS.get("n_estimators", 1000),
        valid_sets=[train_data, valid_data],
        valid_names=["train", "valid"],
        callbacks=callbacks,
    )

    # ===== 4. 評価 =====
    print("\n" + "=" * 50)
    print("  評価結果")
    print("=" * 50)

    y_pred = model.predict(X_test)

    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    print(f"  RMSE : {rmse:,.0f} 円")
    print(f"  MAE  : {mae:,.0f} 円")
    print(f"  R²   : {r2:.4f}")

    # 誤差率（平均価格に対する RMSE の割合）
    mean_price = np.mean(y_test)
    error_rate = rmse / mean_price * 100
    print(f"  誤差率: {error_rate:.1f}% (平均価格 {mean_price:,.0f} 円に対する RMSE)")

    # ===== 5. 特徴量重要度 =====
    print("\n" + "-" * 50)
    print("  特徴量重要度 (gain)")
    print("-" * 50)

    importance = model.feature_importance(importance_type="gain")
    imp_df = pd.DataFrame({
        "feature": feature_cols,
        "importance": importance
    }).sort_values("importance", ascending=False)

    for _, row in imp_df.head(15).iterrows():
        bar = "█" * int(row["importance"] / imp_df["importance"].max() * 30)
        print(f"  {row['feature']:30s} {row['importance']:>12.0f}  {bar}")

    # ===== 6. モデルと結果の保存 =====
    model_path = os.path.join(OUTPUT_DIR, "lightgbm_model.txt")
    model.save_model(model_path)
    print(f"\n[保存完了] モデル: {model_path}")

    # 評価結果の保存
    results = {
        "model_type": "lightgbm",
        "train_size": len(X_train),
        "test_size": len(X_test),
        "rmse": float(rmse),
        "mae": float(mae),
        "r2": float(r2),
        "error_rate_pct": float(error_rate),
        "mean_price": float(mean_price),
        "feature_importance": imp_df.to_dict(orient="records"),
    }
    results_path = os.path.join(OUTPUT_DIR, "evaluation_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[保存完了] 評価結果: {results_path}")

    return model, results


if __name__ == "__main__":
    train_and_evaluate()
