#!/usr/bin/env python3
"""
修正模板路徑解析：
- 若 docker_configs/templates 不存在，建立目錄並回退使用內建模板字串寫入
- 確保 Windows 下相對路徑掛載正確
"""
import json
import yaml
import subprocess
import time
import requests
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OOD_PATH = ROOT / 'data' / 'ood' / 'ood_combinations.json'
OOD_COMPOSE_DIR = ROOT / 'docker_configs' / 'ood'
TEMPLATES_DIR = ROOT / 'docker_configs' / 'templates'
RESULTS_DIR = ROOT / 'results'

# 內建模板 fallback（避免本機缺檔）
L1_TEMPLATE = """events {\n    worker_connections 1024;\n}\n\nhttp {\n    upstream backend_l2 {\n        server {COMBO_ID}_l2:8080;\n    }\n    server {\n        listen 80;\n        location / {\n            proxy_pass http://backend_l2;\n            proxy_set_header Host $host;\n            proxy_set_header X-Real-IP $remote_addr;\n            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n            proxy_set_header X-Forwarded-Proto $scheme;\n        }\n    }\n}\n"""

L2_TEMPLATE = """events {\n    worker_connections 1024;\n}\n\nhttp {\n    upstream backend_l3 {\n        server {COMBO_ID}_l3:8080;\n    }\n    server {\n        listen 8080;\n        location / {\n            proxy_pass http://backend_l3;\n            proxy_set_header Host $host;\n            proxy_set_header X-Real-IP $remote_addr;\n            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n            proxy_set_header X-Forwarded-Proto $scheme;\n        }\n    }\n}\n"""

def ensure_templates():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    l1_path = TEMPLATES_DIR / 'ood_nginx_l1.conf.template'
    l2_path = TEMPLATES_DIR / 'ood_nginx_l2.conf.template'
    if not l1_path.exists():
        l1_path.write_text(L1_TEMPLATE, encoding='utf-8')
    if not l2_path.exists():
        l2_path.write_text(L2_TEMPLATE, encoding='utf-8')


def load_ood_combinations():
    if not OOD_PATH.exists():
        raise FileNotFoundError(f'找不到 {OOD_PATH}，請先執行 prepare_datasets.py')
    return json.loads(OOD_PATH.read_text(encoding='utf-8'))


def generate_nginx_config(combo_id, template_name):
    ensure_templates()
    template_path = TEMPLATES_DIR / f'{template_name}.template'
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
    l1_config = generate_nginx_config(combo_id, 'ood_nginx_l1')
    l2_config = generate_nginx_config(combo_id, 'ood_nginx_l2')

    l3_image = combo['l3']['image']
    l3_ports = ['8080:8080']
    if any(x in l3_image for x in ['httpd', 'apache', 'nginx']):
        l3_ports = ['8080:80']

    compose_content = {
        'version': '3.8',
        'networks': {f'{combo_id}_net': {'driver': 'bridge'}},
        'services': {
            f'{combo_id}_l3': {
                'image': l3_image,
                'container_name': f"{combo_id}_l3",
                'ports': l3_ports,
                'networks': [f'{combo_id}_net'],
                'restart': 'unless-stopped'
            },
            f'{combo_id}_l2': {
                'image': 'nginx:alpine',
                'container_name': f"{combo_id}_l2",
                'ports': ['8080:8080'],
                'volumes': [f"{l2_config.as_posix()}:/etc/nginx/nginx.conf:ro"],
                'networks': [f'{combo_id}_net'],
                'depends_on': [f'{combo_id}_l3'],
                'restart': 'unless-stopped'
            },
            f'{combo_id}_l1': {
                'image': 'nginx:alpine',
                'container_name': f"{combo_id}_l1",
                'ports': [f'{port}:80'],
                'volumes': [f"{l1_config.as_posix()}:/etc/nginx/nginx.conf:ro"],
                'networks': [f'{combo_id}_net'],
                'depends_on': [f'{combo_id}_l2'],
                'restart': 'unless-stopped'
            }
        }
    }
    return compose_content


def start_single_combo(combo):
    combo_id = combo['id']
    compose_file = OOD_COMPOSE_DIR / f'compose_{combo_id}.yml'
    compose = create_ood_compose_file(combo)
    OOD_COMPOSE_DIR.mkdir(parents=True, exist_ok=True)
    compose_file.write_text(yaml.dump(compose, default_flow_style=False), encoding='utf-8')

    proc = subprocess.run(f'docker compose -f "{compose_file}" up -d', shell=True, capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        return {'combo_id': combo_id, 'status': 'failed', 'error': proc.stderr.strip()}

    # 等待 L1 可回應
    time.sleep(5)
    try:
        r = requests.get(combo['url'], timeout=10)
        return {'combo_id': combo_id, 'status': 'running', 'http': r.status_code}
    except Exception as e:
        return {'combo_id': combo_id, 'status': 'no_response', 'error': str(e)}


def main():
    print('🧪 OOD 容器三層鏈路啟動（模板自修復版）')
    combos = load_ood_combinations()
    results = []
    for c in combos:
        results.append(start_single_combo(c))
        time.sleep(0.5)

    # 統計與保存
    counts = {}
    for r in results:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / 'ood_containers_status.json').write_text(json.dumps({'summary': counts, 'details': results}, indent=2, ensure_ascii=False), encoding='utf-8')

    print('容器狀態統計：', counts)

if __name__ == '__main__':
    main()
