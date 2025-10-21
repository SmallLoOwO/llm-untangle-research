# llm-untangle-research
LLM-UnTangle：基於大型語言模型之多層 Web 伺服器指紋識別系統研究專案

---

## 第一階段：準備與驗證

本階段完成以下目標：
- 產生三層架構組合（L1 CDN/L2 Proxy/L3 App）並保存於 `data/combinations.json`
- 進行資料集劃分（train/val/test ≈ 60/20/20）與 OOD 測試集產生（≥ 50）
- 自動生成每個組合的 Docker Compose 檔案
- 使用一鍵驗證腳本確認環境與產出

### 1) 安裝與環境

- Python 3.10+（建議 3.11）
- Windows 使用者建議先安裝 Docker Desktop

建立虛擬環境並安裝依賴：
```bash
# Windows PowerShell / CMD
python -m venv venv
venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt  # 若不存在，可先執行至後續步驟，缺啥再補裝
```

### 2) 生成三層組合

```bash
python scripts\generate_sets.py
```
- 產出：`data/combinations.json`（約 280 組）
- 已修正確保每個最嚴格分層鍵（L1|L2_base|L3_base）至少 2 筆，避免分層抽樣孤立類別。

### 3) 劃分與產生 OOD 測試集

```bash
python scripts\prepare_datasets.py
```
- 產出：
  - `data/processed/train.csv`
  - `data/processed/val.csv`
  - `data/processed/test.csv`
  - `data/ood/ood_combinations.json`（≥ 50 筆）
- 腳本具備「分層降級」機制，若最細分層出現孤立類別，會自動選擇較寬鬆分層或不分層，確保分割完成。

### 4) 產生 Docker Compose 檔

```bash
python scripts\generate_combinations.py
```
- 產出：`docker_configs/compose_*.yml`（每組一檔）

### 5) 一鍵驗證（Stage 1）

```bash
python scripts\verify_stage1.py
```
- 檢查內容：
  - Python 與關鍵套件（pandas、numpy、scikit-learn、faiss-cpu、statsmodels、mapie、sentence-transformers）
  - Docker 與 Docker Compose
  - `data/combinations.json` 計數
  - 分割比例（60/20/20）
  - OOD 計數（≥ 50）
  - `docker_configs` 檔案數量（≥ 1）
- 結果輸出：`results/stage1_checklist.json`
- Windows 上 `sentence-transformers` 可能因 Torch DLL 顯示 WARN，不影響總結 PASS。

### Windows 專用：Torch DLL 修復（選用）
若需要在本機執行 NLP/嵌入推論，且遇到 `c10.dll` 錯誤，可執行：
```bash
python scripts\fix_sentence_transformers_windows.py
```
或手動安裝 CPU 版 Torch：
```bash
pip uninstall -y torch torchvision torchaudio
pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio
pip install -U sentence-transformers
```

### 常見問題
- 分層策略警告：屬正常降級訊息，不影響最終劃分；請以驗證結果為準。
- OOD 筆數不足：請重新執行 `prepare_datasets.py`，新版本會自動補齊至 ≥ 50。
- 從 `scripts/` 目錄執行：所有腳本已內建路徑修正，亦可於專案根目錄執行。

---

## 下一階段（預告）
- 啟動單組或多組 Docker 服務進行流量/標頭收集與指紋識別驗證
- 建立模型訓練/推論管線（可於 Docker 內或雲端環境執行）
