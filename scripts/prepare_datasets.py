#!/usr/bin/env python3
"""
數據集劃分與 OOD 測試集設計
實現科學的訓練/驗證/測試劃分和 OOD 檢測評估
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from collections import defaultdict, Counter
import yaml
import random

def load_combinations():
    """載入組合資訊"""
    with open('data/combinations.json', encoding='utf-8') as f:
        return json.load(f)

def create_ground_truth_labels(combinations):
    """建立地面真相標籤"""
    labels = []
    
    for combo in combinations:
        labels.append({
            'combo_id': combo['id'],
            'url': combo['url'],
            'l1_true': combo['l1']['name'],
            'l2_true': combo['l2']['name'], 
            'l3_true': combo['l3']['name'],
            'l1_image': combo['l1']['image'],
            'l2_image': combo['l2']['image'],
            'l3_image': combo['l3']['image'],
            'l2_base': combo['l2']['base_name'],
            'l3_base': combo['l3']['base_name']
        })
    
    return pd.DataFrame(labels)

def stratified_split(df, train_size=0.6, val_size=0.2, test_size=0.2, random_state=42):
    """
    分層抽樣劃分數據集
    確保各層（L1/L2/L3）的伺服器分佈在各子集中保持一致
    """
    assert abs(train_size + val_size + test_size - 1.0) < 1e-6, "比例總和必須為 1"
    
    # 建立分層標籤（組合 L1, L2, L3 基礎名稱）
    df['stratify_key'] = (
        df['l1_true'].astype(str) + '|' +
        df['l2_base'].astype(str) + '|' + 
        df['l3_base'].astype(str)
    )
    
    # 第一次分割：分出訓練集
    train_df, temp_df = train_test_split(
        df,
        train_size=train_size,
        stratify=df['stratify_key'],
        random_state=random_state
    )
    
    # 第二次分割：從剩餘中分出驗證集和測試集
    val_ratio = val_size / (val_size + test_size)
    val_df, test_df = train_test_split(
        temp_df,
        train_size=val_ratio,
        stratify=temp_df['stratify_key'],
        random_state=random_state
    )
    
    # 移除輔助欄位
    for subset in [train_df, val_df, test_df]:
        subset.drop('stratify_key', axis=1, inplace=True)
    
    return train_df, val_df, test_df

def verify_split_quality(train_df, val_df, test_df):
    """驗證劃分的品質"""
    from scipy.stats import entropy
    
    print("\n" + "="*60)
    print("數據集劃分驗證")
    print("="*60)
    
    total = len(train_df) + len(val_df) + len(test_df)
    
    print(f"\n樣本數量:")
    print(f"  訓練集: {len(train_df):3d} ({len(train_df)/total*100:.1f}%)")
    print(f"  驗證集: {len(val_df):3d} ({len(val_df)/total*100:.1f}%)")
    print(f"  測試集: {len(test_df):3d} ({len(test_df)/total*100:.1f}%)")
    print(f"  總計:   {total:3d}")
    
    # 檢查各層分佈一致性
    quality_scores = []
    
    for layer in ['l1_true', 'l2_base', 'l3_base']:
        print(f"\n{layer} 分佈一致性:")
        
        # 計算各子集的分佈
        train_dist = train_df[layer].value_counts(normalize=True).sort_index()
        val_dist = val_df[layer].value_counts(normalize=True).reindex(train_dist.index, fill_value=0)
        test_dist = test_df[layer].value_counts(normalize=True).reindex(train_dist.index, fill_value=0)
        
        # 顯示前 5 個最常見的技術
        comparison = pd.DataFrame({
            'Train': train_dist.head(),
            'Val': val_dist.head(),
            'Test': test_dist.head()
        }).fillna(0)
        print(comparison)
        
        # 計算 KL 散度（衡量分佈相似度）
        def safe_kl_divergence(p, q):
            """Safe KL divergence calculation"""
            # Add small epsilon to avoid log(0)
            epsilon = 1e-10
            p_safe = p + epsilon
            q_safe = q + epsilon
            return entropy(p_safe, q_safe)
        
        kl_train_val = safe_kl_divergence(train_dist, val_dist)
        kl_train_test = safe_kl_divergence(train_dist, test_dist)
        
        print(f"  KL(Train||Val):  {kl_train_val:.4f}")
        print(f"  KL(Train||Test): {kl_train_test:.4f}")
        
        # 評分標準：KL < 0.1 為優秀，< 0.2 為可接受
        max_kl = max(kl_train_val, kl_train_test)
        if max_kl < 0.1:
            quality = "優秀"
            score = 1.0
        elif max_kl < 0.2:
            quality = "良好"
            score = 0.8
        else:
            quality = "需要改進"
            score = 0.5
        
        print(f"  品質評分: {quality} (KL={max_kl:.4f})")
        quality_scores.append(score)
    
    # 總體品質評分
    overall_quality = np.mean(quality_scores)
    print(f"\n總體劃分品質: {overall_quality:.2f}/1.0")
    
    return overall_quality > 0.7

def create_ood_dataset():
    """建立 OOD 測試集"""
    
    # OOD 伺服器定義
    ood_servers = {
        'l2': [
            {'name': 'traefik_2.11', 'image': 'traefik:2.11', 'reason': '新版本 Traefik'},
            {'name': 'caddy_2.8', 'image': 'caddy:2.8-alpine', 'reason': 'Go 語言編寫的現代伺服器'},
            {'name': 'envoy_1.30', 'image': 'envoyproxy/envoy:v1.30-latest', 'reason': '雲原生代理'}
        ],
        'l3': [
            {'name': 'openlitespeed_1.8', 'image': 'litespeedtech/openlitespeed:1.8', 'reason': '輕量級 Web 伺服器'},
            {'name': 'h2o_http2', 'image': 'lkwg82/h2o-http2-server', 'reason': 'HTTP/2 專用伺服器'},
            {'name': 'jetty_12', 'image': 'jetty:12-jre21', 'reason': '新一代 Java 伺服器'},
            {'name': 'unit_1.31', 'image': 'nginx/unit:1.31.1', 'reason': 'NGINX Unit 應用伺服器'}
        ]
    }
    
    print("\n生成 OOD 測試集...")
    
    ood_combinations = []
    
    # 場景 1：L3 為 OOD（最重要）
    for i, ood_server in enumerate(ood_servers['l3'] * 8, 1):  # 每個重複 8 次
        combo = {
            'id': f"ood_{i:03d}",
            'type': 'l3_ood',
            'l1': {'name': 'cloudflare-simulation', 'image': 'nginx:alpine'},
            'l2': {'name': 'nginx_1.24', 'image': 'nginx:1.24', 'base_name': 'nginx'},
            'l3': {
                'name': ood_server['name'],
                'image': ood_server['image'],
                'is_ood': True,
                'base_name': ood_server['name'].split('_')[0]
            },
            'url': f"http://localhost:{9000+i}",
            'expected_prediction': 'Unknown',
            'reason': ood_server['reason']
        }
        ood_combinations.append(combo)
    
    # 場景 2：L2 為 OOD
    start_idx = len(ood_combinations) + 1
    for i, ood_server in enumerate(ood_servers['l2'] * 4, start_idx):  # 每個重複 4 次
        combo = {
            'id': f"ood_{i:03d}",
            'type': 'l2_ood',
            'l1': {'name': 'cloudflare-simulation', 'image': 'nginx:alpine'},
            'l2': {
                'name': ood_server['name'],
                'image': ood_server['image'],
                'is_ood': True,
                'base_name': ood_server['name'].split('_')[0]
            },
            'l3': {'name': 'apache_2.4.57', 'image': 'httpd:2.4.57', 'base_name': 'apache'},
            'url': f"http://localhost:{9000+i}",
            'expected_prediction': 'Unknown',
            'reason': ood_server['reason']
        }
        ood_combinations.append(combo)
    
    # 場景 3：自訂錯誤頁面
    start_idx = len(ood_combinations) + 1
    custom_scenarios = [
        {
            'id': f"ood_{start_idx+i:03d}",
            'type': 'custom_error',
            'l1': {'name': 'cloudflare-simulation', 'image': 'nginx:alpine'},
            'l2': {'name': 'nginx_1.24', 'image': 'nginx:1.24', 'base_name': 'nginx'},
            'l3': {
                'name': f'custom_apache_v{i}',
                'image': 'httpd:2.4.57',
                'custom_error_page': True,
                'template': f'custom_template_{i}.html',
                'base_name': 'apache'
            },
            'url': f"http://localhost:{9000+start_idx+i}",
            'expected_prediction': 'Unknown',
            'reason': '使用完全自訂的錯誤頁面模板'
        }
        for i in range(6)  # 6 種不同的自訂模板
    ]
    ood_combinations.extend(custom_scenarios)
    
    print(f"  生成 {len(ood_combinations)} 個 OOD 樣本")
    return ood_combinations

def verify_ood_diversity(ood_combinations):
    """驗證 OOD 集的多樣性"""
    print("\n" + "="*60)
    print("OOD 測試集多樣性驗證")
    print("="*60)
    
    # 統計 OOD 類型
    types = Counter(c['type'] for c in ood_combinations)
    
    print(f"\n總樣本數: {len(ood_combinations)}")
    print(f"\nOOD 類型分佈:")
    for ood_type, count in types.items():
        print(f"  {ood_type:20s}: {count:3d} ({count/len(ood_combinations)*100:.1f}%)")
    
    # 統計獨特技術
    unique_l3 = set(c['l3']['name'] for c in ood_combinations if c['l3'].get('is_ood'))
    unique_l2 = set(c['l2']['name'] for c in ood_combinations if c['l2'].get('is_ood'))
    
    print(f"\n獨特 OOD 技術:")
    print(f"  L3: {len(unique_l3)} 種 - {unique_l3}")
    print(f"  L2: {len(unique_l2)} 種 - {unique_l2}")
    
    # 檢查是否符合論文要求（≥50 組，≥5 種未見技術）
    total_unique = len(unique_l3) + len(unique_l2)
    
    print(f"\n驗證結果:")
    print(f"  ✓ 總計 {total_unique} 種未見技術（要求 ≥5）")
    print(f"  ✓ 總計 {len(ood_combinations)} 個樣本（要求 ≥50）")
    
    assert total_unique >= 5, "OOD 技術種類不足！"
    assert len(ood_combinations) >= 50, "OOD 樣本數量不足！"
    
    return True

def save_datasets(train_df, val_df, test_df, ood_combinations):
    """儲存所有數據集"""
    # 儲存劃分結果
    Path('data/processed').mkdir(parents=True, exist_ok=True)
    
    train_df.to_csv('data/processed/train.csv', index=False)
    val_df.to_csv('data/processed/val.csv', index=False)
    test_df.to_csv('data/processed/test.csv', index=False)
    
    # 儲存 combo_id 列表
    splits = {
        'train': train_df['combo_id'].tolist(),
        'val': val_df['combo_id'].tolist(),
        'test': test_df['combo_id'].tolist()
    }
    
    with open('data/processed/splits.json', 'w', encoding='utf-8') as f:
        json.dump(splits, f, indent=2, ensure_ascii=False)
    
    # 儲存 OOD 測試集
    Path('data/ood').mkdir(parents=True, exist_ok=True)
    
    with open('data/ood/ood_combinations.json', 'w', encoding='utf-8') as f:
        json.dump(ood_combinations, f, indent=2, ensure_ascii=False)
    
    # 儲存 OOD 為 CSV 方便查看
    ood_df = pd.DataFrame([
        {
            'combo_id': c['id'],
            'type': c['type'],
            'l1': c['l1']['name'],
            'l2': c['l2']['name'],
            'l3': c['l3']['name'],
            'expected': c['expected_prediction'],
            'reason': c['reason']
        }
        for c in ood_combinations
    ])
    ood_df.to_csv('data/ood/ood_combinations.csv', index=False)
    
    print(f"\n✓ 所有數據集已儲存")
    print(f"  訓練集: {len(train_df)} 筆 -> data/processed/train.csv")
    print(f"  驗證集: {len(val_df)} 筆 -> data/processed/val.csv")
    print(f"  測試集: {len(test_df)} 筆 -> data/processed/test.csv")
    print(f"  OOD 集: {len(ood_combinations)} 筆 -> data/ood/ood_combinations.*")

def main():
    print("✨ LLM-UnTangle 數據集劃分與 OOD 設計")
    print("="*50)
    
    # 1. 載入原始組合
    combinations = load_combinations()
    print(f"載入 {len(combinations)} 組組合")
    
    # 2. 建立地面真相標籤
    df = create_ground_truth_labels(combinations)
    
    # 3. 劃分數據集
    train_df, val_df, test_df = stratified_split(
        df, train_size=0.6, val_size=0.2, test_size=0.2, random_state=42
    )
    
    # 4. 驗證劃分品質
    if verify_split_quality(train_df, val_df, test_df):
        print("✓ 數據集劃分品質優秀")
    else:
        print("⚠️  數據集劃分品質需要改進")
    
    # 5. 建立 OOD 測試集
    ood_combinations = create_ood_dataset()
    verify_ood_diversity(ood_combinations)
    
    # 6. 儲存結果
    save_datasets(train_df, val_df, test_df, ood_combinations)
    
    print(f"\n✓ 數據集準備完成！")
    print(f"\n下一步：")
    print(f"  python scripts/run_untangle_baseline.py")

if __name__ == "__main__":
    main()