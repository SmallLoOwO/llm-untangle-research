#!/usr/bin/env python3
"""
啟動並驗證 OOD (Out-of-Distribution) 容器
- 從 data/ood/ood_combinations.json 載入 OOD 測試集
- 為每個 OOD 組合生成並啟動 Docker Compose 容器
- 驗證容器狀態與 HTTP 回應
- 輸出驗證結果到 results/ood_containers_status.json
"""
import json
import yaml
import subprocess
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
OOD_PATH = ROOT / 'data' / 'ood' / 'ood_combinations.json'
OOD_COMPOSE_DIR = ROOT / 'docker_configs' / 'ood'
RESULTS_DIR = ROOT / 'results'


def load_ood_combinations():
    if not OOD_PATH.exists():
        raise FileNotFoundError(f'找不到 {OOD_PATH}，請先執行 prepare_datasets.py')
    return json.loads(OOD_PATH.read_text(encoding='utf-8'))


def create_ood_compose_file(combo):
    """為 OOD 組合創建 Docker Compose 檔案"""
    combo_id = combo['id']
    # 從 URL 提取 port
    port = int(combo['url'].split(':')[-1])
    
    compose_content = {
        'version': '3.8',
        'services': {
            f'{combo_id}_l3': {
                'image': combo['l3']['image'],
                'container_name': f"{combo_id}_l3_{combo['l3']['name']}",
                'ports': [f'{port + 2000}:80'],
                'restart': 'unless-stopped',
                'labels': ['ood=true', f'layer=l3', f'combo_id={combo_id}']
            },
            f'{combo_id}_l2': {
                'image': combo['l2']['image'],
                'container_name': f"{combo_id}_l2_{combo['l2']['name']}",
                'ports': [f'{port + 1000}:80'],
                'restart': 'unless-stopped',
                'depends_on': [f'{combo_id}_l3'],
                'labels': ['ood=true', f'layer=l2', f'combo_id={combo_id}']
            },
            f'{combo_id}_l1': {
                'image': combo['l1']['image'],
                'container_name': f"{combo_id}_l1_{combo['l1']['name']}",
                'ports': [f'{port}:80'],
                'restart': 'unless-stopped',
                'depends_on': [f'{combo_id}_l2'],
                'labels': ['ood=true', f'layer=l1', f'combo_id={combo_id}']
            }
        }
    }
    return compose_content


def start_ood_container(combo):
    """啟動單個 OOD 組合的容器"""
    combo_id = combo['id']
    compose_file = OOD_COMPOSE_DIR / f'compose_{combo_id}.yml'
    
    try:
        # 生成 compose 檔案
        compose_content = create_ood_compose_file(combo)
        compose_file.write_text(yaml.dump(compose_content, default_flow_style=False), encoding='utf-8')
        
        # 啟動容器
        cmd = f'docker compose -f {compose_file} up -d'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=ROOT)
        
        if result.returncode != 0:
            return {'combo_id': combo_id, 'status': 'failed', 'error': result.stderr}
        
        # 等待容器啟動
        time.sleep(3)
        
        # 驗證 HTTP 回應
        try:
            response = requests.get(combo['url'], timeout=5)
            return {
                'combo_id': combo_id,
                'status': 'running',
                'http_status': response.status_code,
                'response_size': len(response.text),
                'headers_count': len(response.headers)
            }
        except Exception as e:
            return {'combo_id': combo_id, 'status': 'no_response', 'error': str(e)}
            
    except Exception as e:
        return {'combo_id': combo_id, 'status': 'error', 'error': str(e)}


def verify_ood_containers():
    """驗證所有 OOD 容器狀態"""
    print('🧪 OOD 容器啟動與驗證')
    print('=' * 40)
    
    # 建立 OOD compose 目錄
    OOD_COMPOSE_DIR.mkdir(parents=True, exist_ok=True)
    
    # 載入 OOD 組合
    ood_combinations = load_ood_combinations()
    print(f'載入 {len(ood_combinations)} 個 OOD 組合')
    
    results = []
    
    # 使用多執行緒啟動容器（限制併發數避免資源耗盡）
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(start_ood_container, combo): combo for combo in ood_combinations}
        
        for future in tqdm(as_completed(futures), total=len(futures), desc='啟動 OOD 容器'):
            result = future.result()
            results.append(result)
    
    # 統計結果
    status_counts = {}
    for r in results:
        status = r['status']
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print(f'\n容器狀態統計：')
    for status, count in status_counts.items():
        print(f'  {status}: {count}')
    
    # 保存結果
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_ood_combinations': len(ood_combinations),
        'status_summary': status_counts,
        'details': results
    }
    
    output_path = RESULTS_DIR / 'ood_containers_status.json'
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    
    print(f'\n✓ 驗證完成，結果已保存到 {output_path}')
    
    # 成功率
    success_rate = status_counts.get('running', 0) / len(results)
    print(f'OOD 容器成功率：{success_rate:.1%}')
    
    return success_rate >= 0.8  # 80% 成功率為合格


def main():
    success = verify_ood_containers()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()