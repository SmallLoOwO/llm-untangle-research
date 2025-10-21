#!/usr/bin/env python3
"""
環境設置與驗證腳本
LLM-UnTangle 專案環境初始化
"""

import sys
import subprocess
import importlib
import os
from pathlib import Path

def check_python_version():
    """檢查 Python 版本"""
    print(f"Python 版本: {sys.version}")
    if sys.version_info < (3, 10):
        print("⚠️  警告：建議使用 Python 3.10+")
        return False
    return True

def test_imports():
    """驗證所有套件是否正確安裝"""
    tests = []
    
    # 測試核心套件
    packages = [
        ('openai', 'OpenAI API'),
        ('faiss', 'FAISS 向量搜尋'),
        ('sentence_transformers', 'Sentence Transformers'),
        ('sklearn', 'Scikit-learn'),
        ('statsmodels.api', 'Statsmodels'),
        ('pandas', 'Pandas'),
        ('numpy', 'NumPy'),
        ('scipy', 'SciPy'),
        ('requests', 'Requests'),
        ('yaml', 'PyYAML'),
        ('tqdm', 'TQDM')
    ]
    
    for package, name in packages:
        try:
            module = importlib.import_module(package)
            version = getattr(module, '__version__', 'Unknown')
            tests.append((name, "✓", version))
        except ImportError as e:
            tests.append((name, "✗", str(e)))
    
    # 輸出結果
    print("\n" + "="*60)
    print("套件安裝驗證結果")
    print("="*60)
    for name, status, info in tests:
        print(f"{name:25s} [{status}] {info}")
    print("="*60 + "\n")
    
    # 檢查是否全部成功
    success_count = sum(1 for _, status, _ in tests if status == "✓")
    print(f"成功安裝: {success_count}/{len(tests)} 個套件")
    
    if success_count == len(tests):
        print("✓ 所有套件安裝成功！")
        return True
    else:
        print("✗ 部分套件安裝失敗，請檢查錯誤訊息")
        return False

def create_project_structure():
    """建立專案目錄結構"""
    directories = [
        'data/raw',
        'data/processed', 
        'data/ood',
        'models/embeddings',
        'models/abr',
        'results/figures',
        'results/tables',
        'docker_configs',
        'docker_configs/ood',
        'docker_configs/custom_errors',
        'notebooks',
        'scripts',
        'tests',
        'logs/docker',
        'logs/experiments'
    ]
    
    print("建立專案目錄結構...")
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {directory}/")
    
    # 建立 .gitignore
    gitignore_content = """
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
env/
ENV/

# Environment Variables
.env
.env.local

# Jupyter Notebook
.ipynb_checkpoints

# Data files
data/raw/*.json
data/processed/*.csv
logs/

# Docker volumes
docker_configs/*/volumes/

# Results
results/figures/*.png
results/figures/*.pdf
results/tables/*.xlsx

# Models
models/embeddings/*.pkl
models/abr/*.index

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
"""
    
    with open('.gitignore', 'w') as f:
        f.write(gitignore_content)
    print("  ✓ .gitignore")
    
    print(f"\n✓ 專案目錄結構建立完成")

def check_docker():
    """檢查 Docker 是否安裝並運行"""
    try:
        result = subprocess.run(['docker', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Docker: {result.stdout.strip()}")
        else:
            print("✗ Docker 未安裝或未運行")
            return False
        
        # 檢查 Docker Compose
        result = subprocess.run(['docker', 'compose', 'version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Docker Compose: {result.stdout.strip()}")
        else:
            print("✗ Docker Compose 未安裝")
            return False
        
        return True
        
    except FileNotFoundError:
        print("✗ Docker 未安裝")
        return False

def main():
    print("✨ LLM-UnTangle 環境設置與驗證")
    print("="*50)
    
    # 檢查 Python 版本
    if not check_python_version():
        return
    
    # 測試套件安裝
    if not test_imports():
        print("\n安裝缺失的套件：")
        print("pip install -r requirements.txt")
        return
    
    # 建立專案結構
    create_project_structure()
    
    # 檢查 Docker
    print("\n檢查 Docker 環境...")
    if check_docker():
        print("✓ Docker 環境正常")
    else:
        print("⚠️  請先安裝 Docker 和 Docker Compose")
    
    print("\n✓ 環境設置完成！")
    print("\n下一步：")
    print("1. 設置 OpenAI API 金鑰: export OPENAI_API_KEY='your-key'")
    print("2. 執行: python scripts/generate_combinations.py")
    print("3. 啟動 Docker 環境: ./scripts/start_all_dockers.sh")

if __name__ == "__main__":
    main()