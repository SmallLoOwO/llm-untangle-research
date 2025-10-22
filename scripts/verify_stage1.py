#!/usr/bin/env python3
"""
LLM-UnTangle 第一階段完整驗證（包含原第二階段內容）
- 基礎環境檢查（Python、套件、Docker）
- 資料集完整性驗證
- OOD 容器狀態檢查
- Untangle 基線測試結果
- BCa Bootstrap 統計分析
- 論文實驗完整性驗證
"""
import sys
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = {
    'python': {},
    'packages': {},
    'docker': {},
    'datasets': {},
    'docker_configs': {},
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

def shell(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, shell=True, cwd=ROOT)
        return out.returncode, out.stdout.strip() or out.stderr.strip()
    except Exception as e:
        return 1, str(e)

# ========== 基礎環境檢查 ==========
def check_python_environment():
    """檢查 Python 環境和基礎套件"""
    record('python', 'version', PASS, sys.version)

    # 基礎套件
    for mod, name in [('pandas','pandas'), ('numpy','numpy'), ('sklearn','scikit-learn'), 
                      ('faiss','faiss-cpu'), ('statsmodels','statsmodels'), ('mapie','mapie')]:
        try:
            __import__(mod)
            record('packages', name, PASS)
        except Exception as e:
            record('packages', name, FAIL, str(e))

    # sentence-transformers 可用性檢查（寬鬆）
    try:
        import importlib
        st = importlib.import_module('sentence_transformers')
        record('packages', 'sentence-transformers', PASS)
    except Exception as e:
        hint = (
            '若為 Windows DLL 錯誤，請先執行一鍵修復:\n'
            '  python scripts\\fix_sentence_transformers_windows.py\n'
            '或手動安裝 CPU 版 torch：\n'
            '  pip uninstall -y torch torchvision torchaudio\n'
            '  pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio\n'
        )
        record('packages', 'sentence-transformers', WARN, f"{e}\n{hint}")

def check_docker():
    """檢查 Docker 環境"""
    code, out = shell('docker --version')
    record('docker', 'docker', PASS if code == 0 else FAIL, out)
    code, out = shell('docker compose version')
    record('docker', 'compose', PASS if code == 0 else FAIL, out)

def check_datasets():
    """檢查資料集完整性"""
    # combinations.json
    combo_path = ROOT / 'data' / 'combinations.json'
    if combo_path.exists():
        try:
            combos = json.loads(combo_path.read_text(encoding='utf-8'))
            record('datasets', 'combinations.json', PASS if 250 <= len(combos) <= 300 else WARN, f"count={len(combos)}")
        except Exception as e:
            record('datasets', 'combinations.json', FAIL, str(e))
    else:
        record('datasets', 'combinations.json', FAIL, 'missing data/combinations.json')

    # 資料分割檔案
    proc = ROOT / 'data' / 'processed'
    missing = [f for f in ['train.csv','val.csv','test.csv'] if not (proc / f).exists()]
    if missing:
        record('datasets', 'splits', FAIL, f"missing: {missing}")
    else:
        def cnt(p):
            try:
                return sum(1 for _ in open(p, 'r', encoding='utf-8')) - 1
            except Exception:
                return -1
        n_train, n_val, n_test = cnt(proc/'train.csv'), cnt(proc/'val.csv'), cnt(proc/'test.csv')
        total = n_train + n_val + n_test
        if total > 0:
            r_train, r_val, r_test = n_train/total, n_val/total, n_test/total
            ok = abs(r_train-0.6)<=0.1 and abs(r_val-0.2)<=0.1 and abs(r_test-0.2)<=0.1
            record('datasets', 'split_ratio', PASS if ok else WARN, 
                   f"train={n_train}({r_train:.2f}), val={n_val}({r_val:.2f}), test={n_test}({r_test:.2f})")
        else:
            record('datasets', 'split_ratio', FAIL, 'empty files')

    # OOD 資料集
    ood_path = ROOT / 'data' / 'ood' / 'ood_combinations.json'
    if ood_path.exists():
        try:
            ood = json.loads(ood_path.read_text(encoding='utf-8'))
            record('datasets', 'ood', PASS if len(ood) >= 50 else FAIL, f"count={len(ood)}")
        except Exception as e:
            record('datasets', 'ood', FAIL, str(e))
    else:
        record('datasets', 'ood', FAIL, 'missing data/ood/ood_combinations.json')

def check_docker_configs():
    """檢查 Docker 組態檔案"""
    conf_dir = ROOT / 'docker_configs'
    if conf_dir.exists():
        count = len(list(conf_dir.glob('compose_*.yml')))
        record('docker_configs', 'compose_files', PASS if count >= 1 else FAIL, f"count={count}")
    else:
        record('docker_configs', 'compose_files', FAIL, 'missing docker_configs dir')

# ========== 實驗環境檢查 ==========
def check_ood_containers():
    """檢查 OOD 容器狀態"""
    ood_status_path = ROOT / 'results' / 'ood_containers_status.json'
    if not ood_status_path.exists():
        record('ood_containers', 'status_file', WARN, 
               '缺少 ood_containers_status.json，請執行 start_ood_containers.py')
        return False
    
    try:
        data = json.loads(ood_status_path.read_text(encoding='utf-8'))
        running_count = data.get('ood_services_running', 0)
        meets_req = data.get('paper_requirements_met', False)
        
        if running_count == 0:
            record('ood_containers', 'services', FAIL, 'no OOD services running')
            return False
        
        detail = f"running={running_count}, requirements_met={meets_req}"
        status = PASS if meets_req else WARN
        record('ood_containers', 'requirements', status, detail)
        return meets_req
        
    except Exception as e:
        record('ood_containers', 'parse_error', FAIL, str(e))
        return False

def check_baseline_test():
    """檢查基線測試結果"""
    baseline_path = ROOT / 'results' / 'untangle_baseline_results.json'
    if not baseline_path.exists():
        record('baseline_test', 'results_file', WARN, 
               '缺少 untangle_baseline_results.json，請執行 run_untangle_baseline.py')
        return False
    
    try:
        data = json.loads(baseline_path.read_text(encoding='utf-8'))
        test_samples = data.get('test_samples', 0)
        overall_acc = data.get('overall_accuracy', {})
        detailed_results = data.get('detailed_results', [])
        
        if test_samples == 0:
            record('baseline_test', 'samples', FAIL, 'no test samples processed')
            return False
        
        # 檢查 L3 準確率
        l3_acc = overall_acc.get('l3', -1)
        if not (0 <= l3_acc <= 1):
            record('baseline_test', 'validity', FAIL, f'invalid L3 accuracy: {l3_acc}')
            return False
        
        # 檢查詳細結果（BCa 需要）
        if len(detailed_results) != test_samples:
            record('baseline_test', 'completeness', WARN, 
                   f'detailed_results={len(detailed_results)}, expected={test_samples}')
        
        detail = f"samples={test_samples}, L3_accuracy={l3_acc:.3f}, detailed_complete={len(detailed_results)==test_samples}"
        record('baseline_test', 'results', PASS, detail)
        return True
        
    except Exception as e:
        record('baseline_test', 'parse_error', FAIL, str(e))
        return False

def check_bca_confidence():
    """檢查 BCa 統計分析"""
    bca_path = ROOT / 'results' / 'bca_confidence_intervals.json'
    if not bca_path.exists():
        record('bca_confidence', 'results_file', WARN, 
               '缺少 bca_confidence_intervals.json，請執行 calculate_bca_confidence.py')
        return False
    
    try:
        data = json.loads(bca_path.read_text(encoding='utf-8'))
        l3_analysis = data.get('l3_accuracy_analysis', {})
        
        if not l3_analysis:
            record('bca_confidence', 'analysis', FAIL, 'no L3 analysis found')
            return False
        
        # 檢查關鍵統計指標
        lower = l3_analysis.get('lower_bound', -1)
        upper = l3_analysis.get('upper_bound', -1)
        bootstrap_samples = l3_analysis.get('bootstrap_samples', 0)
        
        if not (0 <= lower <= upper <= 1):
            record('bca_confidence', 'validity', FAIL, 
                   f'invalid confidence interval: [{lower:.3f}, {upper:.3f}]')
            return False
        
        if bootstrap_samples < 1000:
            record('bca_confidence', 'bootstrap_quality', WARN, 
                   f'low bootstrap samples: {bootstrap_samples}')
        
        ci_width = upper - lower
        detail = f"CI=[{lower:.3f}, {upper:.3f}], width={ci_width:.3f}, bootstrap_n={bootstrap_samples}"
        record('bca_confidence', 'statistics', PASS, detail)
        return True
        
    except Exception as e:
        record('bca_confidence', 'parse_error', FAIL, str(e))
        return False

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
    record('paper_requirements', 'ood_detection', PASS if ood_ok else WARN, 
           'Out-of-Distribution 檢測實驗環境')
    
    # 基線比較
    record('paper_requirements', 'baseline_comparison', PASS if baseline_ok else WARN,
           'Untangle vs LLM-UnTangle 基線比較')
    
    # 統計驗證
    record('paper_requirements', 'statistical_validation', PASS if bca_ok else WARN,
           'BCa Bootstrap 置信區間統計驗證')
    
    # 完整工作流程
    all_complete = ood_ok and baseline_ok and bca_ok
    record('paper_requirements', 'complete_pipeline', PASS if all_complete else WARN,
           f'完整論文實驗管線 (OOD={ood_ok}, Baseline={baseline_ok}, Stats={bca_ok})')
    
    return all_complete

def main():
    print('🧪 LLM-UnTangle 第一階段完整驗證')
    print('=' * 60)
    
    # 基礎環境檢查
    print('📋 基礎環境檢查...')
    check_python_environment()
    check_docker()
    check_datasets()
    check_docker_configs()
    
    # 實驗環境檢查
    print('🔬 實驗環境檢查...')
    ok_ood = check_ood_containers()
    ok_baseline = check_baseline_test()
    ok_bca = check_bca_confidence()
    ok_paper = check_paper_requirements()
    
    # 將 sentence-transformers 的 WARN 視為可放行（不阻擋 overall）
    all_ok = True
    for section, items in RESULT.items():
        if section in ['summary', 'paper_requirements']:
            continue
        for key, val in items.items():
            if val['status'] == FAIL:
                all_ok = False

    RESULT['summary'] = {
        'overall': PASS if all_ok else FAIL,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'paper_ready': ok_paper
    }

    # 保存結果
    out_dir = ROOT / 'results'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'stage1_complete_checklist.json').write_text(
        json.dumps(RESULT, indent=2, ensure_ascii=False), encoding='utf-8'
    )

    # 輸出報告
    print('\n📋 驗證摘要:')
    for section, items in RESULT.items():
        if section == 'summary':
            continue
        print(f"\n{section.upper().replace('_', ' ')}:")
        for key, val in items.items():
            status_icon = '✅' if val['status'] == PASS else '⚠️' if val['status'] == WARN else '❌'
            print(f"  {status_icon} {key}: {val.get('detail','')}")

    print(f"\n🎯 總體狀態: {RESULT['summary']['overall']}")
    
    if RESULT['summary']['paper_ready']:
        print('🎉 論文實驗環境完整，可進行所有分析!')
    else:
        print('⚠️ 部分實驗組件未完成，建議執行以下指令完成設定:')
        if not ok_ood:
            print('   python scripts/start_ood_containers.py')
        if not ok_baseline:
            print('   python scripts/run_untangle_baseline.py')
        if not ok_bca:
            print('   python scripts/calculate_bca_confidence.py')

    print(f'\n📄 詳細結果已保存到: results/stage1_complete_checklist.json')

    sys.exit(0 if RESULT['summary']['overall'] == PASS else 1)

if __name__ == '__main__':
    main()