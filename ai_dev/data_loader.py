# ============================================================
# データローダー (data_loader.py)
# ============================================================
# config.py の設定に基づいて、CSVを読み込み・結合し、
# 基本的なクレンジングと特徴量生成を行うモジュール。
# ============================================================

import os
import sys
import re
import pandas as pd

# Windows環境のエンコーディング対策
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
from datetime import datetime

# 同階層の config をインポート
from config import (
    DATA_DIR, MASTER_ARTIST, MASTER_VENUE, MASTER_TOUR, TARGET_COLUMN,
    CATEGORICAL_FEATURES, DESCRIPTION_KEYWORDS,
    RANDOM_SEED, DEBUG, get_data_files,
    USE_MANUAL_DATA, MANUAL_MERGE_KEYS,
)

def load_raw_data() -> pd.DataFrame:
    """
    config で指定された全CSVを読み込み、1つの DataFrame に結合する。
    各行にアーティスト名（slug）を付与する。
    """
    data_files = get_data_files()
    if not data_files:
        raise FileNotFoundError(f"データファイルが見つかりません: {DATA_DIR}")

    frames = []
    for fpath in data_files:
        slug = os.path.basename(fpath).replace("_master.csv", "")
        df = pd.read_csv(fpath, low_memory=False)
        df["group_slug"] = slug
        frames.append(df)
        if DEBUG:
            print(f"  [LOAD] {slug}: {len(df)} 件")

    combined = pd.concat(frames, ignore_index=True)
    print(f"[データ読み込み完了] 合計 {len(combined)} 件 ({len(data_files)} グループ)")
    return combined


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    基本的なデータクレンジングを行う。
    """
    df = df.copy()
    df[TARGET_COLUMN] = pd.to_numeric(df[TARGET_COLUMN], errors="coerce")
    before = len(df)
    df = df.dropna(subset=[TARGET_COLUMN])
    df = df[df[TARGET_COLUMN] > 0]
    after = len(df)
    if before != after:
        print(f"  [クレンジング] price 無効行を除外: {before} → {after} 件")

    for col in ["perf_date", "first_observed_at", "last_observed_at", "sold_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(1).astype(int)

    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    特徴量エンジニアリング。
    """
    df = df.copy()

    if "perf_date" in df.columns and "first_observed_at" in df.columns:
        df["days_until_event"] = (df["perf_date"] - df["first_observed_at"]).dt.days
        df.loc[df["days_until_event"] < -30, "days_until_event"] = np.nan

    if "first_observed_at" in df.columns and "last_observed_at" in df.columns:
        df["listing_duration_days"] = (df["last_observed_at"] - df["first_observed_at"]).dt.days

    if "perf_date" in df.columns:
        df["perf_day_of_week"] = df["perf_date"].dt.dayofweek

    if "perf_time" in df.columns:
        df["perf_hour"] = pd.to_datetime(df["perf_time"], format="%H:%M", errors="coerce").dt.hour

    if "raw_description" in df.columns:
        desc = df["raw_description"].fillna("")
        for flag_name, pattern in DESCRIPTION_KEYWORDS.items():
            df[flag_name] = desc.str.contains(pattern, flags=re.IGNORECASE, na=False).astype(int)

    if "ticket_tags" in df.columns:
        tags = df["ticket_tags"].fillna("")
        df["tag_doukkou"] = tags.str.contains("同行", na=False).astype(int)
        df["tag_jyouken_ari"] = tags.str.contains("条件あり", na=False).astype(int)

    from sklearn.preprocessing import LabelEncoder
    label_encoders = {}
    for col in CATEGORICAL_FEATURES + ["group_slug"]:
        if col in df.columns:
            le = LabelEncoder()
            df[col + "_encoded"] = le.fit_transform(df[col].fillna("__UNKNOWN__").astype(str))
            label_encoders[col] = le

    if "status" in df.columns:
        status_map = {"listing": 0, "sold": 1, "deleted": 2}
        df["status_encoded"] = df["status"].map(status_map).fillna(-1).astype(int)

    return df


def get_feature_columns(df: pd.DataFrame) -> list:
    """
    学習に使用する特徴量カラムのリストを返す。
    """
    exclude = {
        TARGET_COLUMN,
        "ticket_id", "created_at_unix", "seller_name", "seller_rating",
        "order_num", "raw_description", "details_fetched",
        "perf_date", "first_observed_at", "last_observed_at", "sold_at",
        "perf_time", "ticket_tags", "delivery_method",
        "event_id", "venue", "ticket_type", "name_type", "group_slug", "status",
        "lottery_date", "first_day", "last_day", "artist_id", "artist_name"
    }
    
    feature_cols = [c for c in df.columns if c not in exclude and df[c].dtype in [np.int64, np.float64, np.int32, np.float32, int, float]]
    return feature_cols


def load_manual_data() -> dict:
    """
    3つのマスタCSV（artist, venue, tour）を読み込み辞書で返す。
    """
    masters = {}
    for name, path in [("artist", MASTER_ARTIST), ("venue", MASTER_VENUE), ("tour", MASTER_TOUR)]:
        if os.path.exists(path):
            df = pd.read_csv(path, encoding="utf-8")
            masters[name] = df
        else:
            print(f"  [警告] マスタファイルが見つかりません: {path}")
            masters[name] = pd.DataFrame()
            
    # 日付カラムの変換 (tour)
    df_tour = masters.get("tour", pd.DataFrame())
    if not df_tour.empty:
        for col in ["lottery_date", "first_day", "last_day"]:
            if col in df_tour.columns:
                df_tour[col] = pd.to_datetime(df_tour[col], errors="coerce")
                
    return masters


def merge_manual_data(df: pd.DataFrame, masters: dict) -> pd.DataFrame:
    """
    チケットデータに3つのマスタデータを結合し、高度な特徴量を生成する。
    """
    if not masters or all(v.empty for v in masters.values()):
        print("  [スキップ] マスタデータが空のためマージをスキップ")
        return df

    df = df.copy()
    before = len(df)

    # 1. 会場マスタの結合 (venue)
    if not masters["venue"].empty:
        df_venue = masters["venue"].drop_duplicates(subset=["venue"])
        df_venue["capacity"] = pd.to_numeric(df_venue["capacity"], errors="coerce")
        df = df.merge(df_venue[["venue", "capacity"]], on="venue", how="left")

    # 2. ツアーマスタの結合 (event_id)
    if not masters["tour"].empty:
        df_tour = masters["tour"].drop_duplicates(subset=["event_id"])
        # artist_idが重複しないよう、必要な列だけ抽出
        use_cols = ["event_id", "base_price", "lottery_date", "seat_rule", "first_day", "last_day", "total_stages"]
        df = df.merge(df_tour[[c for c in use_cols if c in df_tour.columns]], on="event_id", how="left")

    # 3. アーティストマスタの結合 (group_slug -> artist_id)
    if not masters["artist"].empty:
        df_artist = masters["artist"].drop_duplicates(subset=["artist_id"])
        df_artist["fc_members"] = pd.to_numeric(df_artist["fc_members"], errors="coerce")
        # スクレイピング側の group_slug と結合
        df = df.merge(df_artist[["artist_id", "fc_members"]], left_on="group_slug", right_on="artist_id", how="left")

    # マージ成功率の表示 (定価が入ったかどうか)
    matched = df["base_price"].notna().sum() if "base_price" in df.columns else 0
    print(f"  [手動データ結合] {before} 件 → マッチ: {matched} 件 ({matched/before*100:.1f}%)")

    # --- 新規特徴量の生成 ---
    # 1. プレミアム差額・倍率
    if "base_price" in df.columns:
        df["base_price"] = pd.to_numeric(df["base_price"], errors="coerce")
        df["premium_over_base"] = df[TARGET_COLUMN] - df["base_price"]
        df["premium_ratio"] = df[TARGET_COLUMN] / df["base_price"].replace(0, np.nan)

    # 2. チケット倍率 (激戦度)
    if "fc_members" in df.columns and "capacity" in df.columns:
        # 簡易計算: FC会員数 / (キャパ × ツアー公演数) ※公演数がない場合はキャパのみ
        if "total_stages" in df.columns:
            total_stages = pd.to_numeric(df["total_stages"], errors="coerce").fillna(1)
            total_cap = df["capacity"] * total_stages
        else:
            total_cap = df["capacity"]
        df["ticket_multiplier"] = df["fc_members"] / total_cap.replace(0, np.nan)

    # 3. 当落日からの経過日数
    if "lottery_date" in df.columns and "first_observed_at" in df.columns:
        df["days_since_lottery"] = (df["first_observed_at"] - df["lottery_date"]).dt.days

    # 4. 初日・オーラスフラグ
    if "first_day" in df.columns and "perf_date" in df.columns:
        df["is_tour_first_day"] = (df["perf_date"] == df["first_day"]).astype(int)
    if "last_day" in df.columns and "perf_date" in df.columns:
        df["is_tour_last_day"] = (df["perf_date"] == df["last_day"]).astype(int)

    # 5. 座席発表後フラグ
    if "seat_rule" in df.columns and "perf_date" in df.columns and "first_observed_at" in df.columns:
        # seat_rule が数値（公演のX日前）と仮定
        rule_days = pd.to_numeric(df["seat_rule"], errors="coerce")
        seat_announce_date = df["perf_date"] - pd.to_timedelta(rule_days, unit='d')
        # 出品日が座席発表日以降であれば 1
        df["is_after_seat_announce"] = (df["first_observed_at"] >= seat_announce_date).astype(int)

    return df


def prepare_dataset():
    """
    メインのデータ準備パイプライン。
    読み込み → クレンジング → 特徴量生成 → 特徴量/目的変数の分離を行う。
    
    Returns:
        df: 全特徴量を含むDataFrame
        feature_cols: 学習に使う特徴量カラム名のリスト
    """
    print("=" * 50)
    print("  データ準備パイプライン開始")
    print("=" * 50)

    # 1. 読み込み
    df = load_raw_data()

    # 2. クレンジング
    df = clean_data(df)

    # 2.5. 手動データの結合（USE_MANUAL_DATA=True の場合のみ）
    if USE_MANUAL_DATA:
        print("\n--- 手動データ結合 ---")
        df_manual = load_manual_data()
        df = merge_manual_data(df, df_manual)
    else:
        print("\n[手動データ] OFF（config.py の USE_MANUAL_DATA で切替可能）")

    # 3. 特徴量エンジニアリング
    df = engineer_features(df)

    # 4. 特徴量カラムの決定
    feature_cols = get_feature_columns(df)
    print(f"\n[特徴量] 使用カラム ({len(feature_cols)} 個):")
    for c in feature_cols:
        print(f"  - {c}")

    print(f"\n[データセット準備完了] {len(df)} 件 × {len(feature_cols)} 特徴量")
    return df, feature_cols


if __name__ == "__main__":
    # 単体テスト: データの読み込みと特徴量生成のデバッグ
    df, feature_cols = prepare_dataset()
    print("\n--- サンプルデータ（先頭5件） ---")
    print(df[feature_cols + [TARGET_COLUMN]].head())
    print("\n--- 基本統計量 ---")
    print(df[feature_cols + [TARGET_COLUMN]].describe())
