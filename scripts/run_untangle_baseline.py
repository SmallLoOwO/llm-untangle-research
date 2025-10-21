#!/usr/bin/env python3
"""
Untangle 基線測試（修正版）
- 確保容器先運行再測試
- 保存完整詳細結果供 BCa 計算使用
- 改善 HTTP 標頭識別邏輯
"""
import json
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict
import time
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA_PATH = ROOT / 'data' / 'processed' / 'test.csv'
RESULTS_DIR = ROOT / 'results'

def load_test_data():
    if not TEST_DATA_PATH.exists():
        raise FileNotFoundError(f'找不到 {TEST_DATA_PATH}，請先執行 prepare_datasets.py')
    return pd.read_csv(TEST_DATA_PATH)

def ensure_containers_running():
    """確保主要測試容器正在運行"""
    cmd = "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'combo_[0-9]+_l1'"
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    running_containers = len([line for line in proc.stdout.split('\n') if 'combo_' in line and 'Up' in line])
    
    if running_containers == 0:
        print('⚠️ 未檢測到運行中的測試容器，建議先啟動部分容器：')
        print('  docker compose -f docker_configs/compose_combo_001.yml up -d')
        print('  docker compose -f docker_configs/compose_combo_002.yml up -d')
        print('  # ... 啟動更多測試容器')
        return False
    
    print(f'✓ 檢測到 {running_containers} 個運行中的測試容器')
    return True

def enhanced_untangle_fingerprinting(url):
    """增強版 Untangle 指紋識別"""
    try:
        response = requests.get(url, timeout=10, allow_redirects=True)
        headers = {k.lower(): v.lower() for k, v in response.headers.items()}
        content = response.text.lower()
        
        predictions = {}
        
        # L1 (CDN) 識別 - 基於特殊標頭
        if any(key in headers for key in ['cf-ray', 'cf-cache-status', 'cf-request-id']):
            predictions['l1'] = 'cloudflare-simulation'
        elif any(key in headers for key in ['x-served-by', 'x-cache', 'x-fastly-request-id']) and 'fastly' in str(headers.values()):
            predictions['l1'] = 'fastly-simulation'
        elif any(key in headers for key in ['x-akamai-edgescape', 'x-akamai-request-id']):
            predictions['l1'] = 'akamai-simulation'
        else:
            predictions['l1'] = 'unknown'
        
        # L2 (Proxy) 識別 - 基於 Server 標頭與代理特徵
        server_header = headers.get('server', '')
        via_header = headers.get('via', '')
        
        if 'nginx' in server_header:
            predictions['l2'] = 'nginx'
        elif 'varnish' in server_header or 'varnish' in via_header:
            predictions['l2'] = 'varnish'
        elif 'haproxy' in server_header or any('haproxy' in v for v in headers.values()):
            predictions['l2'] = 'haproxy'
        elif 'traefik' in server_header or any('traefik' in v for v in headers.values()):
            predictions['l2'] = 'traefik'
        elif 'envoy' in server_header:
            predictions['l2'] = 'envoy'
        else:
            predictions['l2'] = 'unknown'
        
        # L3 (Application Server) 識別 - 基於內容與標頭特徵
        powered_by = headers.get('x-powered-by', '')
        
        if 'apache' in server_header or 'httpd' in server_header:
            predictions['l3'] = 'apache'
        elif 'tomcat' in server_header or 'tomcat' in powered_by:
            predictions['l3'] = 'tomcat'
        elif 'jetty' in server_header or 'jetty' in powered_by:
            predictions['l3'] = 'jetty'
        elif 'nginx' in server_header and predictions['l2'] != 'nginx':
            predictions['l3'] = 'nginx'
        elif 'lighttpd' in server_header:
            predictions['l3'] = 'lighttpd'
        elif 'caddy' in server_header:
            predictions['l3'] = 'caddy'
        elif any(term in server_header for term in ['openlitespeed', 'litespeed']):
            predictions['l3'] = 'openlitespeed'
        elif '<title>' in content and ('apache' in content or 'httpd' in content):
            predictions['l3'] = 'apache'
        elif '<title>' in content and 'tomcat' in content:
            predictions['l3'] = 'tomcat'
        else:
            predictions['l3'] = 'unknown'
            
        return predictions, {'headers': dict(response.headers), 'status': response.status_code}
        
    except Exception as e:
        return {'l1': 'error', 'l2': 'error', 'l3': 'error'}, {'error': str(e)}

def run_baseline_test():
    print('🧪 Untangle 基線測試（修正版）')
    print('=' * 40)
    
    if not ensure_containers_running():
        print('❌ 請先啟動測試容器後再執行基線測試')
        return None
    
    test_df = load_test_data()
    print(f'載入 {len(test_df)} 個測試樣本')
    
    results = []
    for _, row in tqdm(test_df.iterrows(), total=len(test_df), desc='Untangle 指紋識別'):
        predictions, metadata = enhanced_untangle_fingerprinting(row['url'])
        
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
            },
            'metadata': metadata
        }
        results.append(result)
        time.sleep(0.2)  # 避免過快請求
    
    # 計算準確率
    accuracy_stats = defaultdict(list)
    for r in results:
        for layer in ['l1', 'l2', 'l3']:
            accuracy_stats[layer].append(r['accuracy'][layer])
    
    overall_accuracy = {layer: np.mean(acc_list) for layer, acc_list in accuracy_stats.items()}
    
    # 保存完整結果（包含所有詳細資料供 BCa 使用）
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'method': 'Untangle Baseline Enhanced',
        'test_samples': len(results),
        'overall_accuracy': overall_accuracy,
        'layer_accuracy': {
            layer: {'mean': float(np.mean(acc_list)), 'std': float(np.std(acc_list))}
            for layer, acc_list in accuracy_stats.items()
        },
        'detailed_results': results  # 保存全部結果
    }
    
    output_path = RESULTS_DIR / 'untangle_baseline_results.json'
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    
    print(f'\nUntangle 基線準確率：')
    for layer, acc in overall_accuracy.items():
        print(f'  {layer.upper()}: {acc:.3f} ({acc*100:.1f}%)')
    
    # 顯示識別統計
    print(f'\n識別統計：')
    for layer in ['l1', 'l2', 'l3']:
        pred_counts = defaultdict(int)
        for r in results:
            pred_counts[r['predictions'][layer]] += 1
        top_3 = sorted(pred_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        print(f'  {layer.upper()}: {", ".join([f"{k}({v})" for k,v in top_3])}')
    
    print(f'\n✓ 基線測試完成，結果已保存到 {output_path}')
    return overall_accuracy

if __name__ == '__main__':
    run_baseline_test()