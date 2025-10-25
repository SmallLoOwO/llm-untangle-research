#!/usr/bin/env python3
"""
多版本 Docker 配置生成器 (方案 A)
為 780 組合創建專用的 Docker Compose 配置檔案

特色：
- 為每個組合生成獨立的 docker-compose.yml
- 包含特定版本的錯誤處理配置
- 支援 CDN 模擬的自訂 Headers
- 自動端口分配與網路連線
"""
import json
import yaml
from pathlib import Path
from typing import Dict, Any

ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / 'data' / 'multi_version_combinations.json'
OUTPUT_DIR = ROOT / 'docker_configs_multi_version'
TEMPLATES_DIR = ROOT / 'docker_configs' / 'templates'


def load_combinations():
    """載入多版本組合數據"""
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f'找不到 {INPUT_PATH}\n'
            f'請先執行: python scripts/generate_multi_version_sets.py'
        )
    return json.loads(INPUT_PATH.read_text(encoding='utf-8'))


def create_l1_cdn_config(l1_server: Dict[str, Any]) -> Dict[str, Any]:
    """為 L1 CDN 模擬層創建 Docker 服務配置"""
    config = {
        'image': l1_server['image'],
        'networks': ['multi-tier'],
        'restart': 'unless-stopped'
    }
    
    # 根據 CDN 類型添加特定配置
    if 'cloudflare' in l1_server['name']:
        config['volumes'] = ['./configs/cloudflare.conf:/etc/nginx/nginx.conf:ro']
        config['environment'] = {
            'CF_RAY_ID': '7f8a9b1c2d3e4f5g-LAX',
            'CF_REQUEST_ID': '0123456789abcdef'
        }
    elif 'cloudfront' in l1_server['name']:
        config['volumes'] = ['./configs/cloudfront.conf:/etc/nginx/nginx.conf:ro']
        config['environment'] = {
            'AMZ_CF_POP': 'LAX1-C1',
            'AMZ_CF_ID': '0123456789ABCDEF'
        }
    elif 'fastly' in l1_server['name']:
        config['image'] = 'varnish:7.4'  # Fastly 使用 Varnish
        config['volumes'] = ['./configs/fastly.vcl:/etc/varnish/default.vcl:ro']
        config['environment'] = {
            'FASTLY_SERVICE_ID': 'abc123def456',
            'FASTLY_DEBUG': 'true'
        }
    elif 'akamai' in l1_server['name']:
        config['volumes'] = ['./configs/akamai.conf:/etc/nginx/nginx.conf:ro']
        config['environment'] = {
            'AKAMAI_REQUEST_ID': 'akamai-123456789',
            'AKAMAI_CACHE_KEY': 'cache-key-example'
        }
    
    return config


def create_l2_proxy_config(l2_server: Dict[str, Any]) -> Dict[str, Any]:
    """為 L2 代理層創建 Docker 服務配置"""
    config = {
        'image': l2_server['image'],
        'networks': ['multi-tier'],
        'restart': 'unless-stopped'
    }
    
    # 根據代理類型和版本添加特定配置
    base_name = l2_server['base_name']
    version = l2_server['version']
    
    if base_name == 'nginx':
        config['volumes'] = [f'./configs/nginx_proxy_{version}.conf:/etc/nginx/nginx.conf:ro']
        # Nginx 版本特定環境變數
        if version == '1.26':
            config['environment'] = {'NGINX_HTTP3': 'true'}
    
    elif base_name == 'varnish':
        config['volumes'] = [f'./configs/varnish_{version}.vcl:/etc/varnish/default.vcl:ro']
        # Varnish 版本特定配置
        if version == '7.4':
            config['environment'] = {'VARNISH_FEATURES': 'enhanced'}
    
    elif base_name == 'haproxy':
        config['volumes'] = [f'./configs/haproxy_{version}.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro']
        # HAProxy 版本特定配置
        if version == '2.8':
            config['environment'] = {'HAPROXY_HTTP2': 'enabled'}
    
    elif base_name == 'traefik':
        config['volumes'] = [f'./configs/traefik_{version}.yml:/etc/traefik/traefik.yml:ro']
        config['ports'] = ['8080:8080']  # Traefik Dashboard
        if version == '3.0':
            config['environment'] = {'TRAEFIK_HTTP3': 'true'}
    
    elif base_name == 'envoy':
        config['volumes'] = [f'./configs/envoy_{version}.yaml:/etc/envoy/envoy.yaml:ro']
        config['ports'] = ['9901:9901']  # Envoy Admin
        
    elif base_name == 'squid':
        config['volumes'] = [f'./configs/squid_{version}.conf:/etc/squid/squid.conf:ro']
        
    elif base_name == 'ats':
        config['volumes'] = [
            f'./configs/ats_{version}_records.config:/usr/local/etc/trafficserver/records.config:ro',
            f'./configs/ats_{version}_remap.config:/usr/local/etc/trafficserver/remap.config:ro'
        ]
    
    return config


def create_l3_server_config(l3_server: Dict[str, Any]) -> Dict[str, Any]:
    """為 L3 後端伺服器層創建 Docker 服務配置"""
    config = {
        'image': l3_server['image'],
        'networks': ['multi-tier'],
        'restart': 'unless-stopped'
    }
    
    base_name = l3_server['base_name']
    version = l3_server['version']
    
    if base_name == 'apache':
        config['volumes'] = [
            f'./configs/apache_{version}.conf:/usr/local/apache2/conf/httpd.conf:ro',
            './html:/usr/local/apache2/htdocs:ro'
        ]
        # Apache 版本特定設定
        if version == '2.4.58':
            config['environment'] = {'APACHE_OPTIMIZED': 'true'}
    
    elif base_name == 'tomcat':
        config['volumes'] = [
            f'./configs/tomcat_{version}_server.xml:/usr/local/tomcat/conf/server.xml:ro',
            './webapps:/usr/local/tomcat/webapps:ro'
        ]
        # Tomcat 版本特定設定
        if version == '10.1':
            config['environment'] = {'JAKARTA_EE': '10'}
        elif version == '9.0':
            config['environment'] = {'JAKARTA_EE': '8'}
    
    elif base_name == 'nginx_backend':
        config['volumes'] = [
            f'./configs/nginx_backend_{version}.conf:/etc/nginx/nginx.conf:ro',
            './html:/usr/share/nginx/html:ro'
        ]
    
    elif base_name == 'caddy':
        config['volumes'] = [
            f'./configs/caddy_{version}.json:/etc/caddy/Caddyfile:ro',
            './html:/srv:ro'
        ]
        # Caddy 版本特定設定
        if version == '2.7':
            config['environment'] = {'CADDY_HTTP3': 'enabled'}
    
    elif base_name == 'openlitespeed':
        config['volumes'] = [
            './configs/openlitespeed.conf:/usr/local/lsws/conf/httpd_config.conf:ro',
            './html:/usr/local/lsws/Example/html:ro'
        ]
        config['ports'] = ['7080:7080']  # OLS Admin Console
    
    return config


def create_docker_compose_file(combination: Dict[str, Any]) -> Dict[str, Any]:
    """為單一組合創建完整的 Docker Compose 檔案"""
    combo_id = combination['id']
    ports = combination['ports']
    
    # 創建三層服務配置
    l1_config = create_l1_cdn_config(combination['l1'])
    l2_config = create_l2_proxy_config(combination['l2'])
    l3_config = create_l3_server_config(combination['l3'])
    
    # 組裝完整的 Docker Compose 檔案
    compose_config = {
        'version': '3.8',
        'services': {
            f'{combo_id}_l1_frontend': {
                **l1_config,
                'container_name': f"{combo_id}_l1_{combination['l1']['name']}",
                'ports': [f"{ports['l1']}:80"],
                'depends_on': [f'{combo_id}_l2_proxy'],
                'environment': {
                    **l1_config.get('environment', {}),
                    'BACKEND_HOST': f"{combo_id}_l2_proxy",
                    'BACKEND_PORT': '80'
                }
            },
            f'{combo_id}_l2_proxy': {
                **l2_config,
                'container_name': f"{combo_id}_l2_{combination['l2']['name']}",
                'ports': [f"{ports['l2']}:80"],
                'depends_on': [f'{combo_id}_l3_server'],
                'environment': {
                    **l2_config.get('environment', {}),
                    'BACKEND_HOST': f"{combo_id}_l3_server",
                    'BACKEND_PORT': '80'
                }
            },
            f'{combo_id}_l3_server': {
                **l3_config,
                'container_name': f"{combo_id}_l3_{combination['l3']['name']}",
                'ports': [f"{ports['l3']}:80"],
                'environment': {
                    **l3_config.get('environment', {}),
                    'SERVER_VERSION': combination['l3']['version']
                }
            }
        },
        'networks': {
            'multi-tier': {
                'driver': 'bridge',
                'ipam': {
                    'config': [{
                        'subnet': f"172.{20 + (int(combo_id.split('_')[1]) % 235)}.0.0/16"
                    }]
                }
            }
        }
    }
    
    # 添加元數據標籤
    compose_config['x-metadata'] = {
        'combination_id': combo_id,
        'combination_key': combination['combination_key'],
        'l1_type': combination['l1']['name'],
        'l2_type': combination['l2']['name'],
        'l3_type': combination['l3']['name'],
        'version_signature': combination['version_signature'],
        'generated_at': '2025-10-25T13:00:00Z'
    }
    
    return compose_config


def create_config_templates():
    """創建各種伺服器的配置檔案範本"""
    templates_dir = OUTPUT_DIR / 'configs'
    templates_dir.mkdir(parents=True, exist_ok=True)
    
    # Cloudflare Nginx 配置範本
    cloudflare_config = '''
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server $BACKEND_HOST:$BACKEND_PORT;
    }

    server {
        listen 80;
        
        location / {
            proxy_pass http://backend;
            
            # Cloudflare 特有 Headers
            add_header CF-Cache-Status "HIT" always;
            add_header CF-RAY "$CF_RAY_ID" always;
            add_header Server "cloudflare" always;
            add_header CF-Request-ID "$CF_REQUEST_ID" always;
            
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Real-IP $remote_addr;
        }
        
        # 自訂錯誤頁面
        error_page 403 /cf_403.html;
        error_page 503 /cf_503.html;
        
        location = /cf_403.html {
            internal;
            return 403 "<html><head><title>Cloudflare</title></head><body><h1>Access Denied</h1><p>Error 403 - Ray ID: $CF_RAY_ID</p></body></html>";
            add_header Content-Type text/html;
        }
    }
}
'''
    
    (templates_dir / 'cloudflare.conf').write_text(cloudflare_config, encoding='utf-8')
    
    # 其他配置檔案範本...
    print(f"\u2713 已創建配置檔案範本於 {templates_dir}")


def generate_all_docker_configs():
    """為所有組合生成 Docker 配置檔案"""
    print('🚀 多版本 Docker 配置生成器')
    print('=' * 50)
    
    # 載入組合數據
    data = load_combinations()
    combinations = data['combinations']
    
    print(f"📁 載入 {len(combinations)} 組合")
    
    # 創建輸出目錄
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 創建配置檔案範本
    create_config_templates()
    
    # 為每個組合生成 Docker Compose 檔案
    generated_count = 0
    testing_count = 0
    
    for combination in combinations:
        combo_id = combination['id']
        compose_config = create_docker_compose_file(combination)
        
        # 儲存 Docker Compose 檔案
        compose_file = OUTPUT_DIR / f"compose_{combo_id}.yml"
        compose_file.write_text(
            yaml.dump(compose_config, default_flow_style=False, allow_unicode=True),
            encoding='utf-8'
        )
        
        generated_count += 1
        if combination['status'] == 'selected_for_testing':
            testing_count += 1
        
        # 顯示進度
        if generated_count % 50 == 0:
            progress = generated_count / len(combinations) * 100
            print(f"[{progress:5.1f}%] 已生成 {generated_count} 個配置檔")
    
    # 創建便捷執行腳本
    create_convenience_scripts(combinations, testing_count)
    
    print(f"\n✅ Docker 配置生成完成！")
    print(f"   總配置數: {generated_count}")
    print(f"   測試配置: {testing_count}")
    print(f"   輸出目錄: {OUTPUT_DIR}")
    
    print(f"\n下一步：")
    print(f"   1. 執行: cd {OUTPUT_DIR}")
    print(f"   2. 啟動單一組合: docker compose -f compose_combo_001.yml up -d")
    print(f"   3. 批次測試: ./start_testing_batch.sh")


def create_convenience_scripts(combinations, testing_count):
    """創建便捷執行腳本"""
    # 測試組合批次啟動腳本
    testing_script = "#!/bin/bash\n\n"
    testing_script += "echo '🚀 啟動所有測試組合...'\n\n"
    
    for combo in combinations:
        if combo['status'] == 'selected_for_testing':
            combo_id = combo['id']
            testing_script += f"echo '啟動 {combo_id}...'\n"
            testing_script += f"docker compose -f compose_{combo_id}.yml up -d\n"
            testing_script += "sleep 2\n\n"
    
    testing_script += f"echo '✅ 已啟動 {testing_count} 個測試組合'\n"
    
    script_file = OUTPUT_DIR / 'start_testing_batch.sh'
    script_file.write_text(testing_script, encoding='utf-8')
    script_file.chmod(0o755)
    
    print(f"\u2713 已創建便捷腳本: {script_file}")


if __name__ == '__main__':
    generate_all_docker_configs()