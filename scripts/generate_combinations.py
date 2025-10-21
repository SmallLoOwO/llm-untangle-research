#!/usr/bin/env python3
"""
自動生成 250-300 組三層架構組合
LLM-UnTangle 專案的核心數據集生成器
"""

import yaml
import itertools
import random
import json
from pathlib import Path
from collections import defaultdict

def load_server_configs(config_file="configs/server_configs.yaml"):
    """載入伺服器配置"""
    with open(config_file, encoding='utf-8') as f:
        return yaml.safe_load(f)

def expand_servers(servers_config):
    """展開版本資訊為具體的伺服器實例"""
    expanded = {
        'l1': [],
        'l2': [],
        'l3': []
    }
    
    # L1: CDN 模擬（不需要展開版本）
    for cdn in servers_config['l1_cdns']:
        expanded['l1'].append({
            'name': cdn['name'],
            'image': cdn['image'],
            'config': cdn.get('config', 'default.conf'),
            'description': cdn.get('description', '')
        })
    
    # L2: 反向代理（展開版本）
    for proxy in servers_config['l2_proxies']:
        for version in proxy.get('versions', ['latest']):
            expanded['l2'].append({
                'name': f"{proxy['name']}_{version}",
                'base_name': proxy['name'],
                'version': version,
                'image': proxy['image'].format(version=version),
                'description': proxy.get('description', '')
            })
    
    # L3: 應用伺服器（展開版本）
    for server in servers_config['l3_servers']:
        for version in server.get('versions', ['latest']):
            expanded['l3'].append({
                'name': f"{server['name']}_{version}",
                'base_name': server['name'],
                'version': version,
                'image': server['image'].format(version=version),
                'description': server.get('description', '')
            })
    
    return expanded

def stratified_sampling(all_combinations, target_count=280, random_seed=42):
    """
    分層抽樣確保每種技術都有足夠的代表性
    """
    random.seed(random_seed)
    
    # 按照 L1, L2, L3 的技術类型分类
    tech_groups = defaultdict(list)
    
    for combo in all_combinations:
        key = (
            combo[0]['name'],  # L1
            combo[1]['base_name'],  # L2 基礎名稱
            combo[2]['base_name']   # L3 基礎名稱
        )
        tech_groups[key].append(combo)
    
    print(f"找到 {len(tech_groups)} 種不同的技術組合")
    
    # 每個技術組合至少抽取一個樣本
    selected = []
    remaining_quota = target_count
    
    # 第一步：每個技術組合至少選一個
    for group_combos in tech_groups.values():
        selected.append(random.choice(group_combos))
        remaining_quota -= 1
    
    # 第二步：剩餘名額按比例分配
    if remaining_quota > 0:
        # 按照每個組的大小計算權重
        group_weights = [(key, len(combos)) for key, combos in tech_groups.items()]
        total_weight = sum(weight for _, weight in group_weights)
        
        for key, weight in group_weights:
            if remaining_quota <= 0:
                break
                
            # 按比例分配額外名額
            extra_samples = min(
                remaining_quota,
                max(1, int(remaining_quota * weight / total_weight))
            )
            
            # 從此組中隨機抽取額外樣本
            available = [c for c in tech_groups[key] if c not in selected]
            if available:
                extra = random.sample(available, min(extra_samples, len(available)))
                selected.extend(extra)
                remaining_quota -= len(extra)
    
    # 如果還有剩餘配額，隨機填滿
    if remaining_quota > 0:
        all_unused = [c for c in all_combinations if c not in selected]
        if all_unused:
            extra = random.sample(all_unused, min(remaining_quota, len(all_unused)))
            selected.extend(extra)
    
    return selected[:target_count]

def generate_combinations(config_file="configs/server_configs.yaml"):
    """生成指定數量的組合"""
    # 載入配置
    config = load_server_configs(config_file)
    
    # 展開伺服器
    expanded = expand_servers(config['servers'])
    print(f"可用伺服器數量: L1={len(expanded['l1'])}, "
          f"L2={len(expanded['l2'])}, L3={len(expanded['l3'])}")
    
    # 生成所有可能的組合
    all_combinations = list(itertools.product(
        expanded['l1'],
        expanded['l2'],
        expanded['l3']
    ))
    
    print(f"理論上可生成 {len(all_combinations)} 種組合")
    
    # 取得目標數量
    target_count = config.get('combination_rules', {}).get('target_count', 280)
    
    # 分層抽樣
    selected_combinations = stratified_sampling(all_combinations, target_count)
    
    # 轉換為標準格式
    combinations = []
    for idx, (l1, l2, l3) in enumerate(selected_combinations, 1):
        combinations.append({
            'id': f"combo_{idx:03d}",
            'l1': l1,
            'l2': l2,
            'l3': l3,
            'url': f"http://localhost:{8000+idx}",
            'created_at': None,  # 將在 Docker 啟動時設定
            'status': 'pending'
        })
    
    return combinations

def save_combinations(combinations, output_file="data/combinations.json"):
    """儲存組合到檔案"""
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(combinations, f, indent=2, ensure_ascii=False)
    print(f"✓ 已生成 {len(combinations)} 組組合，儲存至 {output_file}")

def analyze_combinations(combinations):
    """分析組合結果的多樣性和平衡性"""
    from collections import Counter
    
    print("\n組合分析:")
    print(f"  總組合數: {len(combinations)}")
    
    # L1 分佈
    l1_dist = Counter(c['l1']['name'] for c in combinations)
    print(f"\nL1 (CDN) 分佈:")
    for name, count in l1_dist.most_common():
        print(f"  {name:25s}: {count:3d} ({count/len(combinations)*100:.1f}%)")
    
    # L2 分佈
    l2_dist = Counter(c['l2']['base_name'] for c in combinations)
    print(f"\nL2 (代理) 分佈:")
    for name, count in l2_dist.most_common():
        print(f"  {name:25s}: {count:3d} ({count/len(combinations)*100:.1f}%)")
    
    # L3 分佈
    l3_dist = Counter(c['l3']['base_name'] for c in combinations)
    print(f"\nL3 (應用伺服器) 分佈:")
    for name, count in l3_dist.most_common():
        print(f"  {name:25s}: {count:3d} ({count/len(combinations)*100:.1f}%)")
    
    # 版本多樣性
    l2_versions = Counter(c['l2']['name'] for c in combinations)
    l3_versions = Counter(c['l3']['name'] for c in combinations)
    
    print(f"\n版本多樣性:")
    print(f"  L2 不同版本: {len(l2_versions)} 種")
    print(f"  L3 不同版本: {len(l3_versions)} 種")

def main():
    print("✨ LLM-UnTangle 伺服器組合生成器")
    print("="*50)
    
    # 生成組合
    combinations = generate_combinations()
    
    # 儲存結果
    save_combinations(combinations)
    
    # 分析結果
    analyze_combinations(combinations)
    
    print(f"\n✓ 組合生成完成！")
    print(f"\n下一步：")
    print(f"  python scripts/generate_docker_compose.py")
    print(f"  ./scripts/start_all_dockers.sh")

if __name__ == "__main__":
    main()