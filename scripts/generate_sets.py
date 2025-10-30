#!/usr/bin/env python3
"""
生成三層架構組合（90 組擴增版支援）
- 完全枚舉 L1×L2×L3
- 依 combination_rules.min_per_l3 進行按 L3 類別的均衡擴增，直到 target_count
- 若單一 L3 可用版本 < min_per_l3，將循環複用（replicate_tag）填滿
"""
import yaml
import itertools
import json
import os
from pathlib import Path
from collections import defaultdict, deque

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
        expanded['l1'].append({
            'name': cdn['name'],
            'image': cdn['image'],
            'config': cdn.get('config', 'default.conf')
        })
    for proxy in servers_config['l2_proxies']:
        versions = proxy.get('versions', ['latest'])
        for version in versions:
            expanded['l2'].append({
                'name': f"{proxy['name']}_{version}",
                'base_name': proxy['name'],
                'version': version,
                'image': proxy['image'].format(version=version)
            })
    for server in servers_config['l3_servers']:
        versions = server.get('versions', ['latest'])
        for version in versions:
            expanded['l3'].append({
                'name': f"{server['name']}_{version}",
                'base_name': server['name'],
                'version': version,
                'image': server['image'].format(version=version)
            })
    return expanded


def generate_balanced_by_l3(cfg, expanded):
    target = cfg.get('combination_rules', {}).get('target_count', 90)
    min_per_l3 = cfg.get('combination_rules', {}).get('min_per_l3', 10)

    # 準備每個 L3 類別可用的版本清單（以 deque 輪詢）
    by_l3 = defaultdict(list)
    for l3 in expanded['l3']:
        by_l3[l3['base_name']].append(l3)
    for k in by_l3:
        by_l3[k] = deque(by_l3[k])

    l1 = expanded['l1'][0]
    l2 = expanded['l2'][0]

    # 先確保每個 L3 至少 min_per_l3
    combos = []
    used_counts = defaultdict(int)
    for base_name, q in by_l3.items():
        for _ in range(min_per_l3):
            if not q:
                # 理論上不會發生，保險處理
                q = deque(by_l3[base_name])
            l3 = q[0]
            q.rotate(-1)
            used_counts[(base_name, l3['version'])] += 1
            suffix = '' if used_counts[(base_name, l3['version'])] == 1 else f"_{used_counts[(base_name, l3['version'])]}"
            combos.append((l1, l2, {**l3, 'name': f"{l3['name']}{suffix}"}))

    # 若仍未達 target，依所有 L3 輪詢補滿
    all_cycle = deque(expanded['l3'])
    while len(combos) < target:
        l3 = all_cycle[0]
        all_cycle.rotate(-1)
        used_counts[(l3['base_name'], l3['version'])] += 1
        suffix = '' if used_counts[(l3['base_name'], l3['version'])] == 1 else f"_{used_counts[(l3['base_name'], l3['version'])]}"
        combos.append((l1, l2, {**l3, 'name': f"{l3['name']}{suffix}"}))

    return combos[:target]


def generate_and_save():
    print('🔧 LLM-UnTangle 組合生成器（90 組均衡版）')
    cfg = load_server_configs()
    expanded = expand_servers(cfg['servers'])

    # 均衡生成（每 L3 至少 min_per_l3）
    chosen = generate_balanced_by_l3(cfg, expanded)

    out = []
    for idx, (l1, l2, l3) in enumerate(chosen, start=1):
        out.append({
            'id': f"combo_{idx:03d}",
            'l1': l1,
            'l2': l2,
            'l3': l3,
            'url': f"http://localhost:{8000+idx}",
            'replicate_tag': '',
            'status': 'pending'
        })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"✓ 已生成 {len(out)} 組並儲存到 {OUTPUT_PATH}")


if __name__ == '__main__':
    os.chdir(ROOT)
    generate_and_save()
