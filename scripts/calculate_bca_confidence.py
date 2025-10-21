#!/usr/bin/env python3
"""
BCa (Bias-Corrected and Accelerated) Bootstrap 置信區間計算
- 載入 Untangle 基線測試結果
- 進行 10,000 次 Bootstrap 重抽樣
- 計算 BCa 置信區間（預設 95%）
- 輸出結果到 results/bca_confidence_intervals.json
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from tqdm import tqdm
from scipy import stats
import time

ROOT = Path(__file__).resolve().parents[1]
BASELINE_RESULTS_PATH = ROOT / 'results' / 'untangle_baseline_results.json'
RESULTS_DIR = ROOT / 'results'


def load_baseline_results():
    if not BASELINE_RESULTS_PATH.exists():
        raise FileNotFoundError(f'找不到 {BASELINE_RESULTS_PATH}，請先執行 run_untangle_baseline.py')
    return json.loads(BASELINE_RESULTS_PATH.read_text(encoding='utf-8'))


def jackknife_bias_acceleration(data, statistic_func):
    """計算 Jackknife 偏差校正與加速參數"""
    n = len(data)
    theta_hat = statistic_func(data)
    
    # Jackknife 結果
    jackknife_estimates = []
    for i in range(n):
        # 移除第 i 個觀測值
        jackknife_sample = np.concatenate([data[:i], data[i+1:]])
        jackknife_estimates.append(statistic_func(jackknife_sample))
    
    jackknife_estimates = np.array(jackknife_estimates)
    theta_dot = np.mean(jackknife_estimates)
    
    # 偏差校正 z0
    proportion = np.sum(jackknife_estimates < theta_hat) / n
    z0 = stats.norm.ppf(proportion) if 0 < proportion < 1 else 0
    
    # 加速參數 a
    numerator = np.sum((theta_dot - jackknife_estimates) ** 3)
    denominator = 6 * (np.sum((theta_dot - jackknife_estimates) ** 2) ** 1.5)
    a = numerator / denominator if denominator != 0 else 0
    
    return z0, a


def bca_bootstrap(data, statistic_func, n_bootstrap=10000, alpha=0.05):
    """
BCa (Bias-Corrected and Accelerated) Bootstrap 置信區間
參考：Efron & Tibshirani (1993) An Introduction to the Bootstrap
"""
    n = len(data)
    
    # 1. Bootstrap 重抽樣
    print(f'進行 {n_bootstrap:,} 次 Bootstrap 重抽樣...')
    bootstrap_estimates = []
    
    np.random.seed(42)  # 確保結果可重現
    for _ in tqdm(range(n_bootstrap), desc='Bootstrap 抽樣'):
        bootstrap_sample = np.random.choice(data, size=n, replace=True)
        bootstrap_estimates.append(statistic_func(bootstrap_sample))
    
    bootstrap_estimates = np.array(bootstrap_estimates)
    
    # 2. 計算 z0 與 a
    print('計算 Bias-Correction 與 Acceleration 參數...')
    z0, a = jackknife_bias_acceleration(data, statistic_func)
    
    # 3. 計算調整後的分位數
    z_alpha_2 = stats.norm.ppf(alpha / 2)
    z_1_alpha_2 = stats.norm.ppf(1 - alpha / 2)
    
    # BCa 調整公式
    alpha1 = stats.norm.cdf(z0 + (z0 + z_alpha_2) / (1 - a * (z0 + z_alpha_2)))
    alpha2 = stats.norm.cdf(z0 + (z0 + z_1_alpha_2) / (1 - a * (z0 + z_1_alpha_2)))
    
    # 確保在 [0, 1] 範圍內
    alpha1 = max(0, min(1, alpha1))
    alpha2 = max(0, min(1, alpha2))
    
    # 計算置信區間
    lower_bound = np.percentile(bootstrap_estimates, alpha1 * 100)
    upper_bound = np.percentile(bootstrap_estimates, alpha2 * 100)
    
    return {
        'lower_bound': float(lower_bound),
        'upper_bound': float(upper_bound),
        'bias_correction_z0': float(z0),
        'acceleration_a': float(a),
        'bootstrap_mean': float(np.mean(bootstrap_estimates)),
        'bootstrap_std': float(np.std(bootstrap_estimates)),
        'alpha1': float(alpha1),
        'alpha2': float(alpha2)
    }


def calculate_confidence_intervals():
    print('📊 BCa Bootstrap 置信區間計算')
    print('=' * 50)
    
    # 載入基線測試結果
    baseline_data = load_baseline_results()
    
    # 提取準確率數據
    test_df = pd.read_csv(ROOT / 'data' / 'processed' / 'test.csv')
    baseline_results = baseline_data.get('detailed_results', [])
    
    if len(baseline_results) < len(test_df):
        print('⚠️ 基線結果不完整，重新執行 run_untangle_baseline.py')
        return
    
    confidence_results = {}
    
    for layer in ['l1', 'l2', 'l3']:
        print(f'\n計算 {layer.upper()} 層 BCa 置信區間...')
        
        # 提取該層的準確率數據
        layer_accuracy = [r['accuracy'][layer] for r in baseline_results]
        accuracy_array = np.array(layer_accuracy, dtype=float)
        
        # 定義統計量（平均準確率）
        def accuracy_statistic(sample):
            return np.mean(sample)
        
        # 計算 BCa 置信區間
        bca_result = bca_bootstrap(accuracy_array, accuracy_statistic, n_bootstrap=10000, alpha=0.05)
        
        confidence_results[layer] = bca_result
        
        print(f'{layer.upper()} 準確率: {bca_result["bootstrap_mean"]:.3f}')
        print(f'95% BCa 置信區間: [{bca_result["lower_bound"]:.3f}, {bca_result["upper_bound"]:.3f}]')
    
    # 保存結果
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'method': 'BCa Bootstrap',
        'n_bootstrap': 10000,
        'confidence_level': 0.95,
        'baseline_method': 'Untangle',
        'test_samples': len(baseline_results),
        'confidence_intervals': confidence_results
    }
    
    output_path = RESULTS_DIR / 'bca_confidence_intervals.json'
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    
    print(f'\n✓ BCa 置信區間計算完成，結果已保存到 {output_path}')
    return confidence_results


if __name__ == '__main__':
    calculate_confidence_intervals()