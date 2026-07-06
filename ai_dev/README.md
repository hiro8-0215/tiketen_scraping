# AI開発フォルダ (ai_dev/)

このフォルダは、チケット価格予測AIの開発・試運転用ディレクトリです。

## フォルダ構成
```
ai_dev/
├── config.py            # 設定ファイル（データパス・モデル・パラメータの一元管理）
├── data_loader.py       # データ読み込み・クレンジング・特徴量エンジニアリング
├── train_lightgbm.py    # パターンA: LightGBM 学習・評価スクリプト
├── output/              # 学習済みモデル・評価結果の出力先（自動生成）
└── README.md            # 本ファイル
```

## 使い方

### 1. 設定の確認
```bash
python ai_dev/config.py
```
現在の設定（学習データ日付、対象グループ、モデル種別等）を一覧表示します。

### 2. パターンA（LightGBM）の試運転
```bash
python ai_dev/train_lightgbm.py
```

## 設定の変更
`config.py` を直接編集してください。主な設定項目：

| 設定項目 | 変数名 | 説明 |
|---|---|---|
| 学習データの日付 | `TRAIN_DATA_DATE` | `"data_6_28"` 等。`"latest"` で最新データ |
| 対象グループ | `TARGET_GROUPS` | `"all"` または `["snow-man"]` 等 |
| モデル種別 | `MODEL_TYPE` | `"lightgbm"` or `"hybrid"` |
| テスト分割率 | `TEST_SPLIT_RATIO` | デフォルト 0.2 (20%) |
| LightGBMパラメータ | `LGBM_PARAMS` | num_leaves, learning_rate 等 |
