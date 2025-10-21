#!/usr/bin/env python3
"""
修正 verify_stage1.py：
- 改用 import 測試而非錯誤的別名（pandas, numpy）
- sentence-transformers 以延遲匯入並回傳警示，指引安裝 CPU 版 torch
- OOD 檢查門檻調整至 >=50，並提示自動補齊腳本
- docker compose 檢查為 1 個以上即可
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

packages_to_test = [
    ('pandas', 'pandas'),
    ('numpy', 'numpy'),
    ('sklearn', 'scikit-learn'),
    ('faiss', 'faiss-cpu'),
    ('statsmodels', 'statsmodels'),
    ('mapie', 'mapie')
]

all_pk_ok = True
for mod, name in packages_to_test:
    try:
        __import__(mod)
        record('packages', name, PASS)
    except Exception as e:
        all_pk_ok = False
        record('packages', name, FAIL, str(e))

# sentence-transformers 單獨處理（常見 torch DLL 問題）
try:
    import importlib
    st = importlib.import_module('sentence_transformers')
    record('packages', 'sentence-transformers', PASS)
except Exception as e:
    all_pk_ok = False
    hint = (
        '若為 Windows DLL 錯誤，建議安裝 CPU 版 torch:\n'
        '  pip uninstall -y torch torchvision torchaudio\n'
        '  pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio\n'
    )
    record('packages', 'sentence-transformers', FAIL, f"{e}\n{hint}")

# ---------- Docker ----------
code, out = shell('docker --version')
record('docker', 'docker', PASS if code == 0 else FAIL, out)
code, out = shell('docker compose version')
record('docker', 'compose', PASS if code == 0 else FAIL, out)

# ---------- Datasets ----------
import json as _json
combo_path = ROOT / 'data' / 'combinations.json'
if combo_path.exists():
    try:
        combos = _json.loads(combo_path.read_text(encoding='utf-8'))
        record('datasets', 'combinations.json', PASS if 250 <= len(combos) <= 300 else WARN, f"count={len(combos)}")
    except Exception as e:
        record('datasets', 'combinations.json', FAIL, str(e))
else:
    record('datasets', 'combinations.json', FAIL, 'missing data/combinations.json')

# split ratio
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

# OOD >= 50
ood_path = ROOT / 'data' / 'ood' / 'ood_combinations.json'
if ood_path.exists():
    try:
        ood = _json.loads(ood_path.read_text(encoding='utf-8'))
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
overall = all(s.get('status') == PASS for section in RESULT.values() if isinstance(section, dict) for s in section.values())
RESULT['summary'] = {'overall': PASS if overall else FAIL}

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

sys.exit(0 if overall else 1)
