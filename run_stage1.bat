@echo off
chcp 65001 >nul
setlocal

echo 🚀 LLM-UnTangle 第一階段執行腳本
echo ================================================

echo ✨ 步驟 1: 檢查環境
if not exist venv (
    echo ⚠️  請先建立虛擬環境: python -m venv venv
    pause
    exit /b 1
)

echo ✓ 啟動虛擬環境
call venv\Scripts\activate.bat

echo ✨ 步驟 2: 更新本地檔案
echo 正在拉取最新版本...
git pull origin main
if errorlevel 1 (
    echo ⚠️  Git 更新失敗，嘗試強制重設...
    git fetch origin main
    git reset --hard origin/main
)

echo ✨ 步驟 3: 生成伺服器組合
cd /d "%~dp0"
python scripts\generate_sets.py
if errorlevel 1 (
    echo ❌ 組合生成失敗
    pause
    exit /b 1
)

echo ✨ 步驟 4: 準備數據集
python scripts\prepare_datasets.py
if errorlevel 1 (
    echo ❌ 數據集準備失敗
    pause
    exit /b 1
)

echo ✨ 步驟 5: 生成 Docker 配置
python scripts\generate_combinations.py
if errorlevel 1 (
    echo ❌ Docker 配置生成失敗
    pause
    exit /b 1
)

echo.
echo 🎉 第一階段完成！
echo.
echo 📋 結果檔案:
echo    - data\combinations.json (伺服器組合)
echo    - data\processed\*.csv (訓練/驗證/測試集)
echo    - data\ood\*.json (OOD 測試集)
echo    - docker_configs\*.yml (Docker 配置)
echo.
echo 下一步: 啟動 Docker 環境
echo    docker compose -f docker_configs\compose_combo_001.yml up -d
echo.
pause