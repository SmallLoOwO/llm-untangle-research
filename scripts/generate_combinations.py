#!/usr/bin/env python3
"""
修復：generate_combinations.py 在 scripts 目錄執行時應能找到 data/combinations.json
- 使用專案根路徑讀檔與輸出
- 若找不到 combinations.json，提供清楚提示
"""
import json
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / 'data' / 'combinations.json'
OUT_DIR = ROOT / 'docker_configs'


def load_combinations():
    if not DATA_PATH.exists():
        raise FileNotFoundError('找不到 data/combinations.json，請先執行: python scripts/generate_sets.py')
    return json.loads(DATA_PATH.read_text(encoding='utf-8'))


def create_single_compose_file(combo, combo_index):
    combo_id = combo['id']
    base_port = 8000 + combo_index
    return {
        'version': '3.8',
        'services': {
            f'{combo_id}_l3': {
                'image': combo['l3']['image'],
                'container_name': f"{combo_id}_l3_{combo['l3']['name']}",
                'ports': [f'{base_port + 2000}:80'],
                'restart': 'unless-stopped'
            },
            f'{combo_id}_l2': {
                'image': combo['l2']['image'],
                'container_name': f"{combo_id}_l2_{combo['l2']['name']}",
                'ports': [f'{base_port + 1000}:80'],
                'restart': 'unless-stopped',
                'depends_on': [f'{combo_id}_l3']
            },
            f'{combo_id}_l1': {
                'image': combo['l1']['image'],
                'container_name': f"{combo_id}_l1_{combo['l1']['name']}",
                'ports': [f'{base_port}:80'],
                'restart': 'unless-stopped',
                'depends_on': [f'{combo_id}_l2']
            }
        }
    }


def main():
    print('🐳 Docker Compose 配置生成器')
    print('=' * 50)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    combinations = load_combinations()
    print(f"載入 {len(combinations)} 組組合")

    for index, combo in enumerate(combinations):
        compose_content = create_single_compose_file(combo, index)
        filename = OUT_DIR / f"compose_{combo['id']}.yml"
        filename.write_text(yaml.dump(compose_content, default_flow_style=False), encoding='utf-8')
        progress = (index + 1) / len(combinations) * 100
        print(f"[{progress:5.1f}%] 生成 {combo['id']}")

    print(f"\n✓ 生成 {len(combinations)} 個 Docker Compose 配置於 docker_configs/")
    print('\n下一步：docker compose -f docker_configs/compose_combo_001.yml up -d')


if __name__ == '__main__':
    main()
