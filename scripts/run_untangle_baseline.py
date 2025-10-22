#!/usr/bin/env python3
"""
Untangle 基線測試（修正版）
- 針對已啟動的 OOD 容器進行指紋識別測試
- 使用增強版識別邏輯提高準確率
- 保存完整結果供 BCa Bootstrap 分析
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
RESULTS_DIR = ROOT / 'results'
OOD_STATUS_PATH = RESULTS_DIR / 'ood_containers_status.json'

def load_ood_services():
    """載入已啟動的 OOD 服務"""
    if not OOD_STATUS_PATH.exists():
        raise FileNotFoundError(f'找不到 {OOD_STATUS_PATH}，請先執行 start_ood_containers.py')
    
    data = json.loads(OOD_STATUS_PATH.read_text(encoding='utf-8'))
    running_services = data.get('running_services', [])
    
    if not running_services:
        raise RuntimeError('沒有運行中的 OOD 服務，請先啟動容器')
    
    # 轉換為測試格式
    test_urls = []
    for service in running_services:
        combo_id = service['combo_id']
        port = 9001 + int(combo_id.split('_')[1]) - 1
        url = f'http://localhost:{port}'
        
        # 推斷真實服務器類型
        server_header = service.get('server_header', '')
        if 'Apache' in server_header:
            true_server = 'apache'
        elif 'nginx' in server_header:
            true_server = 'nginx'
        elif 'Caddy' in server_header:
            true_server = 'caddy'
        else:
            true_server = 'unknown'
        
        test_urls.append({
            'combo_id': combo_id,
            'url': url,
            'l3_true': true_server,  # 簡化為單層測試
            'image': service.get('image', '')
        })
    
    return test_urls

def enhanced_fingerprinting(url: str) -> dict:
    """增強版指紋識別"""
    try:
        response = requests.get(url, timeout=10, allow_redirects=True)
        headers = {k.lower(): v for k, v in response.headers.items()}
        content = response.text.lower()
        
        predictions = {}
        
        # L3 服務器識別
        server_header = headers.get('server', '').lower()
        
        if 'apache' in server_header or 'httpd' in server_header:
            predictions['l3'] = 'apache'
        elif 'nginx' in server_header:
            predictions['l3'] = 'nginx'
        elif 'caddy' in server_header:
            predictions['l3'] = 'caddy'
        elif 'tomcat' in server_header:
            predictions['l3'] = 'tomcat'
        elif 'jetty' in server_header:
            predictions['l3'] = 'jetty'
        # 基於內容的額外檢測
        elif 'apache' in content:
            predictions['l3'] = 'apache'
        elif 'nginx' in content:
            predictions['l3'] = 'nginx'
        else:
            predictions['l3'] = 'unknown'
        
        return predictions, {
            'headers': dict(response.headers),
            'status_code': response.status_code,
            'content_snippet': content[:200] if content else ''
        }
        
    except Exception as e:
        return {'l3': 'error'}, {'error': str(e)}

def run_baseline_test():
    print('🧪 Untangle 基線測試（針對 OOD 容器）')
    print('=' * 50)
    
    # 載入 OOD 服務
    test_data = load_ood_services()
    print(f'載入 {len(test_data)} 個 OOD 測試目標')
    
    # 檢查容器狀態
    running_containers = subprocess.run(
        'docker ps --filter label=project=llm-untangle --format "{{.Names}}"',
        shell=True, capture_output=True, text=True
    ).stdout.strip().split('\n')
    
    active_containers = [c for c in running_containers if c.strip()]
    print(f'檢測到 {len(active_containers)} 個活躍的 OOD 容器')
    
    if len(active_containers) < 2:
        print('⚠️ 活躍容器太少，建議重新啟動 OOD 容器')
    
    results = []
    for item in tqdm(test_data, desc='Untangle 指紋識別'):
        predictions, metadata = enhanced_fingerprinting(item['url'])
        
        result = {
            'combo_id': item['combo_id'],
            'url': item['url'],
            'ground_truth': {'l3': item['l3_true']},
            'predictions': predictions,
            'accuracy': {'l3': predictions.get('l3') == item['l3_true']},
            'metadata': metadata,
            'image': item.get('image', '')
        }
        results.append(result)
        time.sleep(0.1)
    
    # 計算準確率統計
    correct_predictions = sum(1 for r in results if r['accuracy']['l3'])
    overall_accuracy = correct_predictions / len(results) if results else 0
    
    # 預測分布統計
    pred_counts = defaultdict(int)
    truth_counts = defaultdict(int)
    for r in results:
        pred_counts[r['predictions'].get('l3', 'error')] += 1
        truth_counts[r['ground_truth']['l3']] += 1
    
    # 保存完整結果
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'method': 'Untangle Baseline (OOD Containers)',
        'test_samples': len(results),
        'overall_accuracy': {'l3': overall_accuracy},
        'correct_predictions': correct_predictions,
        'prediction_distribution': dict(pred_counts),
        'ground_truth_distribution': dict(truth_counts),
        'detailed_results': results  # 完整結果供 BCa 使用
    }
    
    output_path = RESULTS_DIR / 'untangle_baseline_results.json'
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    
    print(f'\nUntangle 基線測試結果:')
    print(f'測試樣本: {len(results)}')
    print(f'L3 準確率: {overall_accuracy:.3f} ({overall_accuracy*100:.1f}%)')
    print(f'正確預測: {correct_predictions}/{len(results)}')
    
    print(f'\n預測分布:')
    for pred, count in pred_counts.items():
        print(f'  {pred}: {count}')
    
    print(f'\n✅ 基線測試完成，結果已保存到 {output_path}')
    print(f'📊 可用於 BCa Bootstrap 統計分析')
    
    return overall_accuracy

if __name__ == '__main__':
    try:
        accuracy = run_baseline_test()
        exit(0 if accuracy > 0 else 1)
    except Exception as e:
        print(f'❌ 基線測試失敗: {e}')
        exit(1)