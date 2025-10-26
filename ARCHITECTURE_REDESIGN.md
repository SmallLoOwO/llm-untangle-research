# LLM-UnTangle 三層架構重新設計

## 改進背景

根據研究草案分析，原有的Docker環境應該擁有三層，但目前的實驗成功率**只顯示L3 (第三層)的結果**。為了減少錯誤並從最基礎的測試開始驗證可行性，重新設計三層架構。

## 新架構設計

### L1 層 - CDN (固定 1 個實例)
- **伺服器**：Nginx
- **Docker映像檔**：`nginx:1.25-alpine`
- **功能**：模擬CDN行為，添加快取響應頭
- **配置**：作為最外層的請求入口點

### L2 層 - Proxy (固定 1 個實例)
- **伺服器**：Nginx
- **Docker映像檔**：`nginx:1.25-alpine`
- **功能**：反向代理模式，轉發請求至L3
- **配置**：處理代理邏輯和請求轉發

### L3 層 - Server (10 個不同實例)

根據總覽表格，包含以下 10 個伺服器：

| 序號 | 伺服器 | Docker映像檔 | 維護狀態 |
|------|--------|-------------|----------|
| 1 | Nginx | nginx:1.25-alpine | ⭐⭐⭐ 活躍 |
| 2 | Apache | httpd:2.4.57 | ⭐⭐⭐ 活躍 |
| 3 | Tomcat | tomcat:10.1 | ⭐⭐⭐ 活躍 |
| 4 | Caddy | caddy:2.7-alpine | ⭐⭐⭐ 活躍 |
| 5 | Lighttpd | sebp/lighttpd:1.4.59 | ⭐ 第三方 |
| 6 | OpenLiteSpeed | litespeedtech/openlitespeed:1.7 | ⭐⭐ 維護中 |
| 7 | Varnish | varnish:7.4 | ⭐⭐⭐ 活躍 |
| 8 | HAProxy | haproxy:2.8 | ⭐⭐⭐ 活躍 |
| 9 | Squid | ubuntu/squid:5.2 | ⭐⭐ 維護中 |
| 10 | Traefik | traefik:v3.0 | ⭐⭐⭐ 活躍 |

## 組合數計算

```
組合數 = L1_instances × L2_instances × L3_instances
       = 1 × 1 × 10
       = 10 組
```

---

## 安裝與環境 (保持原有步驟)

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

## 執行步驟 (保持原有流程)

### 1) 生成三層組合

```bash
python scripts\generate_sets.py
```
- 產出：`data/combinations.json`（現在為 10 組）
- 已修正確保每個最嚴格分層鍵（L1|L2_base|L3_base）至少 2 筆，避免分層抽樣孤立類別。

### 2) 劃分與產生 OOD 測試集

```bash
python scripts\prepare_datasets.py
```
- 產出：
  - `data/processed/train.csv`
  - `data/processed/val.csv`
  - `data/processed/test.csv`
  - `data/ood/ood_combinations.json`（≥ 50 筆）
- 腳本具備「分層降級」機制，若最細分層出現孤立類別，會自動選擇較寬鬆分層或不分層，確保分割完成。

### 3) 產生 Docker Compose 檔

```bash
python scripts\generate_combinations.py
```
- 產出：`docker_configs/compose_*.yml`（每組一檔）

### 4) 一鍵驗證（Stage 1）

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

### 5) Windows 專用：Torch DLL 修復（選用）
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

---

## 新架構的技術實作特色

### Docker Compose 結構示例

```yaml
version: '3.8'
services:
  l1-cdn:
    image: nginx:1.25-alpine
    container_name: combo_001_l1_nginx
    ports:
      - "8001:80"
    volumes:
      - ./configs/l1_cdn.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - l2-proxy
    networks:
      - app-network

  l2-proxy:
    image: nginx:1.25-alpine
    container_name: combo_001_l2_nginx
    volumes:
      - ./configs/l2_proxy.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - l3-server
    networks:
      - app-network

  l3-server:
    image: nginx:1.25-alpine  # 或其他L3伺服器
    container_name: combo_001_l3_nginx
    volumes:
      - ./configs/l3_server.conf:/etc/nginx/conf.d/default.conf:ro
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

### 驗證方法

```bash
# 啟動特定組合測試
cd docker_configs
docker-compose -f compose_001.yml up -d

# 測試三層穿透
curl http://localhost:8001/test

# 批量測試所有組合
python scripts/start_ood_containers.py
```

## 預期效益

1. **實驗簡化**：從280+組合減少至10組合
2. **系統驗證**：證明請求能夠正常流經L1→L2→L3
3. **指紋識別**：驗證LLM-UnTangle系統能夠識別各層伺服器
4. **錯誤減少**：簡化架構減少系統複雜性

## 常見問題

- 分層策略警告：屬正常降級訊息，不影響最終劃分；請以驗證結果為準。
- OOD 筆數不足：請重新執行 `prepare_datasets.py`，新版本會自動補齊至 ≥ 50。
- 從 `scripts/` 目錄執行：所有腳本已內建路徑修正，亦可於專案根目錄執行。

---

這個新設計將能夠更好地驗證LLM-UnTangle系統在多層環境下的指紋識別能力，同時簡化了實驗複雜度，專注於最基礎的可行性測試。