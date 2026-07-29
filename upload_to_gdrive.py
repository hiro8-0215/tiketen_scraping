import os
import glob
import json
import sys
import time
import base64
import urllib.request
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone, timedelta

# ユーザー指定の親フォルダID
PARENT_FOLDER_ID = '1Xi4LQGY45c09OmmbhV8MlxzKDbWE8UYe'

def upload_file_with_retry(webapp_url, payload, file_name, max_attempts=5):
    req_data = json.dumps(payload).encode('utf-8')
    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(
            webapp_url,
            data=req_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                res_body = response.read().decode('utf-8', errors='replace')
                res_json = json.loads(res_body)
                if res_json.get("status") == "success":
                    print(f"  -> 完了 (File ID: {res_json.get('fileId')})")
                    return True
                else:
                    error_msg = res_json.get("message", "Unknown error")
                    print(f"  -> [WARN] サーバーエラー応答 (試行 {attempt}/{max_attempts}): {error_msg}")
                    if attempt < max_attempts:
                        backoff = 2 ** attempt
                        print(f"     {backoff}秒後に再試行します...")
                        time.sleep(backoff)
                        continue
                    else:
                        print(f"  -> [ERROR] 最大試行回数に達しました。送信失敗: {file_name} - {error_msg}")
                        return False
        except HTTPError as e:
            status = e.code
            try:
                body = e.read().decode('utf-8', errors='replace')
            except Exception:
                body = str(e)
            print(f"  -> [WARN] HTTPエラー {status} (試行 {attempt}/{max_attempts}): {file_name}")
            print(f"     詳細レスポンス: {body}")
            if status in (404, 429, 500, 502, 503, 504) and attempt < max_attempts:
                backoff = 2 ** attempt
                print(f"     一時的なHTTP {status} のため {backoff}秒後に再試行します...")
                time.sleep(backoff)
                continue
            else:
                print(f"  -> [ERROR] 送信失敗 (HTTP {status}): {file_name}")
                return False
        except (URLError, Exception) as e:
            print(f"  -> [WARN] 通信エラー (試行 {attempt}/{max_attempts}): {e}")
            if attempt < max_attempts:
                backoff = 2 ** attempt
                print(f"     {backoff}秒後に再試行します...")
                time.sleep(backoff)
                continue
            else:
                print(f"  -> [ERROR] 最大試行回数に達しました。送信失敗: {file_name} - {e}")
                return False
    return False

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
        
        success = upload_file_with_retry(webapp_url, payload, file_name)
        if not success:
            print(f"[ERROR] {file_name} のバックアップに失敗しました。処理を中止します。")
            sys.exit(1)

    print("すべてのアーカイブ処理が正常に完了しました！")

if __name__ == "__main__":
    main()
