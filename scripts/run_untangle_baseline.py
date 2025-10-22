#!/usr/bin/env python3
"""
Untangle 基線測試（250-300 組假網站測試）
- 使用傳統 Untangle 指紋識別方法測試 L3 服務器準確率
- 預期 L3 準確率：~50-55%（論文目標值）
- 為 LLM-UnTangle 方法提供比較基準
- 產出完整結果供 BCa Bootstrap 統計分析
"""
import json
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict, Counter
import time
import re
import urllib.parse
from urllib.parse import urlparse
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / 'results'
BASELINE_TARGETS_PATH = RESULTS_DIR / 'baseline_targets.json'

# Untangle 指紋識別規則（基於論文原始方法）
SERVER_PATTERNS = {
    'apache': [
        r'apache[/\s]([0-9\.]+)',
        r'apache\b',
        r'httpd',
        r'server:\s*apache'
    ],
    'nginx': [
        r'nginx[/\s]([0-9\.]+)',
        r'nginx\b',
        r'server:\s*nginx'
    ],
    'tomcat': [
        r'apache-coyote',
        r'tomcat[/\s]([0-9\.]+)',
        r'tomcat\b',
        r'coyote',
        r'catalina'
    ],
    'lighttpd': [
        r'lighttpd[/\s]([0-9\.]+)',
        r'lighttpd\b'
    ],
    'caddy': [
        r'caddy[/\s]([0-9\.]+)', 
        r'caddy\b',
        r'server:\s*caddy'
    ],
    'openlitespeed': [
        r'litespeed',
        r'openlitespeed',
        r'lsws'
    ],
    'iis': [
        r'microsoft-iis[/\s]([0-9\.]+)',
        r'iis\b',
        r'microsoft-httpapi'
    ]
}

# HTTP 錯誤頁面特徵模式
ERROR_PAGE_PATTERNS = {
    'apache': [
        r'apache\s+http\s+server',
        r'<address>apache[/\s]([0-9\.]+)',
        r'the\s+requested\s+url.*?was\s+not\s+found',
        r'you\s+don\'t\s+have\s+permission\s+to\s+access'
    ],
    'nginx': [
        r'<center>nginx</center>',
        r'nginx/([0-9\.]+)',
        r'<title>\d+\s+\w+</title>.*?<center>nginx'
    ],
    'tomcat': [
        r'apache\s+tomcat',
        r'<title>.*?tomcat',
        r'type\s+exception\s+report',
        r'the\s+origin\s+server\s+did\s+not\s+find'
    ],
    'lighttpd': [
        r'lighttpd[/\s]([0-9\.]+)',
        r'<title>\d+\s+-\s+\w+</title>.*?lighttpd'
    ],
    'caddy': [
        r'<title>.*?caddy',
        r'server:\s*caddy'
    ],
    'openlitespeed': [
        r'litespeedtech',
        r'litespeed\s+web\s+server',
        r'openlitespeed'
    ]
}


def load_baseline_targets():
    """載入基線測試目標清單"""
    if not BASELINE_TARGETS_PATH.exists():
        raise FileNotFoundError(
            f'找不到基線測試目標文件: {BASELINE_TARGETS_PATH}\n'
            '請先執行: python scripts/start_ood_containers.py'
        )
    
    try:
        with open(BASELINE_TARGETS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            targets = data.get('targets', [])
            print(f'✅ 載入基線測試目標: {len(targets)} 組')
            return targets
    except Exception as e:
        raise RuntimeError(f'載入基線測試目標失敗: {e}')


def extract_server_from_headers(headers: dict) -> str:
    """從 HTTP headers 提取服務器資訊"""
    server_header = headers.get('server', '').lower()
    if not server_header:
        return 'unknown'
    
    # 按優先級檢測服務器類型
    for server_type, patterns in SERVER_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, server_header, re.IGNORECASE):
                return server_type
    
    return 'unknown'


def extract_server_from_content(content: str) -> str:
    """從頁面內容提取服務器資訊"""
    content_lower = content.lower()
    
    # 檢查錯誤頁面特徵
    for server_type, patterns in ERROR_PAGE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, content_lower, re.IGNORECASE | re.DOTALL):
                return server_type
    
    return 'unknown'


def untangle_fingerprint(url: str, timeout: int = 10) -> dict:
    """
    Untangle 指紋識別實現（簡化版）
    基於 HTTP headers 和頁面內容的模式匹配
    """
    try:
        # 發送 HTTP 請求
        response = requests.get(
            url, 
            timeout=timeout, 
            allow_redirects=True,
            headers={'User-Agent': 'Untangle-Fingerprinter/1.0'}
        )
        
        headers = {k.lower(): v for k, v in response.headers.items()}
        content = response.text
        
        # 組合多種識別方法
        server_from_headers = extract_server_from_headers(headers)
        server_from_content = extract_server_from_content(content)
        
        # 優先信任 header 資訊，其次是內容分析
        if server_from_headers != 'unknown':
            identified_server = server_from_headers
            confidence = 0.9
            method = 'header_analysis'
        elif server_from_content != 'unknown':
            identified_server = server_from_content
            confidence = 0.7
            method = 'content_analysis'
        else:
            identified_server = 'unknown'
            confidence = 0.1
            method = 'no_match'
        
        return {
            'identified_server': identified_server,
            'confidence': confidence,
            'method': method,
            'status_code': response.status_code,
            'server_header': headers.get('server', 'N/A'),
            'content_length': len(content),
            'response_time': response.elapsed.total_seconds(),
            'error': None
        }
        
    except requests.Timeout:
        return {
            'identified_server': 'unknown',
            'confidence': 0.0,
            'method': 'timeout',
            'error': 'request_timeout'
        }
    except requests.ConnectionError:
        return {
            'identified_server': 'unknown',
            'confidence': 0.0,
            'method': 'connection_error',
            'error': 'connection_failed'
        }
    except Exception as e:
        return {
            'identified_server': 'unknown',
            'confidence': 0.0,
            'method': 'exception',
            'error': str(e)
        }


def run_baseline_test():
    """執行 Untangle 基線測試"""
    print('🧪 Untangle 基線測試（論文標準版）')
    print('=' * 50)
    print('目標：測試傳統 Untangle 指紋識別方法的 L3 層準確率')
    print('預期結果：L3 準確率 ~50-55%（論文原始標準）\n')
    
    # 載入目標清單
    targets = load_baseline_targets()
    print(f'測試範圍：{len(targets)} 組三層架構組合')
    
    # 分析目標組成
    l3_distribution = Counter(t['expected_l3'] for t in targets)
    print('\nL3 服務器分佈:')
    for server, count in sorted(l3_distribution.items()):
        print(f'  {server}: {count} 組 ({count/len(targets)*100:.1f}%)')
    
    # 執行測試
    results = []
    success_count = 0
    error_count = 0
    
    print(f'\n🔍 開始 Untangle 指紋識別測試...')
    
    for target in tqdm(targets, desc='Untangle 指紋識別'):
        fingerprint_result = untangle_fingerprint(target['url'])
        
        # 計算準確率
        is_correct = (
            fingerprint_result['identified_server'] == target['expected_l3'] and
            fingerprint_result['identified_server'] != 'unknown'
        )
        
        if fingerprint_result['error'] is None:
            success_count += 1
        else:
            error_count += 1
        
        result = {
            'combo_id': target['combo_id'],
            'url': target['url'],
            'expected_l3': target['expected_l3'],
            'predicted_l3': fingerprint_result['identified_server'],
            'is_correct': is_correct,
            'confidence': fingerprint_result['confidence'],
            'method': fingerprint_result['method'],
            'status_code': fingerprint_result.get('status_code'),
            'server_header': fingerprint_result.get('server_header', 'N/A'),
            'response_time': fingerprint_result.get('response_time'),
            'error': fingerprint_result['error'],
            'l1_type': target['L1'],
            'l2_type': target['L2'],
            'l3_type': target['L3']
        }
        results.append(result)
        
        # 適度延遲避免過度負載
        time.sleep(0.05)
    
    # 統計分析
    valid_results = [r for r in results if r['error'] is None]
    correct_predictions = [r for r in valid_results if r['is_correct']]
    
    overall_accuracy = len(correct_predictions) / len(valid_results) if valid_results else 0
    
    # 各服務器類型的準確率
    server_accuracy = {}
    for server_type in set(t['expected_l3'] for t in targets):
        server_results = [r for r in valid_results if r['expected_l3'] == server_type]
        correct_server = [r for r in server_results if r['is_correct']]
        server_accuracy[server_type] = {
            'accuracy': len(correct_server) / len(server_results) if server_results else 0,
            'total': len(server_results),
            'correct': len(correct_server)
        }
    
    # 混淆矩陣分析
    prediction_matrix = defaultdict(lambda: defaultdict(int))
    for r in valid_results:
        prediction_matrix[r['expected_l3']][r['predicted_l3']] += 1
    
    # 保存結果
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    output = {
        'timestamp': timestamp,
        'method': 'Untangle Baseline Fingerprinting',
        'test_summary': {
            'total_targets': len(targets),
            'successful_tests': success_count,
            'failed_tests': error_count,
            'valid_predictions': len(valid_results),
            'correct_predictions': len(correct_predictions),
            'overall_accuracy': overall_accuracy,
            'error_rate': error_count / len(targets) if targets else 0
        },
        'l3_server_accuracy': server_accuracy,
        'prediction_matrix': dict(prediction_matrix),
        'method_distribution': Counter(r['method'] for r in results),
        'detailed_results': results
    }
    
    # 輸出結果
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = RESULTS_DIR / f'untangle_baseline_results_{int(time.time())}.json'
    output_file.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), 
        encoding='utf-8'
    )
    
    # 控制台報告
    print('\n' + '='*50)
    print('📈 Untangle 基線測試結果')
    print('='*50)
    
    print(f'測試範圍: {len(targets)} 組三層架構')
    print(f'成功測試: {success_count} ({success_count/len(targets)*100:.1f}%)')
    print(f'失敗測試: {error_count} ({error_count/len(targets)*100:.1f}%)')
    print(f'\n🎯 L3 整體準確率: {overall_accuracy:.3f} ({overall_accuracy*100:.1f}%)')
    
    # 論文預期對照
    expected_range = (0.50, 0.55)
    if expected_range[0] <= overall_accuracy <= expected_range[1]:
        status = '✅ 符合預期'
    elif overall_accuracy < expected_range[0]:
        status = '⚠️ 低於預期'
    else:
        status = '📈 高於預期'
    
    print(f'論文預期範圍: {expected_range[0]*100:.0f}-{expected_range[1]*100:.0f}% | 實際結果: {status}')
    
    # 各服務器類型的詳細準確率
    print('\n📉 各 L3 服務器類型準確率:')
    for server, stats in sorted(server_accuracy.items()):
        print(f'  {server:12}: {stats["accuracy"]:6.3f} ({stats["accuracy"]*100:5.1f}%) '
              f'[{stats["correct"]}/{stats["total"]}]')
    
    # 最常見的誤判情況
    print('\n🔍 主要設別錯誤:')
    error_count = defaultdict(int)
    for r in valid_results:
        if not r['is_correct'] and r['predicted_l3'] != 'unknown':
            error_key = f"{r['expected_l3']} → {r['predicted_l3']}"
            error_count[error_key] += 1
    
    for error_type, count in sorted(error_count.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f'  {error_type}: {count} 次')
    
    print(f'\n📋 詳細結果已保存至: {output_file}')
    print('✅ 可用於 BCa Bootstrap 統計分析')
    
    # 返回結果供後續分析
    return {
        'accuracy': overall_accuracy,
        'total_tests': len(targets),
        'successful_tests': success_count,
        'results_file': str(output_file)
    }


if __name__ == '__main__':
    try:
        result = run_baseline_test()
        print(f'\n🎉 基線測試完成!')
        print(f'L3 準確率: {result["accuracy"]:.1%}')
        print(f'成功測試: {result["successful_tests"]}/{result["total_tests"]}')
        exit(0 if result['accuracy'] > 0 else 1)
    except Exception as e:
        print(f'❌ 基線測試失敗: {e}')
        exit(1)