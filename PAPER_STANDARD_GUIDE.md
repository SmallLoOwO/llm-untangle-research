# LLM-UnTangle 論文標準使用指南

## 📋 概述

本專案已更新為符合論文的9種伺服器類型架構，提供更精確的實驗環境和基線測試。

## 🏗️ 架構說明

### 9種伺服器類型

根據論文設計，系統使用3層架構，每層3種伺服器類型：

#### L1層（CDN/Front）
- **Nginx** (nginx:1.20)
- **HAProxy** (haproxy:2.4)
- **Traefik** (traefik:2.5)

#### L2層（Proxy/Cache）
- **Varnish** (varnish:7.0)
- **Squid** (ubuntu/squid:latest)
- **Apache** (httpd:2.4) - 作為反向代理

#### L3層（App/Origin）- 論文重點
- **Tomcat** (tomcat:9.0) - Java應用伺服器
- **Flask** (llm-untangle-flask:latest) - Python應用框架
- **Express** (llm-untangle-express:latest) - Node.js應用框架

### 組合數量
- 基礎架構類型：3 × 3 × 3 = **27種**
- 總測試組合：**280組**
- 每種架構約有 10 個實例

## 🚀 快速開始

### 步驟1：建立自定義映像

```bash
python scripts/create_paper_images.py
```

**功能：**
- 建立 Flask 應用伺服器映像（Python/Flask）
- 建立 Express 應用伺服器映像（Node.js/Express）
- 包含健康檢查端點和錯誤處理

**輸出：**
- `llm-untangle-flask:latest`
- `llm-untangle-express:latest`

### 步驟2：生成論文標準組合

```bash
python scripts/generate_paper_combinations.py
```

**功能：**
- 生成符合論文的280組三層組合
- 確保9種伺服器類型均勻分佈
- 自動分配端口（8001-8280）

**輸出：**
- `data/paper_combinations.json`

**統計分布：**
```
L3層分布（論文重點）:
  express: 94 組 (33.6%)
  flask: 93 組 (33.2%)
  tomcat: 93 組 (33.2%)

架構類型總數: 27 種
```

### 步驟3：生成 Docker Compose 配置

```bash
python scripts/generate_combinations.py
```

**功能：**
- 為每組組合生成獨立的 Docker Compose 文件
- 配置三層服務依賴關係
- 自動端口映射

**輸出：**
- `docker_configs/compose_combo_*.yml`（280個文件）

### 步驟4：執行基線測試

```bash
python scripts/run_batched_baseline.py
```

**功能：**
- 批次啟動容器（10個/批）
- 自動健康檢查
- L3層指紋識別測試
- 自動清理容器

**預期結果：**
- L3 準確率：50-55%（符合論文 Untangle 基線）
- 測試完成時間：約 30-40 分鐘（280組）

**輸出：**
- `results/untangle_batched_results_*.json`

### 步驟5：啟動 OOD 測試

```bash
python scripts/start_ood_containers.py
```

**功能：**
- 啟動3個 Out-of-Distribution 測試容器
- 生成基線測試目標清單
- 驗證 OOD 檢測能力

**輸出：**
- `results/ood_containers_status.json`
- `results/baseline_targets.json`

### 步驟6：統計分析

```bash
python scripts/calculate_bca_confidence.py
```

**功能：**
- BCa Bootstrap 置信區間計算
- 生成論文統計結果
- 各伺服器類型準確率分析

## 📊 論文標準 vs 原始版本對比

| 項目 | 原始版本 | 論文標準版 | 改進 |
|------|----------|------------|------|
| **L1 伺服器** | 3種 CDN模擬（皆為Nginx） | Nginx, HAProxy, Traefik | ✅ 真實多樣性 |
| **L2 伺服器** | 5種（Nginx, Varnish, HAProxy, Traefik, Envoy） | Varnish, Squid, Apache | ✅ 符合論文 |
| **L3 伺服器** | 6種（Apache, Tomcat, Nginx, Lighttpd, Caddy, OLS） | Tomcat, Flask, Express | ✅ 論文重點 |
| **總架構** | 不明確 | 27種明確架構 | ✅ 結構清晰 |
| **測試重點** | 全層級 | L3應用層 | ✅ 論文對齊 |

## 🎯 核心改進

### 1. 符合論文設計
- 精確的9種伺服器類型
- 3×3×3 架構設計
- L3層為研究重點

### 2. 增強的指紋識別
```python
# 新增 Flask 識別邏輯
flask_indicators = [
    'flask' in server,
    'werkzeug' in server,
    'flask application server' in body_l,
    'python/flask' in body_l
]

# 新增 Express 識別邏輯
express_indicators = [
    'express' in server,
    'node' in server and 'express' in body_l,
    'express application server' in body_l,
    'cannot get' in body_l and 'express' in body_l
]
```

### 3. 自定義應用服務器
- Flask 應用包含健康檢查端點
- Express 應用包含標準錯誤處理
- 容器化配置優化

### 4. 簡化的腳本結構
**保留的核心腳本：**
- `generate_sets.py` - 原始組合生成（舊版相容）
- `prepare_datasets.py` - 數據集劃分
- `generate_combinations.py` - Docker Compose 生成
- `verify_stage1.py` - 環境驗證
- `generate_paper_combinations.py` - **論文標準組合生成**
- `create_paper_images.py` - **自定義映像構建**
- `run_batched_baseline.py` - **基線測試**（已更新）
- `start_ood_containers.py` - OOD 測試（已更新）
- `calculate_bca_confidence.py` - 統計分析

**已移除的重複腳本：**
- ❌ `run_complete_baseline.py`
- ❌ `run_corrected_baseline.py`
- ❌ `run_mockup_baseline.py`
- ❌ `run_untangle_baseline.py`
- ❌ `setup_environment.py`
- ❌ `fix_stratify_and_ood.py`
- ❌ `generate_docker_compose.py`

## 📁 文件結構

```
llm-untangle-research/
├── configs/
│   └── server_configs.yaml          # 已更新為9種伺服器類型
├── data/
│   ├── combinations.json            # 舊版組合（舊版相容）
│   └── paper_combinations.json      # 論文標準組合（新）
├── scripts/
│   ├── create_paper_images.py       # 新增：自定義映像構建
│   ├── generate_paper_combinations.py  # 新增：論文組合生成
│   ├── run_batched_baseline.py      # 更新：支援9種類型
│   ├── start_ood_containers.py      # 更新：論文組合
│   └── ... (其他核心腳本)
└── README.md                        # 已更新使用說明
```

## 🔧 配置詳情

### server_configs.yaml 更新

```yaml
servers:
  l1_cdns:  # L1層（CDN/Front）
    - name: nginx_l1
      image: nginx:1.20
    - name: haproxy_l1  
      image: haproxy:2.4
    - name: traefik_l1
      image: traefik:2.5
    
  l2_proxies:  # L2層（Proxy/Cache）
    - name: varnish
      versions: ["7.0"]
      image: varnish:{version}
    - name: squid
      versions: ["latest"]
      image: ubuntu/squid:{version}
    - name: apache
      versions: ["2.4"]
      image: httpd:{version}
    
  l3_servers:  # L3層（App/Origin）
    - name: tomcat  
      versions: ["9.0"]
      image: tomcat:{version}
    - name: flask
      versions: ["latest"]
      image: llm-untangle-flask:{version}
    - name: express
      versions: ["latest"]
      image: llm-untangle-express:{version}
```

## 📈 預期實驗結果

### 基線測試（Untangle方法）
- **L1 準確率**: 95-100%（前端層容易識別）
- **L2 準確率**: 85-92%（代理層中等難度）
- **L3 準確率**: 50-55%（應用層最難，論文改進目標）

### 各伺服器準確率分布
- **Tomcat**: ~45-50%（Java容器特徵少）
- **Flask**: ~50-55%（Python框架標識）
- **Express**: ~50-55%（Node.js框架標識）

## 🎓 論文對齊性

本實現完全符合論文要求：

1. ✅ **9種伺服器類型**：L1(3) + L2(3) + L3(3)
2. ✅ **三層架構**：CDN/Front → Proxy/Cache → App/Origin
3. ✅ **L3層重點**：Tomcat, Flask, Express 為改進目標
4. ✅ **基線準確率**：50-55% 符合 Untangle 原始方法
5. ✅ **測試規模**：250-300組組合
6. ✅ **統計分析**：BCa Bootstrap 置信區間

## 🔍 常見問題

### Q1: 為什麼要建立自定義 Flask 和 Express 映像？
**A:** 官方 Python 和 Node.js 映像不包含預設的 Web 服務器。我們建立自定義映像以：
- 提供標準 HTTP 服務
- 包含健康檢查端點
- 模擬真實應用服務器行為
- 提供可識別的指紋特徵

### Q2: 可以同時使用舊版和論文標準版嗎？
**A:** 可以。系統會優先使用 `paper_combinations.json`，但仍相容 `combinations.json`。

### Q3: 為什麼移除了多個 baseline 測試腳本？
**A:** 這些是開發過程中的迭代版本。`run_batched_baseline.py` 已整合所有功能並支援論文標準。

### Q4: 如何驗證是否使用論文標準？
**A:** 執行測試時，檢查輸出中是否顯示「載入論文標準組合」和「9種伺服器類型」。

## 📞 技術支援

如有問題，請檢查：
1. Docker 是否正常運行
2. 自定義映像是否已建立（`docker images | grep llm-untangle`）
3. 論文組合文件是否存在（`data/paper_combinations.json`）
4. 端口是否被占用（8001-8280, 9001-9003）

## 🎉 總結

論文標準版提供：
- ✅ 精確的9種伺服器類型
- ✅ 清晰的三層架構
- ✅ 符合論文的基線準確率
- ✅ 簡化的腳本結構
- ✅ 完整的實驗流程

現在可以開始進行符合論文標準的 LLM-UnTangle 實驗了！
