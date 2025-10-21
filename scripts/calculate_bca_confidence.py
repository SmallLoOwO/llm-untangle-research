#!/usr/bin/env python3
"""
BCa Bootstrap 置信區間計算（修正版）
- 使用完整 detailed_results 而非截斷版本
- 增加統計有效性檢查
- 輸出更詳細的統計報告
"""
import json
import numpy as np
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
    if n < 3:
        return 0.0, 0.0  # 樣本太少，返回預設值
        
    theta_hat = statistic_func(data)
    
    # Jackknife 估計
    jackknife_estimates = []
    for i in range(n):
        jackknife_sample = np.concatenate([data[:i], data[i+1:]])
        jackknife_estimates.append(statistic_func(jackknife_sample))
    
    jackknife_estimates = np.array(jackknife_estimates)
    theta_dot = np.mean(jackknife_estimates)
    
    # 偏差校正 z0
    proportion = np.sum(jackknife_estimates < theta_hat) / n
    z0 = stats.norm.ppf(max(0.001, min(0.999, proportion)))
    
    # 加速參數 a
    numerator = np.sum((theta_dot - jackknife_estimates) ** 3)
    denominator = 6 * (np.sum((theta_dot - jackknife_estimates) ** 2) ** 1.5)
    a = numerator / denominator if abs(denominator) > 1e-10 else 0
    
    return z0, a

def bca_bootstrap(data, statistic_func, n_bootstrap=10000, alpha=0.05):
    """BCa Bootstrap 置信區間計算"""
    n = len(data)
    if n < 5:
        return {'error': f'樣本數太少 (n={n})，無法進行 Bootstrap 分析'}
    
    # Bootstrap 重抽樣
    print(f'進行 {n_bootstrap:,} 次 Bootstrap 重抽樣...')
    bootstrap_estimates = []
    
    np.random.seed(42)
    for _ in tqdm(range(n_bootstrap), desc='Bootstrap 抽樣'):
        bootstrap_sample = np.random.choice(data, size=n, replace=True)
        bootstrap_estimates.append(statistic_func(bootstrap_sample))
    
    bootstrap_estimates = np.array(bootstrap_estimates)
    
    # 計算 z0 與 a
    print('計算 Bias-Correction 與 Acceleration 參數...')
    z0, a = jackknife_bias_acceleration(data, statistic_func)
    
    # BCa 調整
    z_alpha_2 = stats.norm.ppf(alpha / 2)
    z_1_alpha_2 = stats.norm.ppf(1 - alpha / 2)
    
    # 防止除零
    denom1 = 1 - a * (z0 + z_alpha_2)
    denom2 = 1 - a * (z0 + z_1_alpha_2)
    
    if abs(denom1) < 1e-10 or abs(denom2) < 1e-10:
        print('⚠️ BCa 參數異常，使用基本 Bootstrap 百分位數')
        alpha1, alpha2 = alpha/2, 1-alpha/2
    else:
        alpha1 = stats.norm.cdf(z0 + (z0 + z_alpha_2) / denom1)
        alpha2 = stats.norm.cdf(z0 + (z0 + z_1_alpha_2) / denom2)
        alpha1 = max(0.001, min(0.999, alpha1))
        alpha2 = max(0.001, min(0.999, alpha2))
    
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
        'alpha2': float(alpha2),
        'original_estimate': float(statistic_func(data))
    }

def calculate_confidence_intervals():
    print('📊 BCa Bootstrap 置信區間計算（修正版）')
    print('=' * 50)
    
    baseline_data = load_baseline_results()
    detailed_results = baseline_data.get('detailed_results', [])
    
    if not detailed_results:
        print('❌ 基線結果中無詳細數據，請重新執行 run_untangle_baseline.py')
        return None
    
    print(f'載入 {len(detailed_results)} 個基線測試結果')
    
    confidence_results = {}
    
    for layer in ['l1', 'l2', 'l3']:
        print(f'\n計算 {layer.upper()} 層 BCa 置信區間...')
        
        # 提取該層的準確率數據
        layer_accuracy = [r['accuracy'][layer] for r in detailed_results]
        accuracy_array = np.array(layer_accuracy, dtype=float)
        
        if len(accuracy_array) < 5:
            print(f'⚠️ {layer} 樣本數不足 ({len(accuracy_array)})，跳過')
            continue
        
        # 定義統計量（平均準確率）
        def accuracy_statistic(sample):
            return np.mean(sample)
        
        # 計算 BCa 置信區間
        bca_result = bca_bootstrap(accuracy_array, accuracy_statistic, n_bootstrap=10000, alpha=0.05)
        
        if 'error' in bca_result:
            print(f'❌ {layer} BCa 計算失敗: {bca_result["error"]}')
            continue
        
        confidence_results[layer] = bca_result
        
        print(f'{layer.upper()} 準確率: {bca_result["original_estimate"]:.3f}')
        print(f'Bootstrap 平均: {bca_result["bootstrap_mean"]:.3f} ± {bca_result["bootstrap_std"]:.3f}')
        print(f'95% BCa 置信區間: [{bca_result["lower_bound"]:.3f}, {bca_result["upper_bound"]:.3f}]')
    
    if not confidence_results:
        print('❌ 無法計算任何層的置信區間')
        return None
    
    # 保存結果
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'method': 'BCa Bootstrap',
        'n_bootstrap': 10000,
        'confidence_level': 0.95,
        'baseline_method': 'Untangle Enhanced',
        'test_samples': len(detailed_results),
        'confidence_intervals': confidence_results
    }
    
    output_path = RESULTS_DIR / 'bca_confidence_intervals.json'
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    
    print(f'\n✓ BCa 置信區間計算完成，結果已保存到 {output_path}')
    return confidence_results

if __name__ == '__main__':
    calculate_confidence_intervals()