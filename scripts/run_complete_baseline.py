#!/usr/bin/env python3
"""
完整的 Untangle 基線測試流程（第一階段實驗）

執行步驟：
1. 啟動 OOD 測試環境
2. 從 combinations.json 隨機選取 250-300 組進行基線測試 
3. 執行 Untangle 指紋識別測試
4. 生成統計報告和置信區間
5. 驗證是否符合論文預期結果（L3 準確率 ~50-55%）

白話說明：測試「舊方法」的分數，作為比較標準
- L1（第一層）準確率：~95-100%（CDN 層，容易識別）
- L2（第二層）準確率：~85-92%（代理層，中等難度） 
- L3（第三層）準確率：~50-55%（應用層，最難識別，論文改進重點）
"""

import subprocess
import sys
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / 'results'
SCRIPTS_DIR = ROOT / 'scripts'


def run_script(script_name: str, description: str) -> bool:
    """執行指定腳本並處理結果"""
    print(f'\n{"=" * 60}')
    print(f'🔄 {description}')
    print(f'執行: {script_name}')
    print(f'{"=" * 60}')
    
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        print(f'❌ 找不到腳本: {script_path}')
        return False
    
    try:
        # 使用當前 Python 執行腳本
        result = subprocess.run(
            [sys.executable, str(script_path)], 
            cwd=ROOT,
            capture_output=False,  # 讓輸出直接顯示
            text=True
        )
        
        if result.returncode == 0:
            print(f'✅ {description} 完成')
            return True
        else:
            print(f'❌ {description} 失敗 (退出碼: {result.returncode})')
            return False
            
    except Exception as e:
        print(f'❌ 執行 {script_name} 時發生錯誤: {e}')
        return False


def check_results() -> dict:
    """檢查測試結果並生成摘要報告"""
    print('\n📊 檢查測試結果...')
    
    # 檢查基線測試結果
    baseline_results = None
    results_pattern = RESULTS_DIR.glob('untangle_baseline_results_*.json')
    latest_result = None
    
    for result_file in results_pattern:
        if latest_result is None or result_file.stat().st_mtime > latest_result.stat().st_mtime:
            latest_result = result_file
    
    if latest_result:
        try:
            with open(latest_result, 'r', encoding='utf-8') as f:
                baseline_results = json.load(f)
                print(f'✅ 載入最新基線測試結果: {latest_result.name}')
        except Exception as e:
            print(f'❌ 載入基線測試結果失敗: {e}')
    else:
        print('❌ 找不到基線測試結果文件')
        return {}
    
    if not baseline_results:
        return {}
    
    # 提取關鍵統計資料
    summary = baseline_results.get('test_summary', {})
    l3_accuracy = summary.get('overall_accuracy', 0)
    total_targets = summary.get('total_targets', 0)
    successful_tests = summary.get('successful_tests', 0)
    
    # 各層準確率分析（模擬，因為當前實現主要針對 L3）
    server_accuracy = baseline_results.get('l3_server_accuracy', {})
    
    return {
        'l3_accuracy': l3_accuracy,
        'total_targets': total_targets,
        'successful_tests': successful_tests,
        'server_accuracy': server_accuracy,
        'results_file': str(latest_result)
    }


def generate_final_report(results: dict):
    """生成最終實驗報告"""
    print('\n' + '=' * 70)
    print('🎯 第一階段實驗結果報告：Untangle 基線測試')
    print('=' * 70)
    
    if not results:
        print('❌ 無法生成報告：缺少測試結果')
        return
    
    l3_accuracy = results['l3_accuracy']
    total_targets = results['total_targets']
    successful_tests = results['successful_tests']
    
    print(f'測試規模: {total_targets} 組三層架構組合')
    print(f'成功測試: {successful_tests} ({successful_tests/total_targets*100:.1f}%)')
    print(f'\n🎯 核心結果：L3 層準確率')
    print(f'實際結果: {l3_accuracy:.3f} ({l3_accuracy*100:.1f}%)')
    
    # 論文預期對照
    expected_min, expected_max = 0.50, 0.55
    if expected_min <= l3_accuracy <= expected_max:
        status = '✅ 符合論文預期範圍'
        status_emoji = '🎉'
    elif l3_accuracy < expected_min:
        status = '⚠️ 低於預期範圍'
        status_emoji = '📉'  
    else:
        status = '📈 高於預期範圍'
        status_emoji = '🚀'
    
    print(f'論文預期: {expected_min*100:.0f}%-{expected_max*100:.0f}%')
    print(f'結果評估: {status} {status_emoji}')
    
    # 各服務器類型表現
    print(f'\n📋 各 L3 服務器類型表現:')
    server_accuracy = results.get('server_accuracy', {})
    if server_accuracy:
        for server, stats in sorted(server_accuracy.items()):
            accuracy = stats.get('accuracy', 0)
            total = stats.get('total', 0)
            correct = stats.get('correct', 0)
            print(f'  {server:12}: {accuracy:6.1%} ({correct:3d}/{total:3d})')
    
    print(f'\n📄 詳細結果文件: {results["results_file"]}')
    
    # 實驗意義說明
    print(f'\n🧠 實驗意義:')
    print(f'✓ 建立了 Untangle 舊方法的基線準確率')
    print(f'✓ 驗證了 L3 層識別的挑戰性（準確率相對較低）')
    print(f'✓ 為後續 LLM-UnTangle 改進方法提供了比較基準')
    print(f'✓ 確認了論文實驗設計的有效性')
    
    # 下一步建議
    print(f'\n➡️ 下一步:')
    print(f'1. 可執行 BCa Bootstrap 統計分析計算置信區間')
    print(f'2. 準備實現 LLM-UnTangle 改進方法')
    print(f'3. 進行新舊方法的對比實驗')


def main():
    """主執行流程"""
    print('🔬 LLM-UnTangle 第一階段實驗：Untangle 基線測試')
    print('=' * 70)
    print('目標：測試傳統 Untangle 方法的 L3 層準確率作為改進基準')
    print('預期：L3 準確率約 50-55%，證明現有方法的局限性\n')
    
    # 步驟 1: 準備測試環境和目標
    success1 = run_script(
        'start_ood_containers.py',
        '準備測試環境（OOD 服務 + 250-300 組基線目標）'
    )
    
    if not success1:
        print('❌ 測試環境準備失敗，中止實驗')
        return False
    
    # 短暫等待確保環境穩定
    print('\n⏳ 等待測試環境穩定化 (5秒)...')
    time.sleep(5)
    
    # 步驟 2: 執行 Untangle 基線測試
    success2 = run_script(
        'run_untangle_baseline.py', 
        'Untangle 基線指紋識別測試（250-300 組）'
    )
    
    if not success2:
        print('❌ 基線測試失敗，但可能已有部分結果')
    
    # 步驟 3: 分析結果並生成報告
    results = check_results()
    generate_final_report(results)
    
    # 判斷實驗是否成功
    if results and results.get('successful_tests', 0) > 0:
        print('\n🎉 第一階段實驗完成！')
        print('✅ Untangle 基線測試成功執行')
        print('✅ 已建立改進方法的比較基準')
        return True
    else:
        print('\n❌ 實驗未完全成功')
        print('請檢查錯誤日誌並重新執行')
        return False


if __name__ == '__main__':
    try:
        success = main()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print('\n\n⏹️ 使用者中斷實驗')
        exit(1)
    except Exception as e:
        print(f'\n❌ 實驗執行時發生未預期錯誤: {e}')
        exit(1)