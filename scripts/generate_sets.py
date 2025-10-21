#!/usr/bin/env python3
"""
生成 250-300 組三層架構組合，輸出到 data/combinations.json
修復版：包含錯誤處理和路徑調整
"""
import yaml
import itertools
import random
import json
import os
from pathlib import Path

def load_server_configs(config_file="configs/server_configs.yaml"):
    # 調整路徑以適應從 scripts 目錄執行
    if not os.path.exists(config_file):
        config_file = "../" + config_file  # 嘗試上級目錄
    if not os.path.exists(config_file):
        # 如果還是找不到，創建預設配置
        return create_default_config()
    
    with open(config_file, encoding='utf-8') as f:
        return yaml.safe_load(f)

def create_default_config():
    """創建預設的伺服器配置"""
    return {
        'servers': {
            'l1_cdns': [
                {'name': 'cloudflare-simulation', 'image': 'nginx:alpine', 'config': 'cloudflare.conf'},
                {'name': 'akamai-simulation', 'image': 'nginx:1.24', 'config': 'akamai.conf'},
                {'name': 'fastly-simulation', 'image': 'nginx:1.25', 'config': 'fastly.conf'}
            ],
            'l2_proxies': [
                {'name': 'nginx', 'versions': ['1.24', '1.25', '1.26'], 'image': 'nginx:{version}'},
                {'name': 'varnish', 'versions': ['7.3', '7.4', '7.5'], 'image': 'varnish:{version}'},
                {'name': 'haproxy', 'versions': ['2.8', '2.9', '3.0'], 'image': 'haproxy:{version}'},
                {'name': 'traefik', 'versions': ['2.10', '3.0'], 'image': 'traefik:{version}'},
                {'name': 'envoy', 'versions': ['1.27', '1.28'], 'image': 'envoyproxy/envoy:v{version}-latest'}
            ],
            'l3_servers': [
                {'name': 'apache', 'versions': ['2.4.57', '2.4.58', '2.4.59'], 'image': 'httpd:{version}'},
                {'name': 'tomcat', 'versions': ['9.0', '10.1', '11.0'], 'image': 'tomcat:{version}'},
                {'name': 'nginx', 'versions': ['1.24', '1.25', '1.26'], 'image': 'nginx:{version}'},
                {'name': 'lighttpd', 'versions': ['1.4.71', '1.4.72'], 'image': 'sebp/lighttpd:{version}'},
                {'name': 'caddy', 'versions': ['2.7', '2.8'], 'image': 'caddy:{version}-alpine'},
                {'name': 'openlitespeed', 'versions': ['1.7', '1.8'], 'image': 'litespeedtech/openlitespeed:{version}'}
            ]
        },
        'combination_rules': {
            'target_count': 280
        }
    }

def expand_servers(servers_config):
    """展開伺服器配置為具體實例"""
    expanded = {'l1': [], 'l2': [], 'l3': []}
    
    # L1: CDN 模擬
    for cdn in servers_config['l1_cdns']:
        expanded['l1'].append({
            'name': cdn['name'], 
            'image': cdn['image'], 
            'config': cdn.get('config', 'default.conf')
        })
    
    # L2: 反向代理
    for proxy in servers_config['l2_proxies']:
        for version in proxy.get('versions', ['latest']):
            expanded['l2'].append({
                'name': f"{proxy['name']}_{version}", 
                'base_name': proxy['name'], 
                'version': version, 
                'image': proxy['image'].format(version=version)
            })
    
    # L3: 應用伺服器
    for server in servers_config['l3_servers']:
        for version in server.get('versions', ['latest']):
            expanded['l3'].append({
                'name': f"{server['name']}_{version}", 
                'base_name': server['name'], 
                'version': version, 
                'image': server['image'].format(version=version)
            })
    
    return expanded

def stratified_sampling(all_combinations, target_count=280, seed=42):
    """分層抽樣確保技術覆蓋"""
    random.seed(seed)
    from collections import defaultdict
    
    # 按技術類型分組
    groups = defaultdict(list)
    for combo in all_combinations:
        l1, l2, l3 = combo
        key = (l1['name'], l2['base_name'], l3['base_name'])
        groups[key].append(combo)
    
    selected = []
    
    # 每組先取 1 筆
    for combos in groups.values():
        selected.append(random.choice(combos))
        if len(selected) >= target_count:
            break
    
    # 若不足，隨機補滿
    if len(selected) < target_count:
        remaining = [c for c in all_combinations if c not in selected]
        if remaining:
            extra_needed = min(target_count - len(selected), len(remaining))
            extra = random.sample(remaining, extra_needed)
            selected.extend(extra)
    
    return selected[:target_count]

def generate_and_save(output_file="data/combinations.json"):
    """生成並儲存組合"""
    print("🔧 LLM-UnTangle 組合生成器")
    print("=" * 40)
    
    # 確保從正確目錄執行
    if os.path.basename(os.getcwd()) == 'scripts':
        os.chdir('..')  # 回到專案根目錄
        print("✓ 已切換到專案根目錄")
    
    try:
        cfg = load_server_configs()
        print("✓ 載入伺服器配置")
    except Exception as e:
        print(f"⚠️  配置載入失敗，使用預設配置: {e}")
        cfg = create_default_config()
    
    # 展開伺服器
    expanded = expand_servers(cfg['servers'])
    print(f"✓ 可用伺服器: L1={len(expanded['l1'])}, L2={len(expanded['l2'])}, L3={len(expanded['l3'])}")
    
    # 生成所有組合
    all_combos = list(itertools.product(expanded['l1'], expanded['l2'], expanded['l3']))
    print(f"✓ 理論組合數: {len(all_combos)}")
    
    # 抽樣
    target_count = cfg.get('combination_rules', {}).get('target_count', 280)
    chosen = stratified_sampling(all_combos, target_count=target_count)
    print(f"✓ 選取 {len(chosen)} 組組合")
    
    # 轉換格式
    combos = []
    for idx, (l1, l2, l3) in enumerate(chosen, start=1):
        combos.append({
            'id': f"combo_{idx:03d}", 
            'l1': l1, 
            'l2': l2, 
            'l3': l3, 
            'url': f"http://localhost:{8000+idx}", 
            'status': 'pending'
        })
    
    # 儲存檔案
    Path('data').mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(combos, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 已生成 {len(combos)} 組並儲存到 {output_file}")
    
    # 顯示範例
    if combos:
        print(f"\n📋 範例組合:")
        example = combos[0]
        print(f"   ID: {example['id']}")
        print(f"   L1: {example['l1']['name']} ({example['l1']['image']})")
        print(f"   L2: {example['l2']['name']} ({example['l2']['image']})")
        print(f"   L3: {example['l3']['name']} ({example['l3']['image']})")
        print(f"   URL: {example['url']}")

if __name__ == '__main__':
    try:
        generate_and_save()
        print("\n🎉 組合生成完成！")
        print("\n下一步：")
        print("   python scripts/prepare_datasets.py")
    except Exception as e:
        print(f"\n❌ 執行失敗: {e}")
        import traceback
        traceback.print_exc()
