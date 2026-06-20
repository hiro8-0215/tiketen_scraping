import os
import re
import json
import csv
import urllib.request
import time
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
SNAPSHOT_DIR = os.path.join(DATA_DIR, 'snapshot')
MARKET_DIR = os.path.join(DATA_DIR, 'market_snapshot')

def fetch_html(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        return urllib.request.urlopen(req).read().decode('utf-8')
    except:
        return ""

def get_events(performer):
    html = fetch_html(f'https://ticketen.jp/performers/{performer}')
    soup = BeautifulSoup(html, 'html.parser')
    events = []
    for a in soup.find_all('a', href=True):
        m = re.match(r'^/events/([^/]+)$', a['href'])
        if m and m.group(1) not in events:
            events.append(m.group(1))
    return events

def get_event_id_from_slug(slug):
    html = fetch_html(f'https://ticketen.jp/events/{slug}')
    html = html.replace('\\"', '"')
    
    match = re.search(rf'"id":"([a-zA-Z0-9]{{20}})","name":"[^"]+","slug":"{slug}"', html)
    if match: return match.group(1)
    
    match = re.search(rf'"slug":"{slug}","id":"([a-zA-Z0-9]{{20}})"', html)
    if match: return match.group(1)
    
    match = re.search(rf'"id":"([a-zA-Z0-9]{{20}})","slug":"{slug}"', html)
    if match: return match.group(1)
    
    return None

def fetch_all_tickets(event_id):
    tickets = []
    offset = 0
    limit = 1000
    while True:
        url = f"https://ticketen.jp/api/tickets/all?context=event&eventId={event_id}&activeOnly=0&limit={limit}&offset={offset}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req).read().decode('utf-8')
            data = json.loads(res)
            batch = data.get('tickets', [])
            tickets.extend(batch)
            has_more = data.get('hasMore')
            time.sleep(1)  # サーバー負荷軽減: 最終ページ含め全リクエスト後に1秒待機
            if not has_more:
                break
            offset = data.get('nextOffset')
        except Exception as e:
            print(f"API Error for {event_id} offset {offset}: {e}")
            break
    return tickets

def parse_ticket_details(page, share_code):
    url = f"https://ticketen.jp/ticket/{share_code}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=5000)
        page.wait_for_selector('text=チケット概要', timeout=5000)
    except Exception as e:
        print(f"Failed to load details for {share_code}: {e}")
        return None
        
    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    
    data = {
        'seller_name': '',
        'seller_rating': '',
        'order_num': '',
        'ticket_tags': '',
        'raw_description': ''
    }
    
    text_blocks = [elem.get_text(strip=True) for elem in soup.find_all(['p', 'div', 'span', 'h1', 'h2', 'h3'])]
    
    def find_next_text(label):
        for i, text in enumerate(text_blocks):
            if label in text and text == label:
                if i + 1 < len(text_blocks):
                    return text_blocks[i+1]
            elif text.startswith(label):
                return text.replace(label, '').strip()
        return ''
            
    # ---- 関連タグ（同行・QRなどの抽出）----
    tags_str = find_next_text('関連タグ')
    if tags_str:
        data['ticket_tags'] = tags_str

    # ---- 詳細・備考: ページ全体テキストから正確に切り出す ----
    # 旧方式(text_blocks)は出品者情報が混入するバグがあったため、全文splitで境界検出する方式に変更
    full_text = soup.get_text(separator='\n')
    all_lines = [l.strip() for l in full_text.split('\n') if l.strip()]
    
    desc_start_idx = None
    desc_end_idx = None
    for i, line in enumerate(all_lines):
        if '詳細・備考' in line and desc_start_idx is None:
            desc_start_idx = i + 1
        if desc_start_idx is not None and line == '出品者':
            desc_end_idx = i
            break
    
    if desc_start_idx is not None:
        end = desc_end_idx if desc_end_idx else min(desc_start_idx + 60, len(all_lines))
        raw_lines = all_lines[desc_start_idx:end]
        # 連続重複行を除去
        unique_desc = []
        for line in raw_lines:
            if not unique_desc or unique_desc[-1] != line:
                unique_desc.append(line)
        data['raw_description'] = "\n".join(unique_desc).strip()
    
    # 同行・同行が先にないかticket_tagsに記録
    if not data['ticket_tags'] and data['raw_description']:
        if '同行' in data['raw_description']:
            data['ticket_tags'] = '同行記載あり'
        elif 'ランダム' in data['raw_description']:
            data['ticket_tags'] = 'ランダム記載あり'
    
    # ---- 出品者情報: 全文splitから正確に切り出す ----
    # 「出品者」〜「購入リクエスト」間を抽出して名前・評価を分離
    # ---- 出品者情報: 全文splitから正確に切り出す ----
    # 構造: 出品者 → 名前 → 評価（X.X（N件）） → 登録情報 → 購入リクエスト
    import re as _re
    seller_start_idx = None
    seller_end_idx = None
    for i, line in enumerate(all_lines):
        if line == '出品者' and seller_start_idx is None:
            seller_start_idx = i + 1
        if seller_start_idx is not None and ('購入リクエスト' in line or 'ログインして' in line):
            seller_end_idx = i
            break
    
    if seller_start_idx is not None:
        end = seller_end_idx if seller_end_idx else min(seller_start_idx + 6, len(all_lines))
        seller_block = all_lines[seller_start_idx:end]
        # 重複除去
        unique_seller = []
        for line in seller_block:
            if not unique_seller or unique_seller[-1] != line:
                unique_seller.append(line)
        
        if unique_seller:
            # 先頭行が名前（評価を含まない行）
            first_line = unique_seller[0]
            rating_in_first = _re.search(r'(\d+\.\d+)', first_line)
            if rating_in_first:
                # 名前と評価が同一行の場合: 評価の前を名前とする
                name_part = first_line[:rating_in_first.start()].strip()
                data['seller_name'] = name_part if name_part else first_line
                data['seller_rating'] = rating_in_first.group(1)
            else:
                data['seller_name'] = first_line
                # 2行目以降から評価（X.X形式）を探す
                for line in unique_seller[1:]:
                    if '誠意' in line or '登録' in line or '時間' in line:
                        break
                    m = _re.search(r'(\d+\.\d+)', line)
                    if m:
                        data['seller_rating'] = m.group(1)
                        break
            
    return data



def load_master(performer):
    master_file = os.path.join(DATA_DIR, f'{performer}_master.csv')
    if not os.path.exists(master_file):
        return {}
    
    master = {}
    with open(master_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            master[row['ticket_id']] = row
    return master

def save_master(performer, master):
    os.makedirs(DATA_DIR, exist_ok=True)
    master_file = os.path.join(DATA_DIR, f'{performer}_master.csv')
    fieldnames = ['ticket_id', 'created_at_unix', 'event_id', 'perf_date', 'perf_time', 'venue', 
                  'ticket_type', 'name_type', 'delivery_method', 'seller_name', 
                  'seller_rating', 'order_num', 'ticket_tags', 'first_observed_at', 'last_observed_at', 
                  'sold_at', 'status', 'quantity', 'price', 'raw_description', 'details_fetched']
                  
    with open(master_file, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for t_id, row in master.items():
            row_out = {k: row.get(k, '') for k in fieldnames}
            writer.writerow(row_out)

def save_snapshots(performer, master):
    import pandas as pd
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    os.makedirs(MARKET_DIR, exist_ok=True)
    
    df = pd.DataFrame(list(master.values()))
    if df.empty: return
        
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df['first_observed_at'] = pd.to_datetime(df['first_observed_at'], errors='coerce')
    # Filter out nat
    df = df.dropna(subset=['first_observed_at']).copy()
    df['year_month'] = df['first_observed_at'].dt.strftime('%Y-%m')
    
    for ym, group in df.groupby('year_month'):
        group.to_csv(os.path.join(SNAPSHOT_DIR, f'{performer}_{ym}.csv'), index=False, encoding='utf-8-sig')
        
    market_records = []
    for ym, group in df.groupby('year_month'):
        for (ev_id, p_date, p_time), sub in group.groupby(['event_id', 'perf_date', 'perf_time']):
            valid_prices = sub['price'].dropna()
            market_records.append({
                'year_month': ym,
                'event_id': ev_id,
                'perf_date': p_date,
                'perf_time': p_time,
                'venue': sub['venue'].iloc[0] if not sub.empty else '',
                'total_tickets': len(sub),
                'active_tickets': len(sub[sub['status'] == 'listing']),
                'sold_tickets': len(sub[sub['status'] == 'sold']),
                'deleted_tickets': len(sub[sub['status'] == 'deleted']),
                'avg_price': valid_prices.mean() if not valid_prices.empty else 0,
                'min_price': valid_prices.min() if not valid_prices.empty else 0,
                'max_price': valid_prices.max() if not valid_prices.empty else 0,
            })
            
    if market_records:
        mdf = pd.DataFrame(market_records)
        for ym, group in mdf.groupby('year_month'):
            group.to_csv(os.path.join(MARKET_DIR, f'{performer}_{ym}.csv'), index=False, encoding='utf-8-sig')

def main():
    targets_file = os.path.join(DATA_DIR, 'targets.json')
    if not os.path.exists(targets_file):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(targets_file, 'w') as f:
            json.dump(["snow-man"], f)
            
    with open(targets_file, 'r') as f:
        performers = json.load(f)

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for performer in performers:
        print(f"=== Processing {performer} ===")
        master = load_master(performer)
        
        by_share_code = {t['ticket_id']: t for t in master.values() if not t['ticket_id'].startswith('sold_')}
        by_created_at = {f"{t['created_at_unix']}_{t.get('price', '')}": t for t in master.values() if t.get('created_at_unix')}
        
        current_active_codes = set()
        new_active_tickets = []

        print(f"Fetching events for {performer}...")
        events = get_events(performer)
        for slug in events:
            ev_firestore_id = get_event_id_from_slug(slug)
            if not ev_firestore_id: 
                print(f"Could not find firestore ID for {slug}")
                continue
            
            print(f"Fetching API tickets for {slug}...")
            tickets = fetch_all_tickets(ev_firestore_id)
            for t in tickets:
                status = t.get('status')
                created_at_unix = str(t.get('createdAt', ''))
                price_val = str(t.get('pricePerTicket', ''))
                match_key = f"{created_at_unix}_{price_val}"
                
                if status == 'active':
                    share_code = t.get('shareCode')
                    if not share_code: continue
                    current_active_codes.add(share_code)
                    
                    if share_code in by_share_code:
                        row = by_share_code[share_code]
                        row['created_at_unix'] = created_at_unix
                        row['last_observed_at'] = now_str
                        if str(row.get('details_fetched', 'False')) != 'True':
                            new_active_tickets.append(share_code)
                        by_created_at[match_key] = row
                    else:
                        row = {
                            'ticket_id': share_code,
                            'created_at_unix': created_at_unix,
                            'event_id': slug,
                            'perf_date': t.get('eventDate', ''),
                            'perf_time': t.get('eventStartTime', ''),
                            'venue': t.get('venue', ''),
                            'status': 'listing',
                            'price': t.get('pricePerTicket', 0),
                            'quantity': t.get('quantity', 0),
                            'delivery_method': t.get('deliveryMethod', ''),
                            'ticket_type': t.get('ticketType', ''),
                            'name_type': t.get('nameGender', ''),
                            'raw_description': t.get('description', ''),
                            'first_observed_at': now_str,
                            'last_observed_at': now_str,
                            'details_fetched': 'False',
                        }
                        try:
                            row['first_observed_at'] = datetime.fromtimestamp(int(created_at_unix)/1000.0).strftime('%Y-%m-%d %H:%M:%S')
                        except: pass
                            
                        by_share_code[share_code] = row
                        by_created_at[match_key] = row
                        master[share_code] = row
                        new_active_tickets.append(share_code)
                        
                elif status == 'sold':
                    if match_key in by_created_at:
                        row = by_created_at[match_key]
                        if row['status'] == 'listing':
                            row['status'] = 'sold'
                            row['sold_at'] = now_str
                        row['last_observed_at'] = now_str
                    else:
                        t_id = f"sold_{created_at_unix}"
                        row = {
                            'ticket_id': t_id,
                            'created_at_unix': created_at_unix,
                            'event_id': slug,
                            'perf_date': t.get('eventDate', ''),
                            'perf_time': t.get('eventStartTime', ''),
                            'venue': t.get('venue', ''),
                            'status': 'sold',
                            'price': t.get('pricePerTicket', 0),
                            'quantity': t.get('quantity', 0),
                            'delivery_method': t.get('deliveryMethod', ''),
                            'ticket_type': t.get('ticketType', ''),
                            'name_type': t.get('nameGender', ''),
                            'raw_description': t.get('description', ''),
                            'first_observed_at': now_str,
                            'last_observed_at': now_str,
                            'sold_at': now_str,
                            'details_fetched': 'False',
                        }
                        try:
                            row['first_observed_at'] = datetime.fromtimestamp(int(created_at_unix)/1000.0).strftime('%Y-%m-%d %H:%M:%S')
                        except: pass
                        by_created_at[match_key] = row
                        master[t_id] = row

        if new_active_tickets:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                for i, share_code in enumerate(new_active_tickets):
                    print(f"Fetching details for NEW active ticket {share_code}...")
                    details = parse_ticket_details(page, share_code)
                    time.sleep(1)  # サーバー負荷軽減: 全ページアクセス後に1秒待機
                    if not details: continue
                    
                    row = master[share_code]
                    if details.get('raw_description'):
                        row['raw_description'] = details['raw_description']
                    row['seller_name'] = details.get('seller_name', '')
                    row['seller_rating'] = details.get('seller_rating', '')
                    row['order_num'] = details.get('order_num', '')
                    row['ticket_tags'] = details.get('ticket_tags', '')
                    row['details_fetched'] = 'True'
                    
                    # インクリメンタル保存: 50件ごと + 最後の1件はかならず保存
                    if (i + 1) % 50 == 0 or (i + 1) == len(new_active_tickets):
                        print(f"[CHECKPOINT] Saving after {i+1} detail fetches...")
                        save_master(performer, master)
                    
                browser.close()

        for t_id, row in master.items():
            if row['status'] == 'listing' and t_id not in current_active_codes:
                row['status'] = 'deleted'
                row['last_observed_at'] = now_str

        save_master(performer, master)
        save_snapshots(performer, master)
        print(f"Saved {len(master)} tickets to master for {performer}.")

if __name__ == '__main__':
    main()
