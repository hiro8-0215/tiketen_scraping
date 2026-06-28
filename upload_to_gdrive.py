import os
import glob
import json
import sys
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Google Drive APIの権限スコープ
SCOPES = ['https://www.googleapis.com/auth/drive']

# ユーザー指定の親フォルダID
PARENT_FOLDER_ID = '1Xi4LQGY45c09OmmbhV8MlxzKDbWE8UYe'

def main():
    print("Google Drive アーカイブ処理を開始します...")

    # GitHub Secretsから鍵情報を取得
    creds_json_str = os.environ.get('GDRIVE_CREDENTIALS_JSON')
    if not creds_json_str:
        print("エラー: 環境変数 GDRIVE_CREDENTIALS_JSON が設定されていません。GitHub Secretsの設定を確認してください。")
        sys.exit(1)

    try:
        creds_info = json.loads(creds_json_str)
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"認証エラー: 鍵の読み込みに失敗しました。詳細: {e}")
        sys.exit(1)

    # 1. 今日の日付でフォルダ「data_月_日」を作成
    JST = timezone(timedelta(hours=+9), 'JST')
    now = datetime.now(JST)
    folder_name = f"data_{now.month}_{now.day}"

    try:
        folder_metadata = {
            'name': folder_name,
            'parents': [PARENT_FOLDER_ID],
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=folder_metadata, fields='id').execute()
        subfolder_id = folder.get('id')
        print(f"作成成功: ドライブ上にフォルダ '{folder_name}' を作成しました。")
    except Exception as e:
        print(f"フォルダ作成エラー: {e}")
        sys.exit(1)

    # 2. dataフォルダ内のすべてのCSVをアップロード
    csv_files = glob.glob('data/*_master.csv')
    if not csv_files:
        print("アップロードするCSVファイルが見つかりません。")
        sys.exit(0)

    for file_path in csv_files:
        file_name = os.path.basename(file_path)
        print(f"アップロード中: {file_name} ...")
        file_metadata = {
            'name': file_name,
            'parents': [subfolder_id]
        }
        media = MediaFileUpload(file_path, mimetype='text/csv')
        try:
            file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f"  -> 完了")
        except Exception as e:
            print(f"  -> エラー発生: {file_name} のアップロードに失敗しました: {e}")
            raise e

    print("すべてのアーカイブ処理が正常に完了しました！")

if __name__ == "__main__":
    main()
