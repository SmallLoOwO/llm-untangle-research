#!/usr/bin/env python3
"""
Docker Compose 配置生成器
為每個三層架構組合生成對應的 Docker 配置
適用於 Docker Desktop 使用者
"""

import json
import yaml
from pathlib import Path
from textwrap import dedent
import os

def load_combinations():
    """載入組合資訊"""
    with open('data/combinations.json', encoding='utf-8') as f:
        return json.load(f)

def create_single_compose_file(combo, combo_index):
    """為單一組合建立 Docker Compose 檔案"""
    combo_id = combo['id']
    base_port = 8000 + combo_index
    
    compose_content = {
        'version': '3.8',
        'services': {
            f'{combo_id}_l3': {
                'image': combo['l3']['image'],
                'container_name': f'{combo_id}_l3_{combo["l3"]["name"]}',
                'ports': [f'{base_port + 2000}:80'],
                'restart': 'unless-stopped'
            },
            f'{combo_id}_l2': {
                'image': combo['l2']['image'], 
                'container_name': f'{combo_id}_l2_{combo["l2"]["name"]}',
                'ports': [f'{base_port + 1000}:80'],
                'restart': 'unless-stopped',
                'depends_on': [f'{combo_id}_l3']
            },
            f'{combo_id}_l1': {
                'image': combo['l1']['image'],
                'container_name': f'{combo_id}_l1_{combo["l1"]["name"]}',
                'ports': [f'{base_port}:80'],
                'restart': 'unless-stopped', 
                'depends_on': [f'{combo_id}_l2']
            }
        }
    }
    
    return compose_content

def main():
    print("🐳 Docker Compose 配置生成器")
    print("=" * 50)
    
    # 建立必要目錄
    Path('docker_configs').mkdir(parents=True, exist_ok=True)
    
    # 載入組合
    combinations = load_combinations()
    print(f"載入 {len(combinations)} 組組合")
    
    # 生成配置檔案
    for index, combo in enumerate(combinations):
        compose_content = create_single_compose_file(combo, index)
        
        # 儲存檔案
        filename = f"docker_configs/compose_{combo['id']}.yml"
        with open(filename, 'w', encoding='utf-8') as f:
            yaml.dump(compose_content, f, default_flow_style=False)
        
        # 顯示進度
        progress = (index + 1) / len(combinations) * 100
        print(f"[{progress:5.1f}%] 生成 {combo['id']}")
    
    print(f"\n✓ 生成 {len(combinations)} 個 Docker Compose 配置")
    print("\n下一步：執行啟動腳本")

if __name__ == "__main__":
    main()
