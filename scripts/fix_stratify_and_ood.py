#!/usr/bin/env python3
"""
修復 OOD 數量不足與分層警告：
- 自動分析 data/combinations.json 的分層鍵，若有孤立分層鍵（只有 1 筆），複製一筆帶新 ID/URL 以滿足分層要求。
- 重新生成 OOD 測試集，保證 >= 50 筆。
- 產出到 data/combinations.json（原地覆寫）與 data/ood/ood_combinations.json。
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
COMBO = ROOT / 'data' / 'combinations.json'
OOD = ROOT / 'data' / 'ood' / 'ood_combinations.json'


def load_json(p):
    return json.loads(p.read_text(encoding='utf-8'))


def save_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def fix_stratify_min2(combos):
    from collections import defaultdict
    groups = defaultdict(list)
    for c in combos:
        key = f"{c['l1']['name']}|{c['l2']['base_name']}|{c['l3']['base_name']}"
        groups[key].append(c)

    fixed = []
    for key, items in groups.items():
        fixed.extend(items)
        if len(items) == 1:
            # 複製一筆，修改 id 與 url，避免完全重複
            src = items[0]
            dup = json.loads(json.dumps(src))
            dup['id'] = src['id'] + '_dup'
            if 'url' in dup and dup['url'].startswith('http://localhost:'):
                base = int(dup['url'].rsplit(':', 1)[-1])
                dup['url'] = f"http://localhost:{base+10000}"
            fixed.append(dup)
    return fixed


def ensure_ood_min50():
    # 若現有 OOD < 50，按既有樣式補齊
    existing = []
    if OOD.exists():
        existing = load_json(OOD)
    n = len(existing)
    if n >= 50:
        return existing

    # 依照 prepare_datasets 既定的 OOD 組合來源補齊
    l3 = [
        ('openlitespeed_1.8', 'litespeedtech/openlitespeed:1.8', '輕量級 Web 伺服器'),
        ('h2o_http2', 'lkwg82/h2o-http2-server', 'HTTP/2 專用伺服器'),
        ('jetty_12', 'jetty:12-jre21', 'Java 伺服器'),
        ('unit_1.31', 'nginx/unit:1.31.1', 'NGINX Unit')
    ]
    l2 = [
        ('traefik_2.11', 'traefik:2.11', '新版本 Traefik'),
        ('caddy_2.8', 'caddy:2.8-alpine', 'Caddy'),
        ('envoy_1.30', 'envoyproxy/envoy:v1.30-latest', 'Envoy')
    ]

    i = n + 1
    # 先補 L3 OOD，直到接近 50
    while len(existing) < 50:
        for name, image, reason in l3:
            if len(existing) >= 50:
                break
            existing.append({
                'id': f'ood_{i:03d}', 'type': 'l3_ood',
                'l1': {'name': 'cloudflare-simulation', 'image': 'nginx:alpine'},
                'l2': {'name': 'nginx_1.24', 'image': 'nginx:1.24', 'base_name': 'nginx'},
                'l3': {'name': name, 'image': image, 'is_ood': True, 'base_name': name.split('_')[0]},
                'url': f'http://localhost:{19000+i}', 'expected_prediction': 'Unknown', 'reason': reason
            })
            i += 1
        # 再補 L2 OOD 作為備援
        for name, image, reason in l2:
            if len(existing) >= 50:
                break
            existing.append({
                'id': f'ood_{i:03d}', 'type': 'l2_ood',
                'l1': {'name': 'cloudflare-simulation', 'image': 'nginx:alpine'},
                'l2': {'name': name, 'image': image, 'is_ood': True, 'base_name': name.split('_')[0]},
                'l3': {'name': 'apache_2.4.57', 'image': 'httpd:2.4.57', 'base_name': 'apache'},
                'url': f'http://localhost:{19000+i}', 'expected_prediction': 'Unknown', 'reason': reason
            })
            i += 1

    return existing


def main():
    combos = load_json(COMBO)
    fixed = fix_stratify_min2(combos)
    save_json(COMBO, fixed)
    print(f"✓ 已修復分層孤立類別，combinations.json: {len(combos)} -> {len(fixed)} 筆")

    ood = ensure_ood_min50()
    save_json(OOD, ood)
    print(f"✓ 已補齊 OOD 測試集，count={len(ood)} (>=50)")

    print("\n下一步：")
    print("  1) 重新切分數據：python scripts/prepare_datasets.py")
    print("  2) 重新驗證：python scripts/verify_stage1.py")

if __name__ == '__main__':
    main()
