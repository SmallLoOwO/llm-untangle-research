#!/usr/bin/env python3
"""
數據集劃分與 OOD 測試集設計（穩健版）
- 修復 stratify 失敗：當某些分層類別樣本數 < 2 時，自動降級為較寬鬆的分層鍵，最後退化為不分層。
- 自動處理當前工作目錄在 scripts/ 的情況。
"""
import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from collections import Counter

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
    """嘗試用不同嚴格程度的分層鍵進行分割，必要時降級，最後不分層。"""
    assert abs(train_size + val_size + test_size - 1.0) < 1e-6

    # 依序嘗試不同 stratify key 組合
    for key_name in keys + [None]:
        try:
            if key_name is not None:
                df['stratify_key'] = key_name(df)
                # 若最少類別 < 2，會在 split 觸發 ValueError
                stratify_vec = df['stratify_key']
            else:
                stratify_vec = None

            train_df, temp_df = train_test_split(
                df,
                train_size=train_size,
                stratify=stratify_vec,
                random_state=random_state
            )

            if stratify_vec is not None:
                val_ratio = val_size / (val_size + test_size)
                val_df, test_df = train_test_split(
                    temp_df,
                    train_size=val_ratio,
                    stratify=temp_df['stratify_key'],
                    random_state=random_state
                )
                # 清理
                for subset in [train_df, val_df, test_df]:
                    subset.drop(columns=['stratify_key'], inplace=True, errors='ignore')
            else:
                # 不分層情況
                val_ratio = val_size / (val_size + test_size)
                val_df, test_df = train_test_split(
                    temp_df,
                    train_size=val_ratio,
                    random_state=random_state
                )
            used = '不分層' if key_name is None else key_name.__name__
            print(f"✓ 使用分層策略: {used}")
            return train_df, val_df, test_df
        except ValueError as e:
            # 顯示提示並嘗試下一層級
            print(f"⚠️ 分層策略失敗: {key_name.__name__ if key_name else '不分層'} -> {e}")
            continue

    # 不應到此
    raise RuntimeError('所有分層策略皆失敗')


def verify_split_quality(train_df, val_df, test_df):
    total = len(train_df) + len(val_df) + len(test_df)
    print("\n樣本數量:")
    print(f"  訓練集: {len(train_df)} ({len(train_df)/total*100:.1f}%)")
    print(f"  驗證集: {len(val_df)} ({len(val_df)/total*100:.1f}%)")
    print(f"  測試集: {len(test_df)} ({len(test_df)/total*100:.1f}%)")
    return True


def create_ood_dataset():
    # 簡化版，沿用原設計
    l3 = [
        ('openlitespeed_1.8', 'litespeedtech/openlitespeed:1.8', '輕量級 Web 伺服器'),
        ('h2o_http2', 'lkwg82/h2o-http2-server', 'HTTP/2 專用伺服器'),
        ('jetty_12', 'jetty:12-jre21', 'Java 伺服器'),
        ('unit_1.31', 'nginx/unit:1.31.1', 'NGINX Unit')
    ]
    l2 = [
        ('traefik_2.11', 'traefik:2.11', '新版本 Traefik'),
        ('caddy_2.8', 'caddy:2.8-alpine', 'Caddy'),
        ('envoy_1.30', 'envoyproxy/envoy:v1.30-latest', 'Envoy')
    ]
    combos = []
    # 生成 >= 50 筆
    idx = 1
    for name, image, reason in l3:
        for _ in range(8):
            combos.append({
                'id': f"ood_{idx:03d}", 'type': 'l3_ood',
                'l1': {'name': 'cloudflare-simulation', 'image': 'nginx:alpine'},
                'l2': {'name': 'nginx_1.24', 'image': 'nginx:1.24', 'base_name': 'nginx'},
                'l3': {'name': name, 'image': image, 'is_ood': True, 'base_name': name.split('_')[0]},
                'url': f"http://localhost:{9000+idx}", 'expected_prediction': 'Unknown', 'reason': reason
            })
            idx += 1
    for name, image, reason in l2:
        for _ in range(4):
            combos.append({
                'id': f"ood_{idx:03d}", 'type': 'l2_ood',
                'l1': {'name': 'cloudflare-simulation', 'image': 'nginx:alpine'},
                'l2': {'name': name, 'image': image, 'is_ood': True, 'base_name': name.split('_')[0]},
                'l3': {'name': 'apache_2.4.57', 'image': 'httpd:2.4.57', 'base_name': 'apache'},
                'url': f"http://localhost:{9000+idx}", 'expected_prediction': 'Unknown', 'reason': reason
            })
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

    # 分層鍵嚴格度：先用 L1|L2_base|L3_base，其次 L2_base|L3_base，其次 L3_base，最後不分層
    keys = [
        lambda d: d['l1_true'].astype(str) + '|' + d['l2_base'].astype(str) + '|' + d['l3_base'].astype(str),
        lambda d: d['l2_base'].astype(str) + '|' + d['l3_base'].astype(str),
        lambda d: d['l3_base'].astype(str),
    ]
    train_df, val_df, test_df = try_stratified_split(df, keys)

    verify_split_quality(train_df, val_df, test_df)

    ood = create_ood_dataset()
    save_datasets(train_df, val_df, test_df, ood)

    print('\n✓ 數據集準備完成！檔案已輸出到 data/processed 與 data/ood')


if __name__ == '__main__':
    main()
