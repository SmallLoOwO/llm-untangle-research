#!/usr/bin/env python3
"""
第二階段驗證：容器啟動、基線測試、BCa 置信區間計算
- 驗證 OOD 容器啟動成功率 >= 80%
- 驗證 Untangle 基線測試完成並有效
- 驗證 BCa 置信區間計算結果
- 輸出 JSON 結果與人類可讀摘要
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = {'ood_containers': {}, 'baseline_test': {}, 'bca_confidence': {}, 'summary': {}}
PASS, FAIL, WARN = 'PASS', 'FAIL', 'WARN'


def record(section, key, status, detail=""):
    RESULT[section][key] = {'status': status, 'detail': detail}
    return status == PASS


def check_ood_containers():
    ood_status_path = ROOT / 'results' / 'ood_containers_status.json'
    if not ood_status_path.exists():
        return record('ood_containers', 'status_file', FAIL, 'missing ood_containers_status.json, 請執行 start_ood_containers.py')
    
    try:
        data = json.loads(ood_status_path.read_text(encoding='utf-8'))
        total = data.get('total_ood_combinations', 0)
        running = data.get('status_summary', {}).get('running', 0)
        
        if total == 0:
            return record('ood_containers', 'containers', FAIL, 'no OOD combinations found')
        
        success_rate = running / total
        ok = success_rate >= 0.8
        detail = f"running={running}/{total} ({success_rate:.1%})"
        return record('ood_containers', 'success_rate', PASS if ok else FAIL, detail)
        
    except Exception as e:
        return record('ood_containers', 'parse_error', FAIL, str(e))


def check_baseline_test():
    baseline_path = ROOT / 'results' / 'untangle_baseline_results.json'
    if not baseline_path.exists():
        return record('baseline_test', 'results_file', FAIL, 'missing untangle_baseline_results.json, 請執行 run_untangle_baseline.py')
    
    try:
        data = json.loads(baseline_path.read_text(encoding='utf-8'))
        test_samples = data.get('test_samples', 0)
        overall_acc = data.get('overall_accuracy', {})
        
        if test_samples == 0:
            return record('baseline_test', 'samples', FAIL, 'no test samples processed')
        
        # 檢查每層準確率是否存在
        missing_layers = [layer for layer in ['l1', 'l2', 'l3'] if layer not in overall_acc]
        if missing_layers:
            return record('baseline_test', 'completeness', FAIL, f'missing layers: {missing_layers}')
        
        # 檢查準確率是否合理 (0-1 之間)
        invalid_acc = {layer: acc for layer, acc in overall_acc.items() if not (0 <= acc <= 1)}
        if invalid_acc:
            return record('baseline_test', 'validity', FAIL, f'invalid accuracy: {invalid_acc}')
        
        detail = f"samples={test_samples}, L1={overall_acc['l1']:.3f}, L2={overall_acc['l2']:.3f}, L3={overall_acc['l3']:.3f}"
        return record('baseline_test', 'accuracy', PASS, detail)
        
    except Exception as e:
        return record('baseline_test', 'parse_error', FAIL, str(e))


def check_bca_confidence():
    bca_path = ROOT / 'results' / 'bca_confidence_intervals.json'
    if not bca_path.exists():
        return record('bca_confidence', 'results_file', FAIL, 'missing bca_confidence_intervals.json, 請執行 calculate_bca_confidence.py')
    
    try:
        data = json.loads(bca_path.read_text(encoding='utf-8'))
        confidence_intervals = data.get('confidence_intervals', {})
        
        if not confidence_intervals:
            return record('bca_confidence', 'intervals', FAIL, 'no confidence intervals calculated')
        
        # 檢查每層置信區間
        missing_layers = [layer for layer in ['l1', 'l2', 'l3'] if layer not in confidence_intervals]
        if missing_layers:
            return record('bca_confidence', 'completeness', FAIL, f'missing layers: {missing_layers}')
        
        # 檢查置信區間的有效性
        for layer, interval in confidence_intervals.items():
            lower = interval.get('lower_bound', -1)
            upper = interval.get('upper_bound', -1)
            if not (0 <= lower <= upper <= 1):
                return record('bca_confidence', 'validity', FAIL, f'{layer} invalid interval: [{lower:.3f}, {upper:.3f}]')
        
        # 總結資訊
        n_bootstrap = data.get('n_bootstrap', 0)
        confidence_level = data.get('confidence_level', 0)
        detail = f"bootstrap={n_bootstrap}, confidence={confidence_level}, layers={list(confidence_intervals.keys())}"
        return record('bca_confidence', 'calculation', PASS, detail)
        
    except Exception as e:
        return record('bca_confidence', 'parse_error', FAIL, str(e))


def main():
    print('🧪 LLM-UnTangle 第二階段驗證')
    print('=' * 45)
    
    ok_ood = check_ood_containers()
    ok_baseline = check_baseline_test()
    ok_bca = check_bca_confidence()
    
    overall = all([ok_ood, ok_baseline, ok_bca])
    
    RESULT['summary'] = {
        'overall': PASS if overall else FAIL,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # 輸出報告
    out_dir = ROOT / 'results'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'stage2_checklist.json').write_text(
        json.dumps(RESULT, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    
    print('\n摘要:')
    for section, items in RESULT.items():
        if section == 'summary':
            continue
        print(f"- {section}:")
        for key, val in items.items():
            print(f"  [{val['status']}] {key} - {val.get('detail','')}")
    
    print(f"\n總結: {RESULT['summary']['overall']}")
    print('結果檔: results/stage2_checklist.json')
    
    sys.exit(0 if overall else 1)


if __name__ == '__main__':
    main()