#!/usr/bin/env python3
"""
第一階段完成度自動驗證腳本
- 檢查 Python 版本與套件
- 檢查 Docker 與 Docker Compose
- 檢查 data/combinations.json 是否存在且數量為 250-300（預設 280）
- 檢查 processed 分割檔是否存在（train/val/test）且比例接近 60/20/20
- 檢查 OOD 測試集是否 >= 50 筆
- 檢查 docker_configs 內是否已生成 compose 檔案
- 產出總結報告與 JSON 結果
"""
import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1] if Path(__file__).name.endswith('.py') else Path.cwd()

RESULT = {
    'python': {},
    'packages': {},
    'docker': {},
    'datasets': {},
    'docker_configs': {},
    'summary': {}
}

PASS = 'PASS'
FAIL = 'FAIL'
WARN = 'WARN'


def record(section, key, ok, detail=""):
    RESULT[section][key] = {
        'status': PASS if ok else FAIL,
        'detail': detail
    }
    return ok


def shell(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, shell=True, cwd=ROOT)
        return out.returncode, out.stdout.strip() or out.stderr.strip()
    except Exception as e:
        return 1, str(e)


def check_python():
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 10
    record('python', 'version', ok, f"{sys.version}")

    # 套件檢查
    pkgs = {
        'pandas': 'pd', 'numpy': 'np', 'scikit-learn': 'sklearn',
        'sentence-transformers': 'sentence_transformers', 'faiss-cpu': 'faiss',
        'statsmodels': 'statsmodels', 'mapie': 'mapie'
    }
    all_ok = True
    for name, imp in pkgs.items():
        try:
            __import__(imp)
            record('packages', name, True)
        except Exception as e:
            all_ok = False
            record('packages', name, False, str(e))
    return ok and all_ok


def check_docker():
    code, out = shell('docker --version')
    ok_docker = record('docker', 'docker', code == 0, out)

    code, out = shell('docker compose version')
    ok_compose = record('docker', 'compose', code == 0, out)

    return ok_docker and ok_compose


def check_combinations():
    combo_path = ROOT / 'data' / 'combinations.json'
    if not combo_path.exists():
        return record('datasets', 'combinations.json', False, 'missing data/combinations.json')
    try:
        data = json.loads(combo_path.read_text(encoding='utf-8'))
        n = len(data)
        ok = 250 <= n <= 300
        return record('datasets', 'combinations.json', ok, f"count={n}")
    except Exception as e:
        return record('datasets', 'combinations.json', False, str(e))


def check_splits():
    base = ROOT / 'data' / 'processed'
    files = ['train.csv', 'val.csv', 'test.csv']
    missing = [f for f in files if not (base / f).exists()]
    if missing:
        return record('datasets', 'splits', False, f"missing: {missing}")

    # 粗略檢查比例
    def count_lines(p):
        try:
            return sum(1 for _ in open(p, 'r', encoding='utf-8')) - 1  # 去掉表頭
        except Exception:
            return -1

    train_n = count_lines(base / 'train.csv')
    val_n = count_lines(base / 'val.csv')
    test_n = count_lines(base / 'test.csv')
    total = train_n + val_n + test_n

    if total <= 0:
        return record('datasets', 'splits', False, 'empty files')

    r_train = train_n / total
    r_val = val_n / total
    r_test = test_n / total

    ok = abs(r_train - 0.6) <= 0.1 and abs(r_val - 0.2) <= 0.1 and abs(r_test - 0.2) <= 0.1
    detail = f"train={train_n}({r_train:.2f}), val={val_n}({r_val:.2f}), test={test_n}({r_test:.2f})"
    return record('datasets', 'split_ratio', ok, detail)


def check_ood():
    p = ROOT / 'data' / 'ood' / 'ood_combinations.json'
    if not p.exists():
        return record('datasets', 'ood', False, 'missing data/ood/ood_combinations.json')
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        ok = len(data) >= 50
        return record('datasets', 'ood', ok, f"count={len(data)}")
    except Exception as e:
        return record('datasets', 'ood', False, str(e))


def check_docker_configs():
    d = ROOT / 'docker_configs'
    if not d.exists():
        return record('docker_configs', 'exists', False, 'missing docker_configs dir')
    files = list(d.glob('compose_*.yml'))
    ok = len(files) >= 1
    return record('docker_configs', 'compose_files', ok, f"count={len(files)}")


def main():
    print('🧪 LLM-UnTangle 第一階段完成度驗證')
    print('=' * 45)

    ok_py = check_python()
    ok_dk = check_docker()
    ok_combo = check_combinations()
    ok_splits = check_splits()
    ok_ood = check_ood()
    ok_cfg = check_docker_configs()

    overall = all([ok_py, ok_dk, ok_combo, ok_splits, ok_ood, ok_cfg])

    RESULT['summary'] = {
        'overall': PASS if overall else FAIL,
        'timestamp': __import__('time').strftime('%Y-%m-%d %H:%M:%S')
    }

    # 輸出報告
    out_dir = ROOT / 'results'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'stage1_checklist.json').write_text(json.dumps(RESULT, indent=2, ensure_ascii=False), encoding='utf-8')

    # 人類可讀摘要
    print('\n摘要:')
    for section, items in RESULT.items():
        if section == 'summary':
            continue
        print(f"- {section}:")
        for key, val in items.items():
            print(f"  [{val['status']}] {key} - {val.get('detail','')}")

    print(f"\n總結: {RESULT['summary']['overall']}")
    print(f"結果檔: results/stage1_checklist.json")

    # 非 0 代表未通過，可搭配 CI 使用
    sys.exit(0 if overall else 1)


if __name__ == '__main__':
    main()
