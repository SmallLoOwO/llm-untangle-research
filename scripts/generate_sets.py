#!/usr/bin/env python3
"""
生成 250-300 組三層架構組合，輸出到 data/combinations.json
修正版：
- 自動從 scripts/ 目錄執行時回到專案根目錄
- 正確尋找 configs/server_configs.yaml
- 確保每個 L1|L2_base|L3_base 分層鍵至少 2 筆，避免分層抽樣孤立類別
"""
import yaml
import itertools
import random
import json
import os
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'configs' / 'server_configs.yaml'
OUTPUT_PATH = ROOT / 'data' / 'combinations.json'


def load_server_configs():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f'找不到 {CONFIG_PATH}. 請確認倉庫有 configs/server_configs.yaml')
    with open(CONFIG_PATH, encoding='utf-8') as f:
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
            selected.append(combos[0])
            selected.append(combos[0])

    if len(selected) > target_count:
        selected = selected[:target_count]
    elif len(selected) < target_count:
        remaining = [c for c in all_combinations]
        need = target_count - len(selected)
        selected.extend(random.sample(remaining, need))

    return selected[:target_count]

def generate_and_save():
    print('🔧 LLM-UnTangle 組合生成器（根目錄路徑修正版）')
    cfg = load_server_configs()
    expanded = expand_servers(cfg['servers'])
    all_combos = list(itertools.product(expanded['l1'], expanded['l2'], expanded['l3']))

    target = cfg.get('combination_rules',{}).get('target_count',280)
    chosen = stratified_sampling_balanced(all_combos, target_count=target)

    combos = []
    used_counts = defaultdict(int)
    for idx, (l1,l2,l3) in enumerate(chosen, start=1):
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

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(combos, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"✓ 已生成 {len(combos)} 組並儲存到 {OUTPUT_PATH}")

if __name__ == '__main__':
    # 無論在根目錄或 scripts 內執行，都以 ROOT 為準
    os.chdir(ROOT)
    generate_and_save()
