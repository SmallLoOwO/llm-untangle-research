#!/usr/bin/env python3
"""
修正：
- start_ood_containers.py 成功率過低：
  1) 將 L1/L2/L3 連接埠映射到實際服務埠；
  2) 啟動後重試探測（退避機制）；
  3) 並行度限制、錯誤訊息更清晰。

- run_untangle_baseline.py 準確率為 0：
  1) 使用容器內迴圈（同一組合的 3 層串接）來取得標頭；
  2) 以 docker inspect 解析映像類型輔助識別；
  3) 保存全量詳細結果供 BCa 使用。

- calculate_bca_confidence.py 基線不完整：
  1) 讀取 detailed_results 改為讀取全部樣本（不再截斷）。
"""
import json
import yaml
import subprocess
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
OOD_PATH = ROOT / 'data' / 'ood' / 'ood_combinations.json'
OOD_COMPOSE_DIR = ROOT / 'docker_configs' / 'ood'
RESULTS_DIR = ROOT / 'results'

MAX_RETRIES = 5
RETRY_BACKOFF = 2  # seconds
MAX_WORKERS = 2    # 降低併發以提升穩定度


def load_ood_combinations():
    if not OOD_PATH.exists():
        raise FileNotFoundError(f'找不到 {OOD_PATH}，請先執行 prepare_datasets.py')
    return json.loads(OOD_PATH.read_text(encoding='utf-8'))


def create_ood_compose_file(combo):
    combo_id = combo['id']
    port = int(combo['url'].split(':')[-1])

    compose_content = {
        'version': '3.8',
        'services': {
            f'{combo_id}_l3': {
                'image': combo['l3']['image'],
                'container_name': f"{combo_id}_l3_{combo['l3']['name']}",
                'ports': [f'{port+2}:80'],  # L3: 外部 port+2 -> 容器 80
                'restart': 'unless-stopped',
                'labels': ['ood=true', 'layer=l3', f'combo_id={combo_id}']
            },
            f'{combo_id}_l2': {
                'image': combo['l2']['image'],
                'container_name': f"{combo_id}_l2_{combo['l2']['name']}",
                'ports': [f'{port+1}:80'],  # L2: 外部 port+1
                'restart': 'unless-stopped',
                'depends_on': [f'{combo_id}_l3'],
                'labels': ['ood=true', 'layer=l2', f'combo_id={combo_id}']
            },
            f'{combo_id}_l1': {
                'image': combo['l1']['image'],
                'container_name': f"{combo_id}_l1_{combo['l1']['name']}",
                'ports': [f'{port}:80'],    # L1: 外部 port
                'restart': 'unless-stopped',
                'depends_on': [f'{combo_id}_l2'],
                'labels': ['ood=true', 'layer=l1', f'combo_id={combo_id}']
            }
        }
    }
    return compose_content


def http_probe(url: str):
    for i in range(1, MAX_RETRIES+1):
        try:
            resp = requests.get(url, timeout=5)
            return {'ok': True, 'code': resp.status_code, 'headers': dict(resp.headers), 'len': len(resp.text)}
        except Exception as e:
            time.sleep(RETRY_BACKOFF * i)
            last = str(e)
    return {'ok': False, 'error': last}


def start_ood_container(combo):
    combo_id = combo['id']
    compose_file = OOD_COMPOSE_DIR / f'compose_{combo_id}.yml'
    try:
        compose = create_ood_compose_file(combo)
        OOD_COMPOSE_DIR.mkdir(parents=True, exist_ok=True)
        compose_file.write_text(yaml.dump(compose, default_flow_style=False), encoding='utf-8')

        cmd = f'docker compose -f "{compose_file}" up -d'
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=ROOT)
        if proc.returncode != 0:
            return {'combo_id': combo_id, 'status': 'failed', 'error': proc.stderr.strip()}

        # 等待並重試探測 L1 對外 URL
        probe = http_probe(combo['url'])
        if not probe['ok']:
            return {'combo_id': combo_id, 'status': 'no_response', 'error': probe.get('error','timeout')}

        return {
            'combo_id': combo_id,
            'status': 'running',
            'http_status': probe['code'],
            'response_size': probe['len'],
            'headers_count': len(probe['headers'])
        }
    except Exception as e:
        return {'combo_id': combo_id, 'status': 'error', 'error': str(e)}


def verify_ood_containers():
    print('🧪 OOD 容器啟動與驗證（強化版）')
    print('=' * 40)
    combos = load_ood_combinations()
    print(f'載入 {len(combos)} 個 OOD 組合')

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(start_ood_container, c): c for c in combos}
        for fut in as_completed(futures):
            results.append(fut.result())

    # 統計
    status_counts = {}
    for r in results:
        status_counts[r['status']] = status_counts.get(r['status'], 0) + 1

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_ood_combinations': len(combos),
        'status_summary': status_counts,
        'details': results
    }
    (RESULTS_DIR / 'ood_containers_status.json').write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

    print('\n容器狀態統計：')
    for k,v in status_counts.items():
        print(f'  {k}: {v}')
    success_rate = status_counts.get('running', 0) / max(1,len(results))
    print(f"\nOOD 容器成功率：{success_rate:.1%}")
    return success_rate >= 0.8

if __name__ == '__main__':
    ok = verify_ood_containers()
    raise SystemExit(0 if ok else 1)
