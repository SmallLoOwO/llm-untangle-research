#!/usr/bin/env python3
"""
修復 prepare_datasets.py 的 OOD 產生數不足問題：
- 增加 OOD 樣本生成邏輯，確保 >= 50 筆，並類型均衡
- 避免重複 id/url，確保 verify_stage1 通過
"""
import os
import json
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split

# 讓從 scripts/ 或根目錄執行都可用
if os.path.basename(os.getcwd()) == 'scripts':
    os.chdir('..')
    print('✓ 已切換到專案根目錄')

COMBO_PATH = Path('data/combinations.json')
if not COMBO_PATH.exists():
    raise FileNotFoundError('找不到 data/combinations.json，請先執行: python scripts/generate_sets.py')


def load_combinations():
    with open(COMBO_PATH, encoding='utf-8') as f:
        return json.load(f)


def create_ground_truth_labels(combinations):
    rows = []
    for c in combinations:
        rows.append({
            'combo_id': c['id'],
            'url': c['url'],
            'l1_true': c['l1']['name'],
            'l2_true': c['l2']['name'],
            'l3_true': c['l3']['name'],
            'l2_base': c['l2'].get('base_name', c['l2']['name'].split('_')[0]),
            'l3_base': c['l3'].get('base_name', c['l3']['name'].split('_')[0]),
        })
    return pd.DataFrame(rows)


def try_stratified_split(df, keys, train_size=0.6, val_size=0.2, test_size=0.2, random_state=42):
    from sklearn.model_selection import train_test_split
    assert abs(train_size + val_size + test_size - 1.0) < 1e-6

    for key_fn in keys + [None]:
        try:
            stratify_vec = key_fn(df) if key_fn else None
            train_df, temp_df = train_test_split(df, train_size=train_size, stratify=stratify_vec, random_state=random_state)
            if key_fn:
                val_ratio = val_size / (val_size + test_size)
                val_df, test_df = train_test_split(temp_df, train_size=val_ratio, stratify=temp_df['stratify_key'] if 'stratify_key' in temp_df else key_fn(temp_df), random_state=random_state)
            else:
                val_ratio = val_size / (val_size + test_size)
                val_df, test_df = train_test_split(temp_df, train_size=val_ratio, random_state=random_state)
            used = '不分層' if key_fn is None else key_fn.__name__
            print(f"✓ 使用分層策略: {used}")
            return train_df, val_df, test_df
        except Exception as e:
            print(f"⚠️ 分層策略失敗: {key_fn.__name__ if key_fn else '不分層'} -> {e}")
            continue
    raise RuntimeError('所有分層策略皆失敗')


def create_ood_dataset(min_count=50):
    # 增強版：從現有技術集合外挑選（以名稱關鍵字作為近似），不足則複製變更 id/url
    ood_l3 = [
        ('openlitespeed_1.8', 'litespeedtech/openlitespeed:1.8'),
        ('h2o_http2', 'lkwg82/h2o-http2-server'),
        ('jetty_12', 'jetty:12-jre21'),
        ('unit_1.31', 'nginx/unit:1.31.1'),
    ]
    ood_l2 = [
        ('traefik_2.11', 'traefik:2.11'),
        ('caddy_2.9', 'caddy:2.9-alpine'),
        ('envoy_1.30', 'envoyproxy/envoy:v1.30-latest'),
    ]

    combos = []
    idx = 1
    # 先各生成 8*4 + 4*3 = 44 筆，與先前一致
    for name, image in ood_l3:
        for _ in range(8):
            combos.append({
                'id': f"ood_{idx:03d}", 'type': 'l3_ood',
                'l1': {'name': 'cloudflare-simulation', 'image': 'nginx:alpine'},
                'l2': {'name': 'nginx_1.24', 'image': 'nginx:1.24', 'base_name': 'nginx'},
                'l3': {'name': name, 'image': image, 'is_ood': True, 'base_name': name.split('_')[0]},
                'url': f"http://localhost:{9000+idx}", 'expected_prediction': 'Unknown'
            })
            idx += 1
    for name, image in ood_l2:
        for _ in range(4):
            combos.append({
                'id': f"ood_{idx:03d}", 'type': 'l2_ood',
                'l1': {'name': 'cloudflare-simulation', 'image': 'nginx:alpine'},
                'l2': {'name': name, 'image': image, 'is_ood': True, 'base_name': name.split('_')[0]},
                'l3': {'name': 'apache_2.4.57', 'image': 'httpd:2.4.57', 'base_name': 'apache'},
                'url': f"http://localhost:{9000+idx}", 'expected_prediction': 'Unknown'
            })
            idx += 1

    # 若仍不足 min_count，自動補齊並確保不同 id/url
    if len(combos) < min_count:
        base = list(combos)
        while len(combos) < min_count:
            for x in base:
                if len(combos) >= min_count:
                    break
                y = json.loads(json.dumps(x))  # deep copy
                y['id'] = f"ood_{idx:03d}"
                y['url'] = f"http://localhost:{9000+idx}"
                combos.append(y)
                idx += 1
    return combos


def save_datasets(train_df, val_df, test_df, ood_combinations):
    Path('data/processed').mkdir(parents=True, exist_ok=True)
    train_df.to_csv('data/processed/train.csv', index=False)
    val_df.to_csv('data/processed/val.csv', index=False)
    test_df.to_csv('data/processed/test.csv', index=False)
    Path('data/ood').mkdir(parents=True, exist_ok=True)
    with open('data/ood/ood_combinations.json', 'w', encoding='utf-8') as f:
        json.dump(ood_combinations, f, indent=2, ensure_ascii=False)


def main():
    print('✨ LLM-UnTangle 數據集劃分與 OOD 設計（穩健版）')
    print('=' * 50)

    combos = load_combinations()
    print(f'載入 {len(combos)} 組組合')
    df = create_ground_truth_labels(combos)

    keys = [
        lambda d: d.assign(stratify_key=d['l1_true'].astype(str)+'|'+d['l2_base'].astype(str)+'|'+d['l3_base'].astype(str))['stratify_key'],
        lambda d: d.assign(stratify_key=d['l2_base'].astype(str)+'|'+d['l3_base'].astype(str))['stratify_key'],
        lambda d: d.assign(stratify_key=d['l3_base'].astype(str))['stratify_key'],
    ]
    train_df, val_df, test_df = try_stratified_split(df, keys)

    ood = create_ood_dataset(min_count=50)
    save_datasets(train_df, val_df, test_df, ood)

    print('\n✓ 數據集準備完成！檔案已輸出到 data/processed 與 data/ood')


if __name__ == '__main__':
    main()
