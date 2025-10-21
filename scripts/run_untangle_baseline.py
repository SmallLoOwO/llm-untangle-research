#!/usr/bin/env python3
"""
Untangle 基線測試與 BCa Bootstrap 置信區間計算
實現統計嚴謹的基線準確率評估
"""

import json
import subprocess
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm
from scipy import stats
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import requests

def collect_http_responses(combinations, output_dir='data/raw/responses'):
    """收集 HTTP 響應侜為 Untangle 輸入"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 定義 HTTP 探針（基於 Untangle 論文）
    probes = [
        # 基礎探針
        {'method': 'GET', 'path': '/', 'headers': {}},
        {'method': 'HEAD', 'path': '/', 'headers': {}},
        
        # 錯誤探針
        {'method': 'GET', 'path': '/nonexistent', 'headers': {}},
        {'method': 'POST', 'path': '/', 'headers': {}},
        
        # 特殊 Header 探針 
        {'method': 'GET', 'path': '/', 'headers': {'Host': 'invalid-host.com'}},
        {'method': 'GET', 'path': '/', 'headers': {'User-Agent': 'InvalidAgent/1.0'}},
        {'method': 'GET', 'path': '/', 'headers': {'Accept': 'invalid/type'}},
        
        # HTTP 版本探針
        {'method': 'GET', 'path': '/', 'headers': {}, 'version': '1.0'},
        {'method': 'GET', 'path': '/', 'headers': {}, 'version': '1.1'},
        
        # 非法請求
        {'method': 'INVALID', 'path': '/', 'headers': {}},
        {'method': 'GET', 'path': '/<script>alert(1)</script>', 'headers': {}},
        
        # 內容探針
        {'method': 'GET', 'path': '/admin', 'headers': {}},
        {'method': 'GET', 'path': '/.well-known/', 'headers': {}},
        {'method': 'OPTIONS', 'path': '*', 'headers': {}},
    ]
    
    print(f"收集 {len(combinations)} 個目標的 HTTP 響應...")
    
    def collect_single_target(combo):
        """收集單個目標的所有探針響應"""
        url_base = combo['url']
        responses = []
        
        for probe in probes:
            try:
                # 建構請求
                full_url = f"{url_base.rstrip('/')}{probe['path']}"
                
                response = requests.request(
                    method=probe['method'],
                    url=full_url,
                    headers=probe['headers'],
                    timeout=10,
                    allow_redirects=False
                )
                
                # 記錄響應
                responses.append({
                    'probe': probe,
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'body': response.text[:2000],  # 限制長度
                    'size': len(response.content)
                })
                
            except Exception as e:
                # 記錄錯誤情況
                responses.append({
                    'probe': probe,
                    'error': str(e),
                    'status_code': -1,
                    'headers': {},
                    'body': '',
                    'size': 0
                })
            
            # 避免過度請求
            time.sleep(0.1)
        
        # 儲存響應
        output_file = Path(output_dir) / f"{combo['id']}_responses.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(responses, f, indent=2, ensure_ascii=False)
        
        return combo['id'], len(responses)
    
    # 併行收集（控制併行度避免過載）
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(collect_single_target, combo) for combo in combinations]
        
        for future in tqdm(as_completed(futures), total=len(combinations)):
            combo_id, probe_count = future.result()
    
    print(f"✓ HTTP 響應收集完成")

def prepare_untangle_input(test_df, responses_dir='data/raw/responses'):
    """準備 Untangle 輸入格式"""
    untangle_data = []
    
    for _, row in test_df.iterrows():
        combo_id = row['combo_id']
        
        # 載入此組合的 HTTP 響應
        response_file = Path(responses_dir) / f"{combo_id}_responses.json"
        if not response_file.exists():
            print(f"⚠️  缺少響應檔案: {response_file}")
            continue
        
        with open(response_file, encoding='utf-8') as f:
            responses = json.load(f)
        
        untangle_data.append({
            'combo_id': combo_id,
            'url': row['url'],
            'ground_truth': {
                'l1': row['l1_true'],
                'l2': row['l2_true'],
                'l3': row['l3_true']
            },
            'probes': responses
        })
    
    return untangle_data

def simulate_untangle_predictions(untangle_data):
    """
    模擬 Untangle 的預測結果
    注意：這是模擬，實際使用時需要連接真實的 Untangle 程式
    """
    print("\n模擬 Untangle 預測結果（基於論文數據）...")
    
    results = []
    
    for data in tqdm(untangle_data):
        # 模擬不同層級的準確率（基於論文結果）
        l1_accuracy = 1.0    # L1 準確率 100%
        l2_accuracy = 0.903  # L2 準確率 90.3%
        l3_accuracy = 0.507  # L3 準確率 50.7%
        
        gt = data['ground_truth']
        
        # 模擬預測結果（按照各層準確率）
        predictions = {}
        
        # L1 預測（几乎總是正確）
        if np.random.random() < l1_accuracy:
            predictions['l1'] = gt['l1']
        else:
            # 隨機錯誤預測
            wrong_l1 = ['cloudflare-simulation', 'akamai-simulation', 'fastly-simulation']
            wrong_l1 = [x for x in wrong_l1 if x != gt['l1']]
            predictions['l1'] = np.random.choice(wrong_l1) if wrong_l1 else 'unknown'
        
        # L2 預測
        if np.random.random() < l2_accuracy:
            predictions['l2'] = gt['l2']
        else:
            wrong_l2 = ['nginx_1.24', 'varnish_7.3', 'haproxy_2.8', 'traefik_2.10']
            wrong_l2 = [x for x in wrong_l2 if not x.startswith(gt['l2'].split('_')[0])]
            predictions['l2'] = np.random.choice(wrong_l2) if wrong_l2 else 'unknown'
        
        # L3 預測（最難）
        if np.random.random() < l3_accuracy:
            predictions['l3'] = gt['l3']
        else:
            wrong_l3 = ['apache_2.4.57', 'tomcat_9.0', 'nginx_1.24', 'lighttpd_1.4.71']
            wrong_l3 = [x for x in wrong_l3 if not x.startswith(gt['l3'].split('_')[0])]
            predictions['l3'] = np.random.choice(wrong_l3) if wrong_l3 else 'unknown'
        
        results.append({
            'combo_id': data['combo_id'],
            'success': True,
            'predictions': predictions,
            'confidence': {
                'l1': np.random.uniform(0.8, 1.0),
                'l2': np.random.uniform(0.6, 0.9),
                'l3': np.random.uniform(0.3, 0.7)
            }
        })
    
    return results

def calculate_accuracy(results, test_df):
    """計算準確率"""
    ground_truth = test_df.set_index('combo_id').to_dict('index')
    
    metrics = {
        'l1': {'correct': 0, 'total': 0, 'binary_results': []},
        'l2': {'correct': 0, 'total': 0, 'binary_results': []},
        'l3': {'correct': 0, 'total': 0, 'binary_results': []}
    }
    
    for result in results:
        if not result['success']:
            continue
        
        combo_id = result['combo_id']
        gt = ground_truth[combo_id]
        pred = result['predictions']
        
        for layer in ['l1', 'l2', 'l3']:
            metrics[layer]['total'] += 1
            is_correct = pred.get(layer) == gt[f'{layer}_true']
            
            if is_correct:
                metrics[layer]['correct'] += 1
                metrics[layer]['binary_results'].append(1)
            else:
                metrics[layer]['binary_results'].append(0)
    
    # 計算準確率
    accuracies = {}
    for layer, data in metrics.items():
        if data['total'] > 0:
            accuracies[layer] = data['correct'] / data['total']
        else:
            accuracies[layer] = 0.0
    
    return accuracies, metrics

def bca_bootstrap(data, statistic_func=np.mean, n_bootstrap=10000, alpha=0.05):
    """
    BCa (Bias-Corrected and Accelerated) Bootstrap
    比標準 Bootstrap 更準確的置信區間估計
    """
    n = len(data)
    data = np.array(data)
    
    # 1. 原始統計量
    theta_hat = statistic_func(data)
    
    # 2. Bootstrap 重抽樣
    bootstrap_samples = []
    for _ in tqdm(range(n_bootstrap), desc="BCa Bootstrap", leave=False):
        resample_idx = np.random.choice(n, size=n, replace=True)
        resample = data[resample_idx]
        bootstrap_samples.append(statistic_func(resample))
    
    bootstrap_samples = np.array(bootstrap_samples)
    
    # 3. 計算 Bias Correction (z0)
    prop_less = np.mean(bootstrap_samples < theta_hat)
    # 避免極端值
    prop_less = np.clip(prop_less, 1e-10, 1-1e-10)
    z0 = stats.norm.ppf(prop_less)
    
    # 4. 計算 Acceleration (a) - 使用 Jackknife
    jackknife_samples = []
    for i in range(n):
        # 留一法
        jack_sample = np.delete(data, i)
        jackknife_samples.append(statistic_func(jack_sample))
    
    jackknife_samples = np.array(jackknife_samples)
    jack_mean = np.mean(jackknife_samples)
    
    numerator = np.sum((jack_mean - jackknife_samples) ** 3)
    denominator = 6 * (np.sum((jack_mean - jackknife_samples) ** 2) ** 1.5)
    
    a = numerator / denominator if abs(denominator) > 1e-10 else 0
    
    # 5. 調整後的分位數
    z_alpha_lower = stats.norm.ppf(alpha / 2)
    z_alpha_upper = stats.norm.ppf(1 - alpha / 2)
    
    # 計算調整後的機率
    def adjusted_percentile(z_alpha):
        numerator = z0 + z_alpha
        denominator = 1 - a * (z0 + z_alpha)
        if abs(denominator) < 1e-10:
            return 0.5  # fallback
        adjusted_z = z0 + numerator / denominator
        return stats.norm.cdf(adjusted_z)
    
    adjusted_lower = adjusted_percentile(z_alpha_lower)
    adjusted_upper = adjusted_percentile(z_alpha_upper)
    
    # 確保在有效範圍內
    adjusted_lower = np.clip(adjusted_lower, 0, 1)
    adjusted_upper = np.clip(adjusted_upper, 0, 1)
    
    # 6. 從 Bootstrap 樣本中取調整後的分位數
    lower_bound = np.percentile(bootstrap_samples, adjusted_lower * 100)
    upper_bound = np.percentile(bootstrap_samples, adjusted_upper * 100)
    
    return lower_bound, upper_bound, z0, a

def analyze_baseline_results(results, test_df):
    """分析 Untangle 基線結果並計算 BCa 置信區間"""
    print("\n" + "="*70)
    print("Untangle 基線準確率與 BCa 95% 置信區間")
    print("="*70)
    
    accuracies, metrics = calculate_accuracy(results, test_df)
    statistics = {}
    
    for layer in ['l1', 'l2', 'l3']:
        binary_results = np.array(metrics[layer]['binary_results'])
        
        if len(binary_results) == 0:
            continue
        
        # 計算 BCa 置信區間
        try:
            lower, upper, z0, a = bca_bootstrap(binary_results, n_bootstrap=10000)
        except Exception as e:
            print(f"⚠️  {layer} BCa 計算失敗: {e}")
            # Fallback 到標準 bootstrap
            bootstrap_means = []
            for _ in range(1000):
                resample = np.random.choice(binary_results, size=len(binary_results), replace=True)
                bootstrap_means.append(np.mean(resample))
            lower = np.percentile(bootstrap_means, 2.5)
            upper = np.percentile(bootstrap_means, 97.5)
            z0, a = 0, 0
        
        acc = accuracies[layer]
        ci_width = (upper - lower) * 100
        
        print(f"\n{layer.upper()} 層:")
        print(f"  準確率:           {acc*100:6.2f}%")
        print(f"  BCa 95% CI:       [{lower*100:6.2f}%, {upper*100:6.2f}%]")
        print(f"  CI 寬度:          ±{ci_width/2:5.2f}%")
        print(f"  Bias (z0):        {z0:7.4f}")
        print(f"  Acceleration (a): {a:7.4f}")
        print(f"  樣本數:           {len(binary_results)}")
        
        statistics[layer] = {
            'accuracy': float(acc),
            'ci_lower': float(lower),
            'ci_upper': float(upper),
            'ci_width': float(ci_width),
            'bias_correction': float(z0),
            'acceleration': float(a),
            'sample_size': len(binary_results)
        }
    
    print("="*70 + "\n")
    
    return statistics

def save_baseline_results(results, statistics):
    """儲存基線測試結果"""
    Path('results').mkdir(parents=True, exist_ok=True)
    
    # 儲存詳細結果
    with open('results/untangle_baseline_results.json', 'w', encoding='utf-8') as f:
        json.dump({
            'detailed_results': results,
            'statistics': statistics,
            'metadata': {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_samples': len(results),
                'method': 'BCa Bootstrap (10,000 iterations)'
            }
        }, f, indent=2, ensure_ascii=False)
    
    # 儲存統計摘要
    with open('results/untangle_baseline_statistics.json', 'w', encoding='utf-8') as f:
        json.dump(statistics, f, indent=2)
    
    print(f"✓ 基線結果已儲存至 results/ 目錄")

def main():
    print("✨ Untangle 基線測試與統計分析")
    print("="*50)
    
    # 1. 載入測試集
    test_df = pd.read_csv('data/processed/test.csv')
    print(f"載入測試集: {len(test_df)} 筆")
    
    # 2. 載入組合資訊以取得 URL
    with open('data/combinations.json', encoding='utf-8') as f:
        combinations = json.load(f)
    
    # 篩選測試集的組合
    test_combinations = [c for c in combinations if c['id'] in test_df['combo_id'].tolist()]
    
    # 3. 收集 HTTP 響應（如果尚未收集）
    if not Path('data/raw/responses').exists() or len(list(Path('data/raw/responses').glob('*.json'))) < len(test_combinations) * 0.8:
        print("收集 HTTP 響應...")
        collect_http_responses(test_combinations)
    else:
        print("✓ HTTP 響應已存在，跳過收集")
    
    # 4. 準備 Untangle 輸入
    untangle_data = prepare_untangle_input(test_df)
    print(f"準備 Untangle 輸入: {len(untangle_data)} 個目標")
    
    # 5. 執行 Untangle （模擬）
    results = simulate_untangle_predictions(untangle_data)
    
    # 6. 分析結果與計算置信區間
    statistics = analyze_baseline_results(results, test_df)
    
    # 7. 儲存結果
    save_baseline_results(results, statistics)
    
    print(f"\n✓ Untangle 基線測試完成！")
    print(f"\n關鍵結果:")
    for layer, stats in statistics.items():
        print(f"  {layer.upper()}: {stats['accuracy']*100:.1f}% "
              f"[{stats['ci_lower']*100:.1f}%, {stats['ci_upper']*100:.1f}%]")

if __name__ == "__main__":
    # 設定隨機種子以確保可重現
    np.random.seed(42)
    main()