#!/usr/bin/env python3
"""
第二階段驗證：完整工作流程檢查
- OOD 容器啟動狀態
- Untangle 基線測試結果
- BCa Bootstrap 統計分析
- 論文實驗完整性驗證
"""
import json
import sys
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
RESULT = {
    'ood_containers': {},
    'baseline_test': {},
    'bca_confidence': {},
    'paper_requirements': {},
    'summary': {}
}
PASS, FAIL, WARN = 'PASS', 'FAIL', 'WARN'

def record(section, key, status, detail=""):
    RESULT[section][key] = {'status': status, 'detail': detail}
    return status == PASS

def check_ood_containers():
    """檢查 OOD 容器狀態"""
    ood_status_path = ROOT / 'results' / 'ood_containers_status.json'
    if not ood_status_path.exists():
        return record('ood_containers', 'status_file', FAIL, 
                     '缺少 ood_containers_status.json，請執行 start_ood_containers.py')
    
    try:
        data = json.loads(ood_status_path.read_text(encoding='utf-8'))
        running_count = data.get('ood_services_running', 0)
        meets_req = data.get('paper_requirements_met', False)
        
        if running_count == 0:
            return record('ood_containers', 'services', FAIL, 'no OOD services running')
        
        detail = f"running={running_count}, requirements_met={meets_req}"
        status = PASS if meets_req else WARN
        return record('ood_containers', 'requirements', status, detail)
        
    except Exception as e:
        return record('ood_containers', 'parse_error', FAIL, str(e))

def check_baseline_test():
    """檢查基線測試結果"""
    baseline_path = ROOT / 'results' / 'untangle_baseline_results.json'
    if not baseline_path.exists():
        return record('baseline_test', 'results_file', FAIL, 
                     '缺少 untangle_baseline_results.json，請執行 run_untangle_baseline.py')
    
    try:
        data = json.loads(baseline_path.read_text(encoding='utf-8'))
        test_samples = data.get('test_samples', 0)
        overall_acc = data.get('overall_accuracy', {})
        detailed_results = data.get('detailed_results', [])
        
        if test_samples == 0:
            return record('baseline_test', 'samples', FAIL, 'no test samples processed')
        
        # 檢查 L3 準確率
        l3_acc = overall_acc.get('l3', -1)
        if not (0 <= l3_acc <= 1):
            return record('baseline_test', 'validity', FAIL, f'invalid L3 accuracy: {l3_acc}')
        
        # 檢查詳細結果（BCa 需要）
        if len(detailed_results) != test_samples:
            return record('baseline_test', 'completeness', WARN, 
                         f'detailed_results={len(detailed_results)}, expected={test_samples}')
        
        detail = f"samples={test_samples}, L3_accuracy={l3_acc:.3f}, detailed_complete={len(detailed_results)==test_samples}"
        return record('baseline_test', 'results', PASS, detail)
        
    except Exception as e:
        return record('baseline_test', 'parse_error', FAIL, str(e))

def check_bca_confidence():
    """檢查 BCa 統計分析"""
    bca_path = ROOT / 'results' / 'bca_confidence_intervals.json'
    if not bca_path.exists():
        return record('bca_confidence', 'results_file', FAIL, 
                     '缺少 bca_confidence_intervals.json，請執行 calculate_bca_confidence.py')
    
    try:
        data = json.loads(bca_path.read_text(encoding='utf-8'))
        l3_analysis = data.get('l3_accuracy_analysis', {})
        
        if not l3_analysis:
            return record('bca_confidence', 'analysis', FAIL, 'no L3 analysis found')
        
        # 檢查關鍵統計指標
        lower = l3_analysis.get('lower_bound', -1)
        upper = l3_analysis.get('upper_bound', -1)
        bootstrap_samples = l3_analysis.get('bootstrap_samples', 0)
        
        if not (0 <= lower <= upper <= 1):
            return record('bca_confidence', 'validity', FAIL, 
                         f'invalid confidence interval: [{lower:.3f}, {upper:.3f}]')
        
        if bootstrap_samples < 1000:
            return record('bca_confidence', 'bootstrap_quality', WARN, 
                         f'low bootstrap samples: {bootstrap_samples}')
        
        ci_width = upper - lower
        detail = f"CI=[{lower:.3f}, {upper:.3f}], width={ci_width:.3f}, bootstrap_n={bootstrap_samples}"
        return record('bca_confidence', 'statistics', PASS, detail)
        
    except Exception as e:
        return record('bca_confidence', 'parse_error', FAIL, str(e))

def check_paper_requirements():
    """檢查論文實驗要求完整性"""
    ood_ok = 'ood_containers' in RESULT and any(
        item['status'] == PASS for item in RESULT['ood_containers'].values()
    )
    baseline_ok = 'baseline_test' in RESULT and any(
        item['status'] == PASS for item in RESULT['baseline_test'].values()
    )
    bca_ok = 'bca_confidence' in RESULT and any(
        item['status'] == PASS for item in RESULT['bca_confidence'].values()
    )
    
    # OOD 檢測實驗
    record('paper_requirements', 'ood_detection', PASS if ood_ok else FAIL, 
           'Out-of-Distribution 檢測實驗環境')
    
    # 基線比較
    record('paper_requirements', 'baseline_comparison', PASS if baseline_ok else FAIL,
           'Untangle vs LLM-UnTangle 基線比較')
    
    # 統計驗證
    record('paper_requirements', 'statistical_validation', PASS if bca_ok else FAIL,
           'BCa Bootstrap 置信區間統計驗證')
    
    # 完整工作流程
    all_complete = ood_ok and baseline_ok and bca_ok
    record('paper_requirements', 'complete_pipeline', PASS if all_complete else FAIL,
           f'完整論文實驗管線 (OOD={ood_ok}, Baseline={baseline_ok}, Stats={bca_ok})')
    
    return all_complete

def main():
    print('🧪 LLM-UnTangle 第二階段驗證（完整工作流程）')
    print('=' * 60)
    
    ok_ood = check_ood_containers()
    ok_baseline = check_baseline_test()
    ok_bca = check_bca_confidence()
    ok_paper = check_paper_requirements()
    
    overall = all([ok_ood, ok_baseline, ok_bca])
    
    RESULT['summary'] = {
        'overall': PASS if overall else FAIL,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'paper_ready': ok_paper
    }
    
    # 輸出報告
    out_dir = ROOT / 'results'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'stage2_verification.json').write_text(
        json.dumps(RESULT, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    
    print('\n📋 驗證摘要:')
    for section, items in RESULT.items():
        if section == 'summary':
            continue
        print(f"\n{section.upper().replace('_', ' ')}:")
        for key, val in items.items():
            status_icon = '✅' if val['status'] == PASS else '⚠️' if val['status'] == WARN else '❌'
            print(f"  {status_icon} {key}: {val.get('detail','')}"))
    
    print(f"\n🎯 總體狀態: {RESULT['summary']['overall']}")
    if RESULT['summary']['paper_ready']:
        print('🎉 論文實驗環境完整，可進行所有分析!')
    else:
        print('⚠️ 部分實驗組件未完成，請檢查上述項目')
    
    print('\n📄 詳細報告已保存到: results/stage2_verification.json')
    
    sys.exit(0 if overall else 1)

if __name__ == '__main__':
    main()