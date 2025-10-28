#!/usr/bin/env python3
"""
Docker Compose 配置生成器（修正版）
- 嚴格依照 data/combinations.json 的順序生成，每個 combo 對應不同 L3
- 端口規則：
  - L1: 8000 + index
  - L2: 9000 + index
  - L3: 10000 + index
- 檢查 L3 覆蓋情況，列印所有將要生成的 L3 名稱，方便人工核對
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
    idx = combo_index  # 0-based
    return {
        'version': '3.8',
        'services': {
            f'{combo_id}_l3': {
                'image': combo['l3']['image'],
                'container_name': f"{combo_id}_l3_{combo['l3']['name']}",
                'ports': [f'{10000 + idx}:80'],
                'restart': 'unless-stopped'
            },
            f'{combo_id}_l2': {
                'image': combo['l2']['image'],
                'container_name': f"{combo_id}_l2_{combo['l2']['name']}",
                'ports': [f'{9000 + idx}:80'],
                'restart': 'unless-stopped',
                'depends_on': [f'{combo_id}_l3']
            },
            f'{combo_id}_l1': {
                'image': combo['l1']['image'],
                'container_name': f"{combo_id}_l1_{combo['l1']['name']}",
                'ports': [f'{8000 + idx}:80'],
                'restart': 'unless-stopped',
                'depends_on': [f'{combo_id}_l2']
            }
        }
    }


def main():
    print('🐳 Docker Compose 配置生成器（修正版）')
    print('=' * 60)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    combinations = load_combinations()
    print(f"載入 {len(combinations)} 組組合")

    l3_list = [c['l3']['name'] for c in combinations]
    print('L3 將生成的順序/種類：', ', '.join(l3_list))

    for index, combo in enumerate(combinations):
        compose_content = create_single_compose_file(combo, index)
        filename = OUT_DIR / f"compose_{combo['id']}.yml"
        filename.write_text(yaml.dump(compose_content, default_flow_style=False, allow_unicode=True), encoding='utf-8')
        progress = (index + 1) / len(combinations) * 100
        print(f"[{progress:5.1f}%] 生成 {combo['id']}")

    print(f"\n✓ 生成 {len(combinations)} 個 Docker Compose 配置於 docker_configs/")
    print('\n下一步：docker compose -f docker_configs/compose_combo_001.yml up -d')


if __name__ == '__main__':
    main()
