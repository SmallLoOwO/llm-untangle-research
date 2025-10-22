#!/usr/bin/env python3
"""
OOD 容器三層鏈路啟動（模板自修復版，修正檔名與路徑）
- 自動建立 docker_configs/templates 與模板檔
- 正確讀取 ood_nginx_l1.conf.template / ood_nginx_l2.conf.template
- L1:80 -> L2:8080 -> L3:8080（Apache/NGINX 80 轉 8080）
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

# 內建模板（避免缺檔）
L1_TEMPLATE = """events { worker_connections 1024; }
http {
  upstream backend_l2 { server {COMBO_ID}_l2:8080; }
  server {
    listen 80;
    location / {
      proxy_pass http://backend_l2;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
    }
  }
}
"""

L2_TEMPLATE = """events { worker_connections 1024; }
http {
  upstream backend_l3 { server {COMBO_ID}_l3:8080; }
  server {
    listen 8080;
    location / {
      proxy_pass http://backend_l3;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
    }
  }
}
"""

def ensure_templates():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    l1 = TEMPLATES_DIR / 'ood_nginx_l1.conf.template'
    l2 = TEMPLATES_DIR / 'ood_nginx_l2.conf.template'
    if not l1.exists():
        l1.write_text(L1_TEMPLATE, encoding='utf-8')
    if not l2.exists():
        l2.write_text(L2_TEMPLATE, encoding='utf-8')

def load_ood_combinations():
    if not OOD_PATH.exists():
        raise FileNotFoundError(f'找不到 {OOD_PATH}，請先執行 prepare_datasets.py')
    return json.loads(OOD_PATH.read_text(encoding='utf-8'))

def generate_nginx_config(combo_id: str, template_basename: str) -> Path:
    """
    template_basename 需傳 'ood_nginx_l1' 或 'ood_nginx_l2'
    會讀取 docker_configs/templates/{basename}.conf.template
    """
    ensure_templates()
    template_path = TEMPLATES_DIR / f'{template_basename}.conf.template'
    content = template_path.read_text(encoding='utf-8').replace('{COMBO_ID}', combo_id)
    cfg_dir = OOD_COMPOSE_DIR / combo_id / 'configs'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    out_path = cfg_dir / f'{template_basename}.conf'
    out_path.write_text(content, encoding='utf-8')
    return out_path

def create_ood_compose_file(combo: dict) -> dict:
    combo_id = combo['id']
    port = int(combo['url'].split(':')[-1])

    l1_cfg = generate_nginx_config(combo_id, 'ood_nginx_l1')
    l2_cfg = generate_nginx_config(combo_id, 'ood_nginx_l2')

    l3_image = combo['l3']['image']
    # L3 對內統一 8080，若基底是 httpd/nginx 則對外映射 80 -> 8080
    l3_ports = ['8080:8080']
    if any(x in l3_image for x in ['httpd', 'apache', 'nginx']):
        l3_ports = ['8080:80']

    return {
        'version': '3.8',
        'networks': {f'{combo_id}_net': {'driver': 'bridge'}},
        'services': {
            f'{combo_id}_l3': {
                'image': l3_image,
                'container_name': f'{combo_id}_l3',
                'ports': l3_ports,
                'networks': [f'{combo_id}_net'],
                'restart': 'unless-stopped'
            },
            f'{combo_id}_l2': {
                'image': 'nginx:alpine',
                'container_name': f'{combo_id}_l2',
                'ports': ['8080:8080'],
                'volumes': [f'{l2_cfg.as_posix()}:/etc/nginx/nginx.conf:ro'],
                'networks': [f'{combo_id}_net'],
                'depends_on': [f'{combo_id}_l3'],
                'restart': 'unless-stopped'
            },
            f'{combo_id}_l1': {
                'image': 'nginx:alpine',
                'container_name': f'{combo_id}_l1',
                'ports': [f'{port}:80'],
                'volumes': [f'{l1_cfg.as_posix()}:/etc/nginx/nginx.conf:ro'],
                'networks': [f'{combo_id}_net'],
                'depends_on': [f'{combo_id}_l2'],
                'restart': 'unless-stopped'
            }
        }
    }

def start_single_combo(combo: dict) -> dict:
    combo_id = combo['id']
    compose_file = OOD_COMPOSE_DIR / f'compose_{combo_id}.yml'
    compose = create_ood_compose_file(combo)
    OOD_COMPOSE_DIR.mkdir(parents=True, exist_ok=True)
    compose_file.write_text(yaml.dump(compose, default_flow_style=False), encoding='utf-8')

    # 在專案根啟動，確保相對路徑掛載正確
    proc = subprocess.run(
        f'docker compose -f "{compose_file.as_posix()}" up -d',
        shell=True, capture_output=True, text=True, cwd=ROOT
    )
    if proc.returncode != 0:
        return {'combo_id': combo_id, 'status': 'failed', 'error': proc.stderr.strip()}

    time.sleep(5)
    try:
        r = requests.get(combo['url'], timeout=10)
        return {'combo_id': combo_id, 'status': 'running', 'http': r.status_code}
    except Exception as e:
        return {'combo_id': combo_id, 'status': 'no_response', 'error': str(e)}

def main():
    print('🧪 OOD 容器三層鏈路啟動（模板自修復版，修正檔名）')
    combos = load_ood_combinations()
    results = []
    for c in combos:
        results.append(start_single_combo(c))
        time.sleep(0.3)

    # 統計與保存
    counts = {}
    for r in results:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / 'ood_containers_status.json').write_text(
        json.dumps({'summary': counts, 'details': results}, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    print('容器狀態統計：', counts)

if __name__ == '__main__':
    main()
