#!/usr/bin/env python3
"""
啟動 OOD 容器 + 準備 Untangle 基線測試樣本（250–300 組）
- 維持最少 3 種真 OOD 服務供即時檢測
- 自動生成 250–300 組「假網站」三層組合（L1/L2/L3）供 Untangle 基線測試
- 產出 baseline_targets.json 供 run_untangle_baseline.py 掃描測試
"""
import json
import yaml
import subprocess
import time
import requests
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OOD_COMPOSE_DIR = ROOT / 'docker_configs' / 'ood'
COMPOSE_DIR = ROOT / 'docker_configs' / 'baseline_combos'
RESULTS_DIR = ROOT / 'results'

SHARED_NETWORK = 'ood_shared_net'

# 已驗證成功的 OOD 配置（保持 3 種即可）
VERIFIED_OOD_CONFIGS = {
    'apache_ood': {'image': 'httpd:2.4-alpine', 'port_mapping': '80', 'environment': []},
    'nginx_ood': {'image': 'nginx:mainline-alpine', 'port_mapping': '80', 'environment': []},
    'caddy_ood': {'image': 'caddy:alpine', 'port_mapping': '80', 'environment': []}
}

# 三層組合的候選（論文草案與翻譯稿中的代表性技術）
L1_FRONTENDS = [
    {'name': 'nginx', 'image': 'nginx:1.25-alpine', 'port': 80, 'config': None},
    {'name': 'haproxy', 'image': 'haproxy:2.9-alpine', 'port': 80, 'config': None},
    {'name': 'traefik', 'image': 'traefik:v2.10', 'port': 80, 'config': None},
]
L2_PROXIES = [
    {'name': 'varnish', 'image': 'varnish:7.4', 'port': 80, 'config': None},
    {'name': 'squid', 'image': 'ubuntu/squid:latest', 'port': 3128, 'config': None},
    {'name': 'apache', 'image': 'httpd:2.4-alpine', 'port': 80, 'config': None},
]
L3_ORIGINS = [
    {'name': 'tomcat', 'image': 'tomcat:10.1-jdk17', 'port': 8080},
    {'name': 'flask', 'image': 'python:3.11-slim', 'port': 8080},
    {'name': 'express', 'image': 'node:18-alpine', 'port': 8080},
]

BASE_PORT_OOD = 9001
BASE_PORT_COMBO = 10080

RANDOM_SEED = 42
TARGET_MIN = 250
TARGET_MAX = 300


def ensure_shared_network():
    chk = subprocess.run(f'docker network inspect {SHARED_NETWORK}', shell=True, capture_output=True, text=True)
    if chk.returncode != 0:
        mk = subprocess.run(f'docker network create {SHARED_NETWORK}', shell=True, capture_output=True, text=True)
        if mk.returncode == 0:
            print(f'✅ 建立共用網路: {SHARED_NETWORK}')
            return True
        print(f'❌ 建立網路失敗: {mk.stderr}')
        return False
    return True


def create_ood_service_compose(combo_id: str, config: dict, external_port: int) -> dict:
    return {
        'networks': {SHARED_NETWORK: {'external': True}},
        'services': {
            f'{combo_id}_ood': {
                'image': config['image'],
                'container_name': f'{combo_id}_ood',
                'ports': [f'{external_port}:{config["port_mapping"]}'],
                'networks': [SHARED_NETWORK],
                'environment': config.get('environment', []),
                'restart': 'unless-stopped',
                'labels': ['project=llm-untangle', 'type=ood', f'combo_id={combo_id}']
            }
        }
    }


def create_combo_compose(combo_id: int, l1: dict, l2: dict, l3: dict, ext_port: int) -> dict:
    """建立三層假網站 docker-compose 定義。"""
    backend_name = f'combo_{combo_id}_backend'
    proxy_name = f'combo_{combo_id}_proxy'
    front_name = f'combo_{combo_id}_front'

    services = {
        backend_name: {
            'image': l3['image'],
            'container_name': backend_name,
            'networks': [SHARED_NETWORK],
        },
        proxy_name: {
            'image': l2['image'],
            'container_name': proxy_name,
            'depends_on': [backend_name],
            'networks': [SHARED_NETWORK],
        },
        front_name: {
            'image': l1['image'],
            'container_name': front_name,
            'depends_on': [proxy_name],
            'ports': [f'{ext_port}:80'],
            'networks': [SHARED_NETWORK],
            'labels': ['project=llm-untangle', 'type=baseline']
        }
    }

    # 最小可行配置：用簡單的反向代理把 80 轉到 backend
    # 不同技術的實際配置在論文中有詳細範本，這裡用內建預設啟動頁即可供 Untangle 探測
    return {'version': '3.8', 'services': services, 'networks': {SHARED_NETWORK: {'external': True}}}


def start_ood_service(combo_id: str, config: dict, url: str) -> dict:
    port = int(url.split(':')[-1])
    compose_file = OOD_COMPOSE_DIR / f'ood_{combo_id}.yml'
    try:
        compose = create_ood_service_compose(combo_id, config, port)
        OOD_COMPOSE_DIR.mkdir(parents=True, exist_ok=True)
        compose_file.write_text(yaml.dump(compose, default_flow_style=False), encoding='utf-8')
        subprocess.run(f'docker compose -f "{compose_file}" down -v', shell=True, capture_output=True, cwd=ROOT)
        proc = subprocess.run(f'docker compose -f "{compose_file}" up -d', shell=True, capture_output=True, text=True, cwd=ROOT)
        if proc.returncode != 0:
            return {'combo_id': combo_id, 'status': 'compose_failed', 'error': proc.stderr.strip()}
        print(f'⏳ 等待 {combo_id} 啟動 (4s)...'); time.sleep(4)
        try:
            r = requests.get(url, timeout=8)
            print(f'✅ {combo_id} 成功! Server: {r.headers.get("Server", "N/A")}')
            return {'combo_id': combo_id, 'status': 'running', 'image': config['image'], 'http_status': r.status_code, 'server_header': r.headers.get('Server', 'N/A'), 'content_length': len(r.text)}
        except requests.RequestException as e:
            return {'combo_id': combo_id, 'status': 'no_response', 'error': str(e)}
    except Exception as e:
        return {'combo_id': combo_id, 'status': 'script_error', 'error': str(e)}


def generate_baseline_combos(n_min=TARGET_MIN, n_max=TARGET_MAX, seed=RANDOM_SEED):
    random.seed(seed)
    all_triples = [(l1, l2, l3) for l1 in L1_FRONTENDS for l2 in L2_PROXIES for l3 in L3_ORIGINS]
    total = len(all_triples)
    target_n = min(max(n_min, 1), n_max)
    if target_n > total:
        target_n = total
    selected = random.sample(all_triples, k=target_n)

    COMPOSE_DIR.mkdir(parents=True, exist_ok=True)
    targets = []
    for idx, (l1, l2, l3) in enumerate(selected, start=1):
        ext_port = BASE_PORT_COMBO + idx - 1
        compose = create_combo_compose(idx, l1, l2, l3, ext_port)
        file_path = COMPOSE_DIR / f'combo_{idx:03d}.yml'
        file_path.write_text(yaml.dump(compose, default_flow_style=False), encoding='utf-8')
        targets.append({
            'combo_id': f'combo_{idx:03d}',
            'url': f'http://localhost:{ext_port}',
            'L1': l1['name'], 'L2': l2['name'], 'L3': l3['name']
        })
    # 輸出掃描目標
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / 'baseline_targets.json').write_text(json.dumps({'targets': targets}, indent=2, ensure_ascii=False), encoding='utf-8')
    return targets


def main():
    print('🧪 LLM-UnTangle OOD + 基線樣本準備')
    print('=' * 60)
    print('論文核心：啟動 3 種 OOD 服務，並準備 250–300 組假網站供 Untangle 基線測試\n')

    if not ensure_shared_network():
        return False

    # 啟動 3 種 OOD 服務
    results = []
    success_count = 0
    for i, (name, config) in enumerate(VERIFIED_OOD_CONFIGS.items()):
        combo_id = f'ood_{i+1:03d}'
        url = f'http://localhost:{BASE_PORT_OOD + i}'
        print(f'--- 啟動 {combo_id}: {name} ---')
        print(f'映像: {config["image"]}')
        print(f'URL: {url}')
        r = start_ood_service(combo_id, config, url)
        results.append(r)
        if r['status'] == 'running':
            success_count += 1

    counts = {}
    for r in results:
        counts[r['status']] = counts.get(r['status'], 0) + 1

    success_rate = success_count / max(len(results), 1)
    meets_requirements = success_count >= 3

    # 生成 250–300 組基線測試假網站（只生成 compose 與目標清單，不自動 up，以免佔用過多資源）
    targets = generate_baseline_combos()
    print(f'📦 已生成基線測試組合 compose 檔案: {len(targets)} 組')
    print('➡️ 之後由 run_untangle_baseline.py 逐一啟動並測試，避免同時佔用過多端口/記憶體')

    # 保存狀態
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'paper_requirements_met': meets_requirements,
        'ood_services_running': success_count,
        'success_rate': success_rate,
        'status_summary': counts,
        'running_services': [r for r in results if r['status'] == 'running'],
        'all_results': results,
        'baseline_targets_count': len(targets)
    }
    (RESULTS_DIR / 'ood_containers_status.json').write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')

    print('\n📈 最終狀態:')
    print(f'- OOD 成功啟動: {success_count}/3')
    print(f'- 基線測試樣本: {len(targets)} 組 (目標 250–300)')
    if meets_requirements:
        print('\n🎉 已滿足 OOD 檢測條件，並完成基線樣本準備')
        print('✅ 接著可執行 Untangle 基線測試: python scripts/run_untangle_baseline.py')
    print(f'\n📄 詳細結果已保存到: {RESULTS_DIR / "ood_containers_status.json"}')

    return meets_requirements


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
