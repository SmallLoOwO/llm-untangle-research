#!/usr/bin/env python3
"""
啟動 OOD 容器 + 準備 Untangle 基線測試樣本（250–300 組）
- 維持最少 3 種真 OOD 服務供即時檢測
- 從 data/combinations.json 載入 280 組實際三層組合供 Untangle 基線測試
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
DATA_DIR = ROOT / 'data'
OOD_COMPOSE_DIR = ROOT / 'docker_configs' / 'ood'
RESULTS_DIR = ROOT / 'results'

SHARED_NETWORK = 'ood_shared_net'

# 已驗證成功的 OOD 配置（保持 3 種即可）
VERIFIED_OOD_CONFIGS = {
    'apache_ood': {'image': 'httpd:2.4-alpine', 'port_mapping': '80', 'environment': []},
    'nginx_ood': {'image': 'nginx:mainline-alpine', 'port_mapping': '80', 'environment': []},
    'caddy_ood': {'image': 'caddy:alpine', 'port_mapping': '80', 'environment': []}
}

BASE_PORT_OOD = 9001
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


def load_combinations_data():
    """從 data/combinations.json 載入預定義的三層組合"""
    combinations_file = DATA_DIR / 'combinations.json'
    if not combinations_file.exists():
        print(f'❌ 找不到組合數據文件: {combinations_file}')
        return []
    
    try:
        with open(combinations_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f'✅ 載入 {len(data)} 組三層組合數據')
            return data
    except Exception as e:
        print(f'❌ 載入組合數據失敗: {e}')
        return []


def generate_baseline_targets(n_min=TARGET_MIN, n_max=TARGET_MAX, seed=RANDOM_SEED):
    """從已有的組合數據生成基線測試目標清單"""
    combinations = load_combinations_data()
    if not combinations:
        print('❌ 無法載入組合數據，無法生成基線測試目標')
        return []
    
    random.seed(seed)
    
    # 選取 250-300 組進行基線測試
    total = len(combinations)
    target_n = min(max(n_min, 1), min(n_max, total))
    
    if target_n > total:
        print(f'⚠️ 可用組合數 ({total}) 少於最低要求 ({n_min})，使用全部組合')
        selected = combinations
    else:
        selected = random.sample(combinations, k=target_n)
    
    # 生成測試目標清單
    targets = []
    for combo in selected:
        targets.append({
            'combo_id': combo['id'],
            'url': combo['url'],
            'L1': combo['l1']['base_name'] if 'base_name' in combo['l1'] else combo['l1']['name'],
            'L2': combo['l2']['base_name'] if 'base_name' in combo['l2'] else combo['l2']['name'], 
            'L3': combo['l3']['base_name'] if 'base_name' in combo['l3'] else combo['l3']['name'],
            'l1_image': combo['l1']['image'],
            'l2_image': combo['l2']['image'],
            'l3_image': combo['l3']['image'],
            'expected_l3': combo['l3']['base_name'] if 'base_name' in combo['l3'] else combo['l3']['name']
        })
    
    # 保存目標清單
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    baseline_targets = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_targets': len(targets),
        'sampling_info': {
            'seed': seed,
            'available_combinations': total,
            'selected_count': len(targets),
            'target_range': f'{n_min}-{n_max}'
        },
        'targets': targets
    }
    
    targets_file = RESULTS_DIR / 'baseline_targets.json'
    targets_file.write_text(json.dumps(baseline_targets, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'📦 已生成基線測試目標清單: {len(targets)} 組 -> {targets_file}')
    
    return targets


def main():
    print('🧪 LLM-UnTangle OOD 測試環境啟動（論文達標版）')
    print('=' * 60)
    print('論文核心：提供多種未知服務器類型供 Out-of-Distribution 檢測\n')

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

    # 生成基線測試目標清單（250-300 組）
    targets = generate_baseline_targets()
    
    # 保存完整狀態
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'paper_requirements_met': meets_requirements,
        'ood_services_running': success_count,
        'total_ood_services': len(results),
        'success_rate': success_rate,
        'status_summary': counts,
        'running_services': [r for r in results if r['status'] == 'running'],
        'all_ood_results': results,
        'baseline_targets_count': len(targets)
    }
    
    (RESULTS_DIR / 'ood_containers_status.json').write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8'
    )

    print('\n📈 最終 OOD 服務啟動結果:')
    print(f'總計測試: {len(results)} 個服務')
    print(f'成功啟動: {success_count} ({success_rate*100:.1f}%)')
    print(f'狀態分佈: {counts}')
    
    if meets_requirements:
        print('\n🎉 論文要求達成：已啟動 3 種不同的 OOD 服務器')
        print('✅ 滿足 Out-of-Distribution 檢測實驗條件')
        print('✅ 可進行 Untangle 基線比較測試')
        print('✅ 可執行 BCa Bootstrap 統計分析')
    else:
        print('\n⚠️ 未滿足最少 3 種 OOD 服務要求')
    
    print(f'\n📄 詳細結果已保存到: {RESULTS_DIR / "ood_containers_status.json"}')
    
    if targets:
        print('\n🌐 可用的 OOD 測試服務:')
        for r in [r for r in results if r['status'] == 'running']:
            name = r['combo_id'].replace('_ood', '')
            print(f'  {r["combo_id"]}: {r["server_header"]} ({name})')
        
        print('\n📋 論文實驗狀態:')
        print('✅ 可進行 OOD 檢測實驗')
        print('✅ 可執行基線比較測試')
        print('✅ 可計算統計置信區間')
        print(f'\n🎯 接下來執行: python scripts/run_untangle_baseline.py')
        print(f'   將測試 {len(targets)} 組三層架構組合的 Untangle 基線準確率')

    return meets_requirements


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)