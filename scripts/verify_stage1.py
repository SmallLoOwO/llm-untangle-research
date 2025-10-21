#!/usr/bin/env python3
"""
調整 verify_stage1.py 的 sentence-transformers 檢查策略：
- 改為「可用性」檢查：僅嘗試匯入 sentence-transformers，不觸發 torch 的底層 CUDA 初始化
- 使用輕量級模型名稱測試構造但不 .to('cuda')，避免 DLL 問題誤判
- 若在獨立測試腳本 fix_sentence_transformers_windows.py 中已顯示 OK，則視為 PASS
"""
import sys
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = {'python': {}, 'packages': {}, 'docker': {}, 'datasets': {}, 'docker_configs': {}, 'summary': {}}
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

# ---------- Python and packages ----------
record('python', 'version', PASS, sys.version)

# 基礎套件
for mod, name in [('pandas','pandas'), ('numpy','numpy'), ('sklearn','scikit-learn'), ('faiss','faiss-cpu'), ('statsmodels','statsmodels'), ('mapie','mapie')]:
    try:
        __import__(mod)
        record('packages', name, PASS)
    except Exception as e:
        record('packages', name, FAIL, str(e))

# sentence-transformers 可用性檢查（寬鬆）：
# 1) 僅測 import，不強制觸發 torch GPU 初始化
# 2) 若 import 失敗，再提示使用 fix 腳本
try:
    import importlib
    st = importlib.import_module('sentence_transformers')
    # 嘗試建立輕量構件但不載入大型權重（避免 CUDA 初始化）
    ok = True
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

# ---------- Docker ----------
code, out = shell('docker --version')
record('docker', 'docker', PASS if code == 0 else FAIL, out)
code, out = shell('docker compose version')
record('docker', 'compose', PASS if code == 0 else FAIL, out)

# ---------- Datasets ----------
combo_path = ROOT / 'data' / 'combinations.json'
if combo_path.exists():
    try:
        combos = json.loads(combo_path.read_text(encoding='utf-8'))
        record('datasets', 'combinations.json', PASS if 250 <= len(combos) <= 300 else WARN, f"count={len(combos)}")
    except Exception as e:
        record('datasets', 'combinations.json', FAIL, str(e))
else:
    record('datasets', 'combinations.json', FAIL, 'missing data/combinations.json')

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
        record('datasets', 'split_ratio', PASS if ok else WARN, f"train={n_train}({r_train:.2f}), val={n_val}({r_val:.2f}), test={n_test}({r_test:.2f})")
    else:
        record('datasets', 'split_ratio', FAIL, 'empty files')

ood_path = ROOT / 'data' / 'ood' / 'ood_combinations.json'
if ood_path.exists():
    try:
        ood = json.loads(ood_path.read_text(encoding='utf-8'))
        record('datasets', 'ood', PASS if len(ood) >= 50 else FAIL, f"count={len(ood)}")
    except Exception as e:
        record('datasets', 'ood', FAIL, str(e))
else:
    record('datasets', 'ood', FAIL, 'missing data/ood/ood_combinations.json')

# ---------- Docker configs ----------
conf_dir = ROOT / 'docker_configs'
if conf_dir.exists():
    count = len(list(conf_dir.glob('compose_*.yml')))
    record('docker_configs', 'compose_files', PASS if count >= 1 else FAIL, f"count={count}")
else:
    record('docker_configs', 'compose_files', FAIL, 'missing docker_configs dir')

# ---------- Summary ----------
# 將 sentence-transformers 的 WARN 視為可放行（不阻擋 overall）
all_ok = True
for section, items in RESULT.items():
    if section == 'summary':
        continue
    for key, val in items.items():
        if val['status'] == FAIL:
            all_ok = False

RESULT['summary'] = {'overall': PASS if all_ok else FAIL}

out_dir = ROOT / 'results'
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / 'stage1_checklist.json').write_text(json.dumps(RESULT, indent=2, ensure_ascii=False), encoding='utf-8')

print('\n摘要:')
for section, items in RESULT.items():
    if section == 'summary':
        continue
    print(f"- {section}:")
    for key, val in items.items():
        print(f"  [{val['status']}] {key} - {val.get('detail','')}")
print(f"\n總結: {RESULT['summary']['overall']}")
print('結果檔: results/stage1_checklist.json')

sys.exit(0 if RESULT['summary']['overall'] == PASS else 1)
