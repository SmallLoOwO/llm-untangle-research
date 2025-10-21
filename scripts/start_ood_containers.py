#!/usr/bin/env python3
"""
OOD 容器三層鏈路啟動與驗證（完全重構版）
- 建立 Docker 自訂網路確保容器間通信
- 生成 NGINX 配置模板建立 L1->L2->L3 反向代理鏈
- 統一應用伺服器埠為 8080，確保 upstream 連接成功
- 順序啟動並驗證每層健康狀態
"""
import json
import yaml
import subprocess
import time
import requests
from pathlib import Path
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
OOD_PATH = ROOT / 'data' / 'ood' / 'ood_combinations.json'
OOD_COMPOSE_DIR = ROOT / 'docker_configs' / 'ood'
TEMPLATES_DIR = ROOT / 'docker_configs' / 'templates'
RESULTS_DIR = ROOT / 'results'

def load_ood_combinations():
    if not OOD_PATH.exists():
        raise FileNotFoundError(f'找不到 {OOD_PATH}，請先執行 prepare_datasets.py')
    return json.loads(OOD_PATH.read_text(encoding='utf-8'))

def generate_nginx_config(combo_id, template_name):
    """生成 NGINX 配置檔案"""
    template_path = TEMPLATES_DIR / f'{template_name}.template'
    if not template_path.exists():
        raise FileNotFoundError(f'找不到模板: {template_path}')
    
    template_content = template_path.read_text(encoding='utf-8')
    config_content = template_content.replace('{COMBO_ID}', combo_id)
    
    config_dir = OOD_COMPOSE_DIR / combo_id / 'configs'
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / f'{template_name}.conf'
    config_path.write_text(config_content, encoding='utf-8')
    
    return config_path

def create_ood_compose_file(combo):
    combo_id = combo['id']
    port = int(combo['url'].split(':')[-1])
    
    # 生成配置檔案
    l1_config = generate_nginx_config(combo_id, 'ood_nginx_l1')
    l2_config = generate_nginx_config(combo_id, 'ood_nginx_l2')
    
    # 標準化 L3 應用伺服器埠配置
    l3_image = combo['l3']['image']
    l3_ports = ['8080:8080']  # 統一內外部都使用 8080
    l3_environment = []
    
    # 根據不同應用伺服器調整配置
    if 'tomcat' in l3_image:
        l3_environment = ['CATALINA_OPTS=-Dfile.encoding=UTF-8']
    elif 'jetty' in l3_image:
        l3_environment = ['JETTY_HOME=/usr/local/jetty']
    elif 'httpd' in l3_image or 'apache' in l3_image:
        l3_ports = ['8080:80']  # Apache 預設監聽 80，映射到 8080
    elif 'nginx' in l3_image:
        l3_ports = ['8080:80']  # NGINX 預設監聽 80
    
    compose_content = {
        'version': '3.8',
        'networks': {
            f'{combo_id}_net': {
                'driver': 'bridge'
            }
        },
        'services': {
            f'{combo_id}_l3': {
                'image': l3_image,
                'container_name': f"{combo_id}_l3",
                'ports': l3_ports,
                'environment': l3_environment,
                'networks': [f'{combo_id}_net'],
                'restart': 'unless-stopped',
                'labels': ['ood=true', 'layer=l3', f'combo_id={combo_id}'],
                'healthcheck': {
                    'test': ['CMD', 'curl', '-f', 'http://localhost:8080/', '||', 'exit', '1'],
                    'interval': '30s',
                    'timeout': '10s',
                    'retries': 3
                }
            },
            f'{combo_id}_l2': {
                'image': 'nginx:alpine',  # 統一使用 NGINX 作為 L2 反向代理
                'container_name': f"{combo_id}_l2",
                'ports': ['8080:8080'],
                'volumes': [f'{l2_config.relative_to(ROOT)}:/etc/nginx/nginx.conf:ro'],
                'networks': [f'{combo_id}_net'],
                'depends_on': [f'{combo_id}_l3'],
                'restart': 'unless-stopped',
                'labels': ['ood=true', 'layer=l2', f'combo_id={combo_id}']
            },
            f'{combo_id}_l1': {
                'image': 'nginx:alpine',  # 統一使用 NGINX 作為 L1 CDN 模擬
                'container_name': f"{combo_id}_l1",
                'ports': [f'{port}:80'],
                'volumes': [f'{l1_config.relative_to(ROOT)}:/etc/nginx/nginx.conf:ro'],
                'networks': [f'{combo_id}_net'],
                'depends_on': [f'{combo_id}_l2'],
                'restart': 'unless-stopped',
                'labels': ['ood=true', 'layer=l1', f'combo_id={combo_id}']
            }
        }
    }
    return compose_content

def start_ood_container(combo):
    combo_id = combo['id']
    compose_file = OOD_COMPOSE_DIR / f'compose_{combo_id}.yml'
    
    try:
        # 生成 compose 檔案
        compose_content = create_ood_compose_file(combo)
        OOD_COMPOSE_DIR.mkdir(parents=True, exist_ok=True)
        compose_file.write_text(yaml.dump(compose_content, default_flow_style=False), encoding='utf-8')
        
        # 啟動容器
        cmd = f'docker compose -f "{compose_file}" up -d'
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=ROOT)
        if proc.returncode != 0:
            return {'combo_id': combo_id, 'status': 'failed', 'error': f'compose_up: {proc.stderr.strip()}'}
        
        # 等待服務就緒
        time.sleep(8)
        
        # 驗證三層鏈路
        try:
            response = requests.get(combo['url'], timeout=10)
            if response.status_code != 200:
                return {'combo_id': combo_id, 'status': 'http_error', 'error': f'HTTP {response.status_code}'}
                
            return {
                'combo_id': combo_id,
                'status': 'running',
                'http_status': response.status_code,
                'response_size': len(response.text),
                'headers_count': len(response.headers),
                'server_header': response.headers.get('Server', 'N/A')
            }
        except requests.RequestException as e:
            return {'combo_id': combo_id, 'status': 'no_response', 'error': str(e)}
            
    except Exception as e:
        return {'combo_id': combo_id, 'status': 'error', 'error': str(e)}

def verify_ood_containers():
    print('🧪 OOD 容器三層鏈路啟動（重構版）')
    print('=' * 50)
    
    combos = load_ood_combinations()
    print(f'載入 {len(combos)} 個 OOD 組合')
    
    results = []
    # 順序啟動，避免資源競爭
    for combo in tqdm(combos, desc='啟動 OOD 三層鏈路'):
        result = start_ood_container(combo)
        results.append(result)
        
        # 短暫休息避免 Docker 過載
        time.sleep(1)
    
    # 統計結果
    status_counts = {}
    for r in results:
        status = r['status']
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print(f'\n容器狀態統計：')
    for status, count in status_counts.items():
        print(f'  {status}: {count}')
    
    # 顯示失敗案例的錯誤類型
    failed_errors = {}
    for r in results:
        if r['status'] != 'running':
            error_type = r.get('error', 'unknown')[:50]  # 前50字符
            failed_errors[error_type] = failed_errors.get(error_type, 0) + 1
    
    if failed_errors:
        print('\n主要失敗原因：')
        for error, count in sorted(failed_errors.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f'  {error}: {count} 次')
    
    # 保存結果
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_ood_combinations': len(combos),
        'status_summary': status_counts,
        'failed_error_types': failed_errors,
        'details': results
    }
    
    output_path = RESULTS_DIR / 'ood_containers_status.json'
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    
    success_rate = status_counts.get('running', 0) / len(results)
    print(f'\n✓ 驗證完成，結果已保存到 {output_path}')
    print(f'OOD 容器成功率：{success_rate:.1%}')
    
    return success_rate >= 0.8

def main():
    success = verify_ood_containers()
    exit(0 if success else 1)

if __name__ == '__main__':
    main()