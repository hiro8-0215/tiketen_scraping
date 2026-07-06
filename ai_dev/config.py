# ============================================================
# AI開発 設定ファイル (config.py)
# ============================================================
# このファイルを編集することで、学習データ・モデル・パラメータを
# 一括で制御できます。
# ============================================================

import os

# ============================================================
# 1. パス設定
# ============================================================

# プロジェクトルート（このファイルの1つ上の階層）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- 学習データの日付 ---
# tiketen_date_data 内のフォルダ名を指定（例: "data_6_28"）
# "latest" を指定すると data/ 直下の最新マスターを使用
TRAIN_DATA_DATE = "data_6_28"

# データディレクトリ（自動解決）
if TRAIN_DATA_DATE == "latest":
    DATA_DIR = os.path.join(PROJECT_ROOT, "data")
else:
    DATA_DIR = os.path.join(PROJECT_ROOT, "tiketen_date_data", TRAIN_DATA_DATE)

# 手動データ（マスタデータ）のパス
MANUAL_DATA_DIR = os.path.join(PROJECT_ROOT, "手動_data")
MASTER_ARTIST = os.path.join(MANUAL_DATA_DIR, "master_artist.csv")
MASTER_VENUE = os.path.join(MANUAL_DATA_DIR, "master_venue.csv")
MASTER_TOUR = os.path.join(MANUAL_DATA_DIR, "master_tour.csv")

# --- 手動データを使うかどうか ---
# True : 手動データ（定価・当落日・地域等）をチケットデータに結合して学習
# False: チケットデータのみで学習（デフォルト）
USE_MANUAL_DATA = True

# 手動データとチケットデータの結合キー
# 手動データ側 → チケットデータ側 の対応
MANUAL_MERGE_KEYS = {
    "コンサート名": "event_id",   # イベントスラッグで結合
    "会場名": "venue",            # 会場名で補助結合（任意）
}

# AI開発フォルダのルート
AI_DEV_DIR = os.path.dirname(os.path.abspath(__file__))

# 出力ディレクトリ（学習済みモデル・結果等）
OUTPUT_DIR = os.path.join(AI_DEV_DIR, "train_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# 2. 学習対象グループ
# ============================================================
# 学習に使用するアーティストのスラッグ一覧
# "all" を指定すると、データが存在する全グループを自動検出
# 個別指定の場合はリストで記述（例: ["snow-man", "sixtones"]）

TARGET_GROUPS = "all"

# データが実質的に存在しない（ヘッダのみ）グループを除外
EXCLUDE_GROUPS = [
    "ambitious",
    "b-and-zai",
    "banzai",
    "boys-be",
    "sixtones",  # 6/28時点でデータなし
]

# ============================================================
# 3. モデル設定
# ============================================================
# "lightgbm"   : パターンA（安定志向・LightGBM）
# "hybrid"     : パターンB（最高精度・BERT + MLP + LightGBM）

MODEL_TYPE = "lightgbm"

# --- LightGBM ハイパーパラメータ ---
LGBM_PARAMS = {
    "objective": "regression",
    "metric": "rmse",
    "boosting_type": "gbdt",
    "num_leaves": 63,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "verbose": -1,
    "n_estimators": 1000,
    "early_stopping_rounds": 50,
}

# --- ハイブリッドモデル（パターンB）のパラメータ ---
HYBRID_PARAMS = {
    "bert_model_name": "cl-tohoku/bert-base-japanese",
    "embedding_dim": 32,       # カテゴリカル変数の埋め込み次元
    "mlp_hidden_dims": [128, 64],
    "dropout": 0.3,
    "learning_rate": 1e-4,
    "epochs": 30,
    "batch_size": 64,
    "device": "cuda",          # "cuda" or "cpu"
}

# ============================================================
# 4. 学習・評価設定
# ============================================================

# 目的変数
TARGET_COLUMN = "price"

# テスト分割比率（ホールドアウト検証）
TEST_SPLIT_RATIO = 0.2

# 交差検証の分割数
CV_FOLDS = 5

# 乱数シード（再現性確保）
RANDOM_SEED = 42

# ============================================================
# 5. 特徴量エンジニアリング設定
# ============================================================

# CSVの元カラム一覧（参照用）
RAW_COLUMNS = [
    "ticket_id", "created_at_unix", "event_id", "perf_date", "perf_time",
    "venue", "ticket_type", "name_type", "delivery_method",
    "seller_name", "seller_rating", "order_num", "ticket_tags",
    "first_observed_at", "last_observed_at", "sold_at", "status",
    "quantity", "price", "raw_description", "details_fetched",
]

# 特徴量として使用するカテゴリカルカラム
CATEGORICAL_FEATURES = [
    "event_id",
    "venue",
    "ticket_type",
    "name_type",
]

# raw_description からキーワード抽出するパターン
# キー: 生成されるフラグ列名、値: 正規表現パターン
DESCRIPTION_KEYWORDS = {
    "is_arena": r"アリーナ",
    "is_stand": r"スタンド|スタンダード",
    "is_doukkou": r"同行",
    "is_random": r"ランダム",
    "is_nuritsubushi": r"塗りつぶし|塗り潰し",
    "is_renban": r"連番",
    "is_fc": r"FC|ファンクラブ",
    "has_seat_info": r"\d+列|\d+番|\d+ゲート|ブロック",
    "is_good_seat": r"良席|神席|前方|最前|花道|センター|メンステ",
}

# ============================================================
# 6. 表示・デバッグ設定
# ============================================================

# デバッグモード（True: 詳細ログ出力）
DEBUG = False

# お買い得チケット抽出の表示件数
BARGAIN_TOP_N = 20


# ============================================================
# ヘルパー関数（他モジュールから config をインポートして使う）
# ============================================================

def get_data_files():
    """学習対象のCSVファイルパスのリストを返す"""
    import glob
    all_csvs = glob.glob(os.path.join(DATA_DIR, "*_master.csv"))
    
    if TARGET_GROUPS == "all":
        # 除外リストに含まれないものだけ返す
        result = []
        for f in all_csvs:
            slug = os.path.basename(f).replace("_master.csv", "")
            if slug not in EXCLUDE_GROUPS:
                result.append(f)
        return result
    else:
        return [
            os.path.join(DATA_DIR, f"{slug}_master.csv")
            for slug in TARGET_GROUPS
            if slug not in EXCLUDE_GROUPS
        ]


def print_config_summary():
    """現在の設定を見やすく表示する"""
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 60)
    print("  AI開発 設定サマリー")
    print("=" * 60)
    print(f"  学習データ日付   : {TRAIN_DATA_DATE}")
    print(f"  データディレクトリ: {DATA_DIR}")
    print(f"  手動データ       : {'ON ✔' if USE_MANUAL_DATA else 'OFF ✘'} ({MANUAL_DATA_FILE})")
    print(f"  対象グループ     : {TARGET_GROUPS}")
    print(f"  除外グループ     : {EXCLUDE_GROUPS}")
    print(f"  モデル種別       : {MODEL_TYPE}")
    print(f"  目的変数         : {TARGET_COLUMN}")
    print(f"  テスト分割       : {TEST_SPLIT_RATIO * 100:.0f}%")
    print(f"  交差検証         : {CV_FOLDS} fold")
    print(f"  乱数シード       : {RANDOM_SEED}")
    print(f"  デバッグモード   : {DEBUG}")
    print(f"  出力先           : {OUTPUT_DIR}")
    print("-" * 60)
    
    data_files = get_data_files()
    print(f"  検出されたCSVファイル ({len(data_files)} 件):")
    for f in data_files:
        print(f"    - {os.path.basename(f)}")
    print("=" * 60)


if __name__ == "__main__":
    print_config_summary()
