#!/usr/bin/env python3
"""
Untangle 基線測試腳本
- 對測試集進行 Untangle 原始指紋識別，作為基線性能比較
- 計算 L1/L2/L3 各層準確率
- 輸出結果到 results/untangle_baseline_results.json
"""
import json
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict
import time

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA_PATH = ROOT / 'data' / 'processed' / 'test.csv'
RESULTS_DIR = ROOT / 'results'

def load_test_data():
    if not TEST_DATA_PATH.exists():
        raise FileNotFoundError(f'找不到 {TEST_DATA_PATH}，請先執行 prepare_datasets.py')
    return pd.read_csv(TEST_DATA_PATH)

def simulate_untangle_fingerprinting(url):
    """模擬 Untangle 指紋識別（基於 HTTP 標頭）"""
    try:
        response = requests.get(url, timeout=10)
        headers = response.headers
        predictions = {}
        
        # L1 (CDN)
        if 'cf-ray' in headers or 'CF-Cache-Status' in headers:
            predictions['l1'] = 'cloudflare-simulation'
        elif 'X-Served-By' in headers and 'fastly' in str(headers.get('X-Served-By', '')).lower():
            predictions['l1'] = 'fastly-simulation'
        elif 'X-Akamai-Edgescape' in headers:
            predictions['l1'] = 'akamai-simulation'
        else:
            predictions['l1'] = 'unknown'
        
        # L2 (Proxy)
        server_header = headers.get('Server', '').lower()
        if 'nginx' in server_header:
            predictions['l2'] = 'nginx'
        elif 'varnish' in server_header:
            predictions['l2'] = 'varnish'
        elif 'haproxy' in headers.get('X-Powered-By', '').lower():
            predictions['l2'] = 'haproxy'
        elif 'traefik' in headers.get('X-Forwarded-Server', '').lower():
            predictions['l2'] = 'traefik'
        elif 'envoy' in server_header:
            predictions['l2'] = 'envoy'
        else:
            predictions['l2'] = 'unknown'
        
        # L3 (Application Server)
        if 'apache' in server_header or 'httpd' in server_header:
            predictions['l3'] = 'apache'
        elif 'nginx' in server_header and predictions['l2'] != 'nginx':
            predictions['l3'] = 'nginx'
        elif 'tomcat' in server_header or ('X-Powered-By' in headers and 'tomcat' in headers['X-Powered-By'].lower()):
            predictions['l3'] = 'tomcat'
        elif 'lighttpd' in server_header:
            predictions['l3'] = 'lighttpd'
        elif 'caddy' in server_header:
            predictions['l3'] = 'caddy'
        elif 'openlitespeed' in server_header or 'litespeed' in server_header:
            predictions['l3'] = 'openlitespeed'
        else:
            predictions['l3'] = 'unknown'
            
        return predictions
        
    except Exception as e:
        return {'l1': 'error', 'l2': 'error', 'l3': 'error', 'error': str(e)}

def run_baseline_test():
    print('🧪 Untangle 基線測試')
    print('=' * 40)
    
    test_df = load_test_data()
    print(f'載入 {len(test_df)} 個測試樣本')
    
    results = []
    for _, row in tqdm(test_df.iterrows(), total=len(test_df), desc='Untangle 指紋識別'):
        predictions = simulate_untangle_fingerprinting(row['url'])
        
        result = {
            'combo_id': row['combo_id'],
            'url': row['url'],
            'ground_truth': {
                'l1': row['l1_true'],
                'l2': row['l2_base'],
                'l3': row['l3_base']
            },
            'predictions': predictions,
            'accuracy': {
                'l1': predictions['l1'] == row['l1_true'],
                'l2': predictions['l2'] == row['l2_base'],
                'l3': predictions['l3'] == row['l3_base']
            }
        }
        results.append(result)
        time.sleep(0.1)
    
    # 計算準確率
    accuracy_stats = defaultdict(list)
    for r in results:
        for layer in ['l1', 'l2', 'l3']:
            accuracy_stats[layer].append(r['accuracy'][layer])
    
    overall_accuracy = {layer: np.mean(acc_list) for layer, acc_list in accuracy_stats.items()}
    
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'method': 'Untangle Baseline',
        'test_samples': len(results),
        'overall_accuracy': overall_accuracy,
        'layer_accuracy': {
            layer: {'mean': float(np.mean(acc_list)), 'std': float(np.std(acc_list))}
            for layer, acc_list in accuracy_stats.items()
        },
        'detailed_results': results[:10]
    }
    
    output_path = RESULTS_DIR / 'untangle_baseline_results.json'
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    
    print(f'\nUntangle 基線準確率：')
    for layer, acc in overall_accuracy.items():
        print(f'  {layer.upper()}: {acc:.3f} ({acc*100:.1f}%)')
    
    print(f'\n✓ 基線測試完成，結果已保存到 {output_path}')
    return overall_accuracy

if __name__ == '__main__':
    run_baseline_test()