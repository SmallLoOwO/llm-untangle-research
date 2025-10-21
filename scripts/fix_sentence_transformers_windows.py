#!/usr/bin/env python3
"""
Windows 專用：修復 sentence-transformers 在 venv 中的 torch DLL 問題檢測與自動修復。
步驟：
1) 嘗試 import sentence_transformers
2) 若出現 WinError 1114 / c10.dll 錯誤：
   - 卸載 torch/torchvision/torchaudio
   - 安裝 CPU 版 torch 套件
   - 重新嘗試 import
3) 結果輸出到終端並以退出碼表示成功或失敗
"""
import subprocess
import sys


def run(cmd):
    print(f"$ {cmd}")
    p = subprocess.run(cmd, shell=True)
    return p.returncode


def try_import():
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
        print("OK: sentence-transformers 匯入成功")
        return True
    except Exception as e:
        print("IMPORT ERROR:", e)
        return False


def fix_windows_cpu_torch():
    # 卸載 GPU 版或不相容版本
    run("pip uninstall -y torch torchvision torchaudio")
    # 安裝 CPU 版
    returncode = run("pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio")
    if returncode != 0:
        print("安裝 CPU 版 torch 失敗，請手動檢查網路或權限")
        return False
    # 確保 sentence-transformers 存在
    run("pip install -U sentence-transformers")
    return True


def main():
    ok = try_import()
    if ok:
        sys.exit(0)

    print("檢測到 sentence-transformers/Torch DLL 問題，開始自動修復...")
    if not fix_windows_cpu_torch():
        sys.exit(1)

    # 再次測試
    ok2 = try_import()
    sys.exit(0 if ok2 else 1)


if __name__ == "__main__":
    main()
