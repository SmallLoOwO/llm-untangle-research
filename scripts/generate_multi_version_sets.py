#!/usr/bin/env python3
"""
方案 A：多版本擴展策略組合生成器
生成 780 組三層架構組合 (6×13×10)
透過部署同一伺服器的多個版本，大幅增加測試組合數

特色：
- L1層：6個CDN模擬實例（Cloudflare, CloudFront, Fastly, Akamai）
- L2層：13個Proxy實例（包含多版本Nginx, Varnish, HAProxy等）
- L3層：10個Server實例（包含多版本Apache, Tomcat, Nginx, Caddy等）
- 輸出到 data/multi_version_combinations.json
"""
import yaml
import itertools
import random
import json
import os
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'configs' / 'server_configs_multi_version.yaml'
OUTPUT_PATH = ROOT / 'data' / 'multi_version_combinations.json'


def load_server_configs():
    """載入多版本伺服器配置"""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f'找不到 {CONFIG_PATH}. 請確認有多版本配置檔')
    with open(CONFIG_PATH, encoding='utf-8') as f:
        return yaml.safe_load(f)


def expand_multi_version_servers(servers_config):
    """展開多版本伺服器配置為完整實例列表"""
    expanded = {'l1': [], 'l2': [], 'l3': []}
    
    # L1層：CDN模擬（6個實例）
    for cdn in servers_config['l1_cdns']:
        expanded['l1'].append({
            'name': cdn['name'],
            'image': cdn['image'],
            'config': cdn.get('config', 'default.conf'),
            'description': cdn['description'],
            'features': cdn.get('features', [])
        })
    
    # L2層：代理伺服器（13個實例）
    for proxy in servers_config['l2_proxies']:
        for version in proxy.get('versions', ['latest']):
            version_info = proxy.get('version_info', {}).get(version, {})
            expanded['l2'].append({
                'name': f"{proxy['name']}_{version}",
                'base_name': proxy['name'],
                'version': version,
                'image': proxy['image'].format(version=version),
                'description': proxy['description'],
                'released': version_info.get('released', 'Unknown'),
                'status': version_info.get('status', 'Unknown'),
                'features': version_info.get('features', [])
            })
    
    # L3層：後端伺服器（10個實例）
    for server in servers_config['l3_servers']:
        for version in server.get('versions', ['latest']):
            version_info = server.get('version_info', {}).get(version, {})
            expanded['l3'].append({
                'name': f"{server['name']}_{version}",
                'base_name': server['name'],
                'version': version,
                'image': server['image'].format(version=version),
                'description': server['description'],
                'released': version_info.get('released', 'Unknown'),
                'status': version_info.get('status', 'Unknown'),
                'features': version_info.get('features', [])
            })
    
    return expanded


def generate_all_combinations(expanded_servers):
    """生成所有可能的三層組合（6×13×10=780組）"""
    all_combinations = []
    
    for l1, l2, l3 in itertools.product(
        expanded_servers['l1'],
        expanded_servers['l2'],
        expanded_servers['l3']
    ):
        all_combinations.append((l1, l2, l3))
    
    return all_combinations


def create_combination_metadata(l1, l2, l3, combo_id, index):
    """創建組合的詳細元數據"""
    return {
        'id': combo_id,
        'index': index + 1,
        'l1': l1,
        'l2': l2,
        'l3': l3,
        'combination_key': f"{l1['name']}|{l2['base_name']}_{l2['version']}|{l3['base_name']}_{l3['version']}",
        'url': f"http://localhost:{8000 + index + 1}",
        'ports': {
            'l1': 8000 + index + 1,
            'l2': 9000 + index + 1,
            'l3': 10000 + index + 1
        },
        'version_signature': {
            'l1_type': l1['name'].split('_')[0],  # cloudflare, cloudfront, etc.
            'l2_base': l2['base_name'],
            'l2_version': l2['version'],
            'l3_base': l3['base_name'],
            'l3_version': l3['version']
        },
        'expected_differences': {
            'error_format': f"L2({l2['base_name']}_v{l2['version']}) + L3({l3['base_name']}_v{l3['version']})",
            'header_variations': len(l1.get('features', [])),
            'version_specific_behaviors': True
        },
        'status': 'pending',
        'created_at': '2025-10-25T13:00:00Z'
    }


def sample_combinations_for_testing(all_combinations, target_test_count=300, seed=42):
    """從780組合中抽樣300組用於實際測試"""
    random.seed(seed)
    
    # 使用分層抽樣確保不同版本組合都有代表性
    groups = defaultdict(list)
    
    for combo in all_combinations:
        l1, l2, l3 = combo
        key = (l1['name'].split('_')[0], l2['base_name'], l3['base_name'])
        groups[key].append(combo)
    
    # 從每個基礎組合群組中抽樣
    selected_for_testing = []
    samples_per_group = max(1, target_test_count // len(groups))
    
    for group_combos in groups.values():
        if len(selected_for_testing) >= target_test_count:
            break
        
        sample_size = min(samples_per_group, len(group_combos))
        sampled = random.sample(group_combos, sample_size)
        selected_for_testing.extend(sampled)
    
    # 如果還需要更多樣本，隨機補足
    if len(selected_for_testing) < target_test_count:
        remaining = [c for c in all_combinations if c not in selected_for_testing]
        need = target_test_count - len(selected_for_testing)
        if remaining:
            selected_for_testing.extend(random.sample(remaining, min(need, len(remaining))))
    
    return selected_for_testing[:target_test_count]


def generate_and_save():
    """主要生成函數"""
    print('🚀 方案 A：多版本擴展策略組合生成器')
    print('=' * 60)
    
    # 載入配置
    cfg = load_server_configs()
    expanded = expand_multi_version_servers(cfg['servers'])
    
    # 顯示統計資訊
    l1_count = len(expanded['l1'])
    l2_count = len(expanded['l2'])
    l3_count = len(expanded['l3'])
    total_theoretical = l1_count * l2_count * l3_count
    
    print(f"📊 伺服器實例統計：")
    print(f"   L1 (CDN/Front):     {l1_count} 個實例")
    print(f"   L2 (Proxy/Cache):   {l2_count} 個實例")
    print(f"   L3 (Server/Origin): {l3_count} 個實例")
    print(f"   理論組合總數:       {total_theoretical} 組")
    print()
    
    # 生成所有組合
    all_combinations = generate_all_combinations(expanded)
    print(f"✓ 成功生成 {len(all_combinations)} 組完整組合")
    
    # 創建完整組合列表
    full_combinations = []
    for index, (l1, l2, l3) in enumerate(all_combinations):
        combo_id = f"combo_{index + 1:03d}"
        combo_metadata = create_combination_metadata(l1, l2, l3, combo_id, index)
        full_combinations.append(combo_metadata)
    
    # 抽樣測試組合
    test_count = cfg.get('testing', {}).get('selected_combinations', 300)
    selected_combinations = sample_combinations_for_testing(all_combinations, test_count)
    
    # 標記測試組合
    test_combo_indices = set()
    for test_combo in selected_combinations:
        for i, full_combo in enumerate(full_combinations):
            if (full_combo['l1']['name'] == test_combo[0]['name'] and
                full_combo['l2']['name'] == test_combo[1]['name'] and
                full_combo['l3']['name'] == test_combo[2]['name']):
                full_combinations[i]['status'] = 'selected_for_testing'
                test_combo_indices.add(i)
                break
    
    # 準備輸出數據
    output_data = {
        'metadata': {
            'strategy': 'multi_version_expansion',
            'plan': 'A',
            'total_combinations': len(full_combinations),
            'selected_for_testing': len(test_combo_indices),
            'l1_instances': l1_count,
            'l2_instances': l2_count,
            'l3_instances': l3_count,
            'formula': f"{l1_count} × {l2_count} × {l3_count} = {total_theoretical}",
            'generated_at': '2025-10-25T13:00:00Z'
        },
        'server_instances': {
            'l1_cdns': expanded['l1'],
            'l2_proxies': expanded['l2'],
            'l3_servers': expanded['l3']
        },
        'combinations': full_combinations,
        'testing_statistics': {
            'total_available': len(full_combinations),
            'selected_count': len(test_combo_indices),
            'coverage_rate': f"{len(test_combo_indices) / len(full_combinations) * 100:.1f}%",
            'sampling_method': 'stratified_random'
        }
    }
    
    # 儲存到檔案
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2), 
        encoding='utf-8'
    )
    
    print(f"\n📁 輸出結果：")
    print(f"   檔案位置: {OUTPUT_PATH}")
    print(f"   總組合數: {len(full_combinations)}")
    print(f"   測試組合: {len(test_combo_indices)}")
    print(f"   覆蓋率:   {len(test_combo_indices) / len(full_combinations) * 100:.1f}%")
    
    print(f"\n🎯 與 Untangle 對比：")
    print(f"   Untangle:     756 組合")
    print(f"   方案 A:       {len(full_combinations)} 組合")
    print(f"   增長幅度:     +{len(full_combinations) - 756} 組合 ({(len(full_combinations) - 756) / 756 * 100:+.1f}%)")
    
    print(f"\n✅ 多版本擴展策略實施完成！")
    print(f"\n下一步：")
    print(f"   1. 執行: python scripts/generate_multi_version_docker_configs.py")
    print(f"   2. 建立 Docker 配置檔案")
    print(f"   3. 開始資料收集")


if __name__ == '__main__':
    # 切換到專案根目錄
    os.chdir(ROOT)
    generate_and_save()