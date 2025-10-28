#!/usr/bin/env python3
"""
生成三層架構組合，輸出到 data/combinations.json
修正版（1x1x9 或一般情況皆適用）：
- 嚴格依照 configs/server_configs.yaml 的 servers 列表完全枚舉 L1×L2×L3
- 不再使用分層隨機抽樣，避免重複挑選同一個 L3 導致覆蓋不均
- 若 combination_rules.target_count 小於全量，依序取前 target_count 筆，保證每個 L3 最少取 1 次（若 target < L3 種數，則報錯）
- 從 scripts/ 目錄執行時自動切回專案根目錄
"""
import yaml
import itertools
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
    # L1
    for cdn in servers_config['l1_cdns']:
        expanded['l1'].append({
            'name': cdn['name'],
            'image': cdn['image'],
            'config': cdn.get('config', 'default.conf')
        })
    # L2
    for proxy in servers_config['l2_proxies']:
        versions = proxy.get('versions', ['latest'])
        for version in versions:
            expanded['l2'].append({
                'name': f"{proxy['name']}_{version}",
                'base_name': proxy['name'],
                'version': version,
                'image': proxy['image'].format(version=version)
            })
    # L3
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


def generate_all_combos(expanded):
    return list(itertools.product(expanded['l1'], expanded['l2'], expanded['l3']))


def choose_combos_complete(cfg, all_combos, expanded):
    target = cfg.get('combination_rules', {}).get('target_count', len(all_combos))
    # 驗證：target 需至少等於獨特 L3 的數量，否則必然有 L3 未覆蓋
    unique_l3 = {c[2]['name'] for c in all_combos}
    if target < len(unique_l3):
        raise ValueError(f"target_count={target} 小於 L3 類型數量 {len(unique_l3)}，將導致部分 L3 未被覆蓋。請將 target_count >= {len(unique_l3)}。")

    # 完全枚舉，依序取前 target 筆即可（配置已限制 L1=1, L2=1, L3=9）
    chosen = all_combos[:target]

    # 最後一次保險：若 target==len(all_combos) 但仍擔心 YAML 編輯錯，加入覆蓋性檢查
    covered_l3 = {c[2]['name'] for c in chosen}
    missing = unique_l3 - covered_l3
    if missing:
        raise RuntimeError(f"選擇的組合未涵蓋所有 L3：缺少 {sorted(missing)}。請檢查 configs/server_configs.yaml。")

    return chosen


def generate_and_save():
    print('🔧 LLM-UnTangle 組合生成器（完全枚舉版）')
    cfg = load_server_configs()
    expanded = expand_servers(cfg['servers'])
    all_combos = generate_all_combos(expanded)

    chosen = choose_combos_complete(cfg, all_combos, expanded)

    combos = []
    for idx, (l1, l2, l3) in enumerate(chosen, start=1):
        combos.append({
            'id': f"combo_{idx:03d}",
            'l1': l1,
            'l2': l2,
            'l3': l3,
            'url': f"http://localhost:{8000+idx}",
            'replicate_tag': '',
            'status': 'pending'
        })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(combos, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"✓ 已生成 {len(combos)} 組並儲存到 {OUTPUT_PATH}")


if __name__ == '__main__':
    # 無論在根目錄或 scripts 內執行，都以 ROOT 為準
    os.chdir(ROOT)
    generate_and_save()
