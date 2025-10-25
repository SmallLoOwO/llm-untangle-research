@echo off
REM 方案 A：多版本擴展策略執行腳本
REM 從 96 組合擴展到 780+ 組合
REM 實現公式：L1_instances × L2_instances × L3_instances = 6 × 13 × 10 = 780

echo =====================================
echo 🚀 方案 A：多版本擴展策略
echo =====================================
echo.
echo 目標：實現 780 組三層架構組合 (6×13×10)
echo 特色：多版本伺服器部署、CDN模擬、版本分化錯誤處理
echo.

REM 檢查 Python 環境
echo 步驟 1: 檢查 Python 環境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 錯誤：找不到 Python。請安裝 Python 3.8+
    pause
    exit /b 1
)
echo ✓ Python 環境正常

REM 檢查 Docker
echo 步驟 2: 檢查 Docker 環境...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 錯誤：找不到 Docker。請安裝 Docker Desktop
    pause
    exit /b 1
)
echo ✓ Docker 環境正常

REM 安裝依賴
echo 步驟 3: 安裝 Python 依賴包...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ❌ 錯誤：依賴安裝失敗
    pause
    exit /b 1
)
echo ✓ 依賴安裝完成

REM 生成多版本組合
echo.
echo 步驟 4: 生成多版本伺服器組合 (780 組)...
python scripts\generate_multi_version_sets.py
if %errorlevel% neq 0 (
    echo ❌ 錯誤：組合生成失敗
    pause
    exit /b 1
)
echo ✓ 多版本組合生成完成

REM 生成 Docker 配置
echo.
echo 步驟 5: 生成 Docker Compose 配置檔...
python scripts\generate_multi_version_docker_configs.py
if %errorlevel% neq 0 (
    echo ❌ 錯誤：Docker 配置生成失敗
    pause
    exit /b 1
)
echo ✓ Docker 配置生成完成

REM 驗證結果
echo.
echo 步驟 6: 驗證生成結果...
if exist "data\multi_version_combinations.json" (
    echo ✓ 組合数據檔存在
) else (
    echo ❌ 錯誤：組合数據檔不存在
    pause
    exit /b 1
)

if exist "docker_configs_multi_version" (
    echo ✓ Docker 配置目錄存在
) else (
    echo ❌ 錯誤：Docker 配置目錄不存在
    pause
    exit /b 1
)

REM 顯示結果統計
echo.
echo =====================================
echo ✅ 方案 A 實施完成！
echo =====================================
echo.

REM 讀取結果統計
( 
for /f "tokens=*" %%i in ('python -c "import json; data=json.load(open('data/multi_version_combinations.json', encoding='utf-8')); print(f'{data[\"metadata\"][\"total_combinations\"]},{data[\"metadata\"][\"selected_for_testing\"]},{data[\"metadata\"][\"l1_instances\"]},{data[\"metadata\"][\"l2_instances\"]},{data[\"metadata\"][\"l3_instances\"]}')"') do (
    for /f "tokens=1,2,3,4,5 delims=," %%a in ("%%i") do (
        echo 📈 結果統計：
        echo    總組合數：    %%a 組
        echo    測試組合：    %%b 組
        echo    L1 實例：     %%c 個
        echo    L2 實例：     %%d 個
        echo    L3 實例：     %%e 個
        echo    公式：       %%c × %%d × %%e = %%a
    )
)
)

echo.
echo 🔍 與 Untangle 比較：
echo    Untangle：        756 組合
echo    方案 A：         780 組合
echo    改進幅度：       +24 組合 (+3.2%%)
echo.

echo 📦 生成的檔案：
echo    • data\multi_version_combinations.json  (組合數據)
echo    • docker_configs_multi_version\        (780個Docker配置)
echo    • docker_configs_multi_version\configs\ (伺服器配置範本)
echo.

echo 🚀 下一步操作：
echo    1. 進入配置目錄： cd docker_configs_multi_version
echo    2. 測試單一組合：   docker compose -f compose_combo_001.yml up -d
echo    3. 批次測試：       .\start_testing_batch.sh
echo    4. 模擬攻擊測試：   python ..\scripts\run_probe_attacks.py
echo.

echo ℹ️  提示：這個方案通過部署不同版本的同一伺服器，
echo     在錯誤處理上產生細微差異，從而測試 SRM 的魏棒性。
echo.

REM 提供選項繼續
echo 🔄 您想現在執行什麼操作？
echo    [1] 測試單一組合
echo    [2] 啟動所有測試組合
echo    [3] 查看詳細統計
echo    [4] 離開
echo.
set /p choice=請輸入選項 [1-4]: 

if "%choice%"=="1" (
    echo 啟動第一個測試組合...
    cd docker_configs_multi_version
    docker compose -f compose_combo_001.yml up -d
    cd ..
    echo ✓ 組合 combo_001 已啟動，請訪問 http://localhost:8001
    pause
) else if "%choice%"=="2" (
    echo 批次啟動所有測試組合...
    cd docker_configs_multi_version
    call start_testing_batch.sh
    cd ..
    echo ✓ 所有測試組合已啟動
    pause
) else if "%choice%"=="3" (
    echo 查看詳細統計...
    python -c "
import json
with open('data/multi_version_combinations.json', encoding='utf-8') as f:
    data = json.load(f)
print('\n📈 詳細統計報告：')
print('=' * 40)
print(f'總組合數： {data["metadata"]["total_combinations"]}')
print(f'測試組合： {data["metadata"]["selected_for_testing"]}')
print(f'L1 CDN 模擬： {len(data["server_instances"]["l1_cdns"])} 種')
print(f'L2 代理伺服器： {len(data["server_instances"]["l2_proxies"])} 種')
print(f'L3 後端伺服器： {len(data["server_instances"]["l3_servers"])} 種')
print('\n伺服器版本分布：')
for layer, servers in data['server_instances'].items():
    print(f'{layer}:')
    for server in servers:
        if 'version' in server:
            print(f'  {server["name"]}: v{server["version"]}')
        else:
            print(f'  {server["name"]}')
    "
    pause
)

echo.
echo 謝謝使用 LLM-UnTangle 多版本擴展策略！
pause