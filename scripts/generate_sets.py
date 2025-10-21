#!/usr/bin/env python3
"""
生成 250-300 組三層架構組合，輸出到 data/combinations.json
"""
import yaml
import itertools
import random
import json
from pathlib import Path

def load_server_configs(config_file="configs/server_configs.yaml"):
    with open(config_file, encoding='utf-8') as f:
        return yaml.safe_load(f)

def expand_servers(servers_config):
    expanded = {'l1': [], 'l2': [], 'l3': []}
    for cdn in servers_config['l1_cdns']:
        expanded['l1'].append({'name': cdn['name'], 'image': cdn['image'], 'config': cdn.get('config','default.conf')})
    for proxy in servers_config['l2_proxies']:
        for version in proxy.get('versions', ['latest']):
            expanded['l2'].append({'name': f"{proxy['name']}_{version}", 'base_name': proxy['name'], 'version': version, 'image': proxy['image'].format(version=version)})
    for server in servers_config['l3_servers']:
        for version in server.get('versions', ['latest']):
            expanded['l3'].append({'name': f"{server['name']}_{version}", 'base_name': server['name'], 'version': version, 'image': server['image'].format(version=version)})
    return expanded

def stratified_sampling(all_combinations, target_count=280, seed=42):
    random.seed(seed)
    # 分組 key：L1 名稱 + L2/L3 基礎名稱
    from collections import defaultdict
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
        extra = random.sample(remaining, target_count - len(selected))
        selected.extend(extra)
    return selected[:target_count]

def generate_and_save(output_file="data/combinations.json"):
    cfg = load_server_configs()
    expanded = expand_servers(cfg['servers'])
    all_combos = list(itertools.product(expanded['l1'], expanded['l2'], expanded['l3']))
    chosen = stratified_sampling(all_combos, target_count=cfg.get('combination_rules',{}).get('target_count',280))
    combos = []
    for idx, (l1,l2,l3) in enumerate(chosen, start=1):
        combos.append({'id': f"combo_{idx:03d}", 'l1': l1, 'l2': l2, 'l3': l3, 'url': f"http://localhost:{8000+idx}", 'status':'pending'})
    Path('data').mkdir(parents=True, exist_ok=True)
    with open(output_file,'w',encoding='utf-8') as f:
        json.dump(combos, f, ensure_ascii=False, indent=2)
    print(f"✓ 已生成 {len(combos)} 組並儲存到 {output_file}")

if __name__ == '__main__':
    generate_and_save()
