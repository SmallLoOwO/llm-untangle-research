#!/usr/bin/env python3
"""
根据论文的9种伺服器类型重新生成测试组合
L1(3种) × L2(3种) × L3(3种) = 27种基础组合
每种组合生成多个实例，总计250-300组
"""
import json
import itertools
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / 'data' / 'paper_combinations.json'

# 论文定义的伺服器类型
L1_SERVERS = ['nginx_l1', 'haproxy_l1', 'traefik_l1']
L2_SERVERS = ['varnish_l2', 'squid_l2', 'apache_l2'] 
L3_SERVERS = ['tomcat', 'flask', 'express']  # 论文重点测试层

# Docker映像配置
SERVER_IMAGES = {
    # L1层
    'nginx_l1': {'image': 'nginx:1.20', 'name': 'nginx_l1', 'base_name': 'nginx'},
    'haproxy_l1': {'image': 'haproxy:2.4', 'name': 'haproxy_l1', 'base_name': 'haproxy'},
    'traefik_l1': {'image': 'traefik:2.5', 'name': 'traefik_l1', 'base_name': 'traefik'},
    
    # L2层
    'varnish_l2': {'image': 'varnish:7.0', 'name': 'varnish_l2', 'base_name': 'varnish'},
    'squid_l2': {'image': 'ubuntu/squid:latest', 'name': 'squid_l2', 'base_name': 'squid'},
    'apache_l2': {'image': 'httpd:2.4', 'name': 'apache_l2', 'base_name': 'apache'},
    
    # L3层（论文重点）
    'tomcat': {'image': 'tomcat:9.0', 'name': 'tomcat', 'base_name': 'tomcat'},
    'flask': {'image': 'llm-untangle-flask:latest', 'name': 'flask', 'base_name': 'flask'}, 
    'express': {'image': 'llm-untangle-express:latest', 'name': 'express', 'base_name': 'express'}
}

def generate_paper_combinations(target_count=280, seed=42):
    """根据论文生成标准组合"""
    random.seed(seed)
    
    # 生成所有可能的三层组合 (3×3×3 = 27)
    all_combinations = list(itertools.product(L1_SERVERS, L2_SERVERS, L3_SERVERS))
    
    combinations = []
    base_port = 8001
    
    # 每种组合生成多个实例以达到目标数量
    instances_per_combo = target_count // len(all_combinations) + 1
    
    for combo_idx, (l1, l2, l3) in enumerate(all_combinations):
        for instance in range(instances_per_combo):
            if len(combinations) >= target_count:
                break
                
            combo_id = f"combo_{len(combinations)+1:03d}"
            port = base_port + len(combinations)
            
            combination = {
                'id': combo_id,
                'url': f'http://localhost:{port}',
                'port': port,
                
                # L1层配置
                'l1': {
                    **SERVER_IMAGES[l1],
                    'layer': 'L1',
                    'type': 'CDN/Front'
                },
                
                # L2层配置  
                'l2': {
                    **SERVER_IMAGES[l2],
                    'layer': 'L2',
                    'type': 'Proxy/Cache'
                },
                
                # L3层配置（论文重点）
                'l3': {
                    **SERVER_IMAGES[l3],
                    'layer': 'L3', 
                    'type': 'App/Origin',
                    'paper_focus': True  # 标记为论文重点层
                },
                
                'architecture_type': f"{l1}-{l2}-{l3}",
                'paper_compliant': True,
                'status': 'pending'
            }
            
            combinations.append(combination)
    
    return combinations[:target_count]

def save_combinations(combinations, output_path):
    """保存组合到文件"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(combinations, f, indent=2, ensure_ascii=False)
    
    # 生成统计信息
    l3_distribution = {}
    for combo in combinations:
        l3_type = combo['l3']['base_name']
        l3_distribution[l3_type] = l3_distribution.get(l3_type, 0) + 1
    
    print(f"✅ 已生成 {len(combinations)} 组论文标准组合")
    print(f"📊 L3层分布（论文重点）:")
    for server, count in sorted(l3_distribution.items()):
        print(f"   {server}: {count} 组 ({count/len(combinations)*100:.1f}%)")
    
    # 显示架构类型数量
    arch_types = set(c['architecture_type'] for c in combinations)
    print(f"\n🏗️ 架构类型总数: {len(arch_types)} 种")
    print(f"   (L1: 3种 × L2: 3种 × L3: 3种 = 27种基础架构)")
    
    return combinations

if __name__ == '__main__':
    print("📋 根据论文生成9种伺服器类型的测试组合...")
    print("=" * 60)
    
    combinations = generate_paper_combinations(280)
    save_combinations(combinations, OUTPUT_PATH)
    
    print(f"\n💾 组合已保存至: {OUTPUT_PATH}")
    print("🎯 符合论文要求：L1(3种) × L2(3种) × L3(3种) = 9种伺服器类型")
    print("\n下一步: python scripts/create_paper_images.py")
