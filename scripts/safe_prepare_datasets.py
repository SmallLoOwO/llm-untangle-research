#!/usr/bin/env python3
"""
修復版：在 scripts 目錄執行時，自動回到專案根目錄查找 data/combinations.json
若找不到則提供明確錯誤訊息與提示
"""
import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from collections import Counter

# 1) 確保當前工作目錄是專案根目錄
if os.path.basename(os.getcwd()) == 'scripts':
    os.chdir('..')
    print('✓ 已切換到專案根目錄 (為了讀取 data/combinations.json)')

COMBO_PATH = Path('data/combinations.json')

if not COMBO_PATH.exists():
    raise FileNotFoundError(
        '找不到 data/combinations.json。\n'
        '請先執行: python scripts/generate_sets.py 來生成組合清單。\n'
        '若已執行，請確認目前的工作目錄在專案根目錄（包含 data/ 資料夾）。'
    )

# 2) 其餘內容直接導入原本的 prepare_datasets.py
from scripts.prepare_datasets import (
    load_combinations,
    create_ground_truth_labels,
    stratified_split,
    verify_split_quality,
    create_ood_dataset,
    verify_ood_diversity,
    save_datasets,
)


def main():
    print('✨ LLM-UnTangle 數據集劃分與 OOD 設計 (修復版入口)')
    print('=' * 55)

    # 1. 載入原始組合
    combinations = load_combinations()
    print(f'載入 {len(combinations)} 組組合')

    # 2. 建立地面真相標籤
    df = create_ground_truth_labels(combinations)

    # 3. 劃分數據集
    train_df, val_df, test_df = stratified_split(
        df, train_size=0.6, val_size=0.2, test_size=0.2, random_state=42
    )

    # 4. 驗證劃分品質
    if verify_split_quality(train_df, val_df, test_df):
        print('✓ 數據集劃分品質優秀')
    else:
        print('⚠️  數據集劃分品質需要改進')

    # 5. 建立 OOD 測試集
    ood_combinations = create_ood_dataset()
    verify_ood_diversity(ood_combinations)

    # 6. 儲存結果
    save_datasets(train_df, val_df, test_df, ood_combinations)

    print('\n✓ 數據集準備完成！')
    print('\n下一步：')
    print('  python scripts/run_untangle_baseline.py')


if __name__ == '__main__':
    main()
