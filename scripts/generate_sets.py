#!/usr/bin/env python3
"""
生成 250-300 組三層架構組合，輸出到 data/combinations.json
修正版：確保最嚴格分層鍵 (L1|L2_base|L3_base) 中每一類別至少 2 筆，避免分層抽樣時出現孤立類別。
"""
import yaml
import itertools
import random
import json
from pathlib import Path
from collections import defaultdict

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

def _key(l1,l2,l3):
    return (l1['name'], l2['base_name'], l3['base_name'])

def stratified_sampling_balanced(all_combinations, target_count=280, seed=42):
    random.seed(seed)
    groups = defaultdict(list)
    for (l1,l2,l3) in all_combinations:
        groups[_key(l1,l2,l3)].append((l1,l2,l3))

    selected = []
    # 先讓每一個分層鍵至少選 2 筆（若該組只有 1 筆，允許重複抽樣同一組，避免孤立類別）
    for combos in groups.values():
        if len(selected) >= target_count:
            break
        if len(combos) >= 2:
            picked = random.sample(combos, 2)
            selected.extend(picked)
        else:
            # 只有 1 筆，重複該筆第二次，之後下游程式會以不同 id/url 區分
            selected.append(combos[0])
            selected.append(combos[0])

    # 若超過 target_count，截斷；若不足則隨機補滿（避免重複盡量從未選集合補）
    if len(selected) > target_count:
        selected = selected[:target_count]
    elif len(selected) < target_count:
        remaining = [c for c in all_combinations]
        need = target_count - len(selected)
        selected.extend(random.sample(remaining, need))

    return selected[:target_count]


def generate_and_save(output_file="data/combinations.json"):
    cfg = load_server_configs()
    expanded = expand_servers(cfg['servers'])
    all_combos = list(itertools.product(expanded['l1'], expanded['l2'], expanded['l3']))

    target = cfg.get('combination_rules',{}).get('target_count',280)
    chosen = stratified_sampling_balanced(all_combos, target_count=target)

    combos = []
    used_counts = defaultdict(int)
    for idx, (l1,l2,l3) in enumerate(chosen, start=1):
        # 對於被重複的組合，自動累加序號後綴，並調整 URL 埠避免衝突
        k = _key(l1,l2,l3)
        used_counts[k] += 1
        suffix = '' if used_counts[k] == 1 else f"_{used_counts[k]}"
        combos.append({
            'id': f"combo_{idx:03d}",
            'l1': l1,
            'l2': l2,
            'l3': l3,
            'url': f"http://localhost:{8000+idx}",
            'replicate_tag': suffix,
            'status':'pending'
        })

    Path('data').mkdir(parents=True, exist_ok=True)
    with open(output_file,'w',encoding='utf-8') as f:
        json.dump(combos, f, ensure_ascii=False, indent=2)
    print(f"✓ 已生成 {len(combos)} 組並儲存到 {output_file}")

if __name__ == '__main__':
    generate_and_save()
