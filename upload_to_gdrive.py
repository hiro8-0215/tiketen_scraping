import os
import glob
import json
import sys
import base64
import urllib.request
from datetime import datetime, timezone, timedelta

# ユーザー指定の親フォルダID
PARENT_FOLDER_ID = '1Xi4LQGY45c09OmmbhV8MlxzKDbWE8UYe'

def main():
    print("Google Apps Script 経由でのバックアップ処理を開始します...")

    # URLを直接指定
    webapp_url = 'https://script.google.com/macros/s/AKfycbzQV0CeTbPRAv4zTA-SpLqQJdJ9WUPpmDeEAOBFJKoqj9m50rSCl-2LDEMZ0y9Appdc/exec'

    # 日本時間(JST)で今日の日付を取得
    JST = timezone(timedelta(hours=+9), 'JST')
    now = datetime.now(JST)
    subfolder_name = f"data_{now.month}_{now.day}"
    print(f"ターゲットフォルダ: {subfolder_name}")

    csv_files = glob.glob('data/*_master.csv')
    if not csv_files:
        print("アップロードするCSVファイルが見つかりません。")
        sys.exit(0)

    for file_path in csv_files:
        file_name = os.path.basename(file_path)
        print(f"送信中: {file_name} ...")
        
        # ファイルをBase64エンコード
        with open(file_path, 'rb') as f:
            file_data = base64.b64encode(f.read()).decode('utf-8')
            
        payload = {
            "parentFolderId": PARENT_FOLDER_ID,
            "subfolderName": subfolder_name,
            "filename": file_name,
            "filedata": file_data
        }
        
        req = urllib.request.Request(
            webapp_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body)
                if res_json.get("status") == "success":
                    print(f"  -> 完了 (File ID: {res_json.get('fileId')})")
                else:
                    print(f"  -> サーバーエラー: {res_json.get('message')}")
                    sys.exit(1)
        except Exception as e:
            print(f"  -> 通信エラー: {file_name} の送信に失敗しました: {e}")
            sys.exit(1)

    print("すべてのアーカイブ処理が正常に完了しました！")

if __name__ == "__main__":
    main()
