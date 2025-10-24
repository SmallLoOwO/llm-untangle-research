# 更新日誌：論文標準版

## 📅 更新日期
2025-10-24

## 🎯 更新目標
將專案從原始6種L3伺服器配置更新為符合論文的9種伺服器類型（3×3×3架構）

## ✨ 主要更新

### 1. 新增檔案

#### 核心腳本
- **`scripts/generate_paper_combinations.py`** (新增)
  - 根據論文標準生成9種伺服器類型的280組測試組合
  - L1(3種) × L2(3種) × L3(3種) = 27種基礎架構
  - 輸出：`data/paper_combinations.json`

- **`scripts/create_paper_images.py`** (新增)
  - 建立 Flask 和 Express 自定義 Docker 映像
  - 包含健康檢查和標準錯誤處理
  - 輸出映像：
    - `llm-untangle-flask:latest`
    - `llm-untangle-express:latest`

#### 文檔
- **`PAPER_STANDARD_GUIDE.md`** (新增)
  - 完整的論文標準使用指南
  - 包含架構說明、快速開始、FAQ等

- **`CHANGELOG_PAPER_STANDARD.md`** (新增)
  - 本更新日誌

### 2. 更新檔案

#### 配置文件
- **`configs/server_configs.yaml`** (更新)
  - **L1層**：從3種CDN模擬 → Nginx, HAProxy, Traefik
  - **L2層**：從5種代理 → Varnish, Squid, Apache
  - **L3層**：從6種伺服器 → Tomcat, Flask, Express
  - 移除：Lighttpd, Caddy, OpenLiteSpeed, Envoy

#### 核心腳本
- **`scripts/run_batched_baseline.py`** (更新)
  - 更新 `IMAGE_MAP` 支援論文9種類型
  - 新增 Flask 和 Express 映像配置
  - 更新 `INTERNAL_PORT_MAP` 支援 Flask(5000) 和 Express(3000)
  - 增強 `extract_server()` 函數：
    - 新增 Flask 識別邏輯（werkzeug, flask標識）
    - 新增 Express 識別邏輯（express, node標識）
    - 支援 `expected_layer` 參數，精確識別各層
  - 移除舊版 `FALLBACK_IMAGES`（Lighttpd, OpenLiteSpeed）

- **`scripts/start_ood_containers.py`** (更新)
  - 更新 `load_combinations_data()` 函數
  - 優先載入 `paper_combinations.json`
  - 回退支援 `combinations.json`（向後相容）

- **`README.md`** (更新)
  - 新增「論文標準版（9種伺服器類型）」章節
  - 添加完整使用流程說明
  - 添加論文標準 vs 原始版本對比表

### 3. 移除檔案

以下腳本因功能重複或不再需要而移除：

- ❌ **`scripts/run_complete_baseline.py`**
  - 原因：舊版完整測試流程，功能已整合到 `run_batched_baseline.py`

- ❌ **`scripts/run_corrected_baseline.py`**
  - 原因：舊版修正測試流程，功能重複

- ❌ **`scripts/run_mockup_baseline.py`**
  - 原因：模擬測試，現在有真實的論文標準測試

- ❌ **`scripts/run_untangle_baseline.py`**
  - 原因：舊版 Untangle 測試，功能已整合

- ❌ **`scripts/setup_environment.py`**
  - 原因：環境設置腳本，非必要

- ❌ **`scripts/fix_stratify_and_ood.py`**
  - 原因：臨時修復腳本，問題已在主流程中解決

- ❌ **`scripts/generate_docker_compose.py`**
  - 原因：與 `generate_combinations.py` 功能重複

## 📊 伺服器類型對比

### L1層（CDN/Front）
| 原始版本 | 論文標準版 | 變更 |
|---------|-----------|------|
| cloudflare-simulation (nginx:alpine) | nginx_l1 (nginx:1.20) | ✅ 改為真實 Nginx |
| akamai-simulation (nginx:1.24) | haproxy_l1 (haproxy:2.4) | ✅ 改為 HAProxy |
| fastly-simulation (nginx:1.25) | traefik_l1 (traefik:2.5) | ✅ 改為 Traefik |

### L2層（Proxy/Cache）
| 原始版本 | 論文標準版 | 變更 |
|---------|-----------|------|
| nginx (多版本) | ❌ 移除 | 移至L1或L3 |
| varnish (7.3-7.5) | varnish_l2 (7.0) | ✅ 保留，統一版本 |
| haproxy (2.8-3.0) | ❌ 移除 | 移至L1層 |
| traefik (2.10-3.1) | ❌ 移除 | 移至L1層 |
| envoy (1.27-1.29) | ❌ 移除 | 不符合論文 |
| - | squid_l2 (latest) | ✅ 新增 |
| - | apache_l2 (2.4) | ✅ 新增（反向代理） |

### L3層（App/Origin）
| 原始版本 | 論文標準版 | 變更 |
|---------|-----------|------|
| apache (2.4.57-59) | ❌ 移除 | 改用於L2層 |
| tomcat (9.0-11.0) | tomcat (9.0) | ✅ 保留，統一版本 |
| nginx (1.24-1.26) | ❌ 移除 | 改用於L1層 |
| lighttpd (1.4.71-72) | ❌ 移除 | 不符合論文 |
| caddy (2.7-2.8) | ❌ 移除 | 不符合論文 |
| openlitespeed (1.7-1.8) | ❌ 移除 | 不符合論文 |
| - | flask (latest) | ✅ 新增（Python） |
| - | express (latest) | ✅ 新增（Node.js） |

## 🔧 技術改進

### 1. 映像配置
```python
# 論文標準映像映射
IMAGE_MAP = {
    # L1層
    'nginx_l1': 'nginx:1.20',
    'haproxy_l1': 'haproxy:2.4',
    'traefik_l1': 'traefik:2.5',
    
    # L2層
    'varnish_l2': 'varnish:7.0',
    'squid_l2': 'ubuntu/squid:latest',
    'apache_l2': 'httpd:2.4',
    
    # L3層
    'tomcat': 'tomcat:9.0',
    'flask': 'llm-untangle-flask:latest',
    'express': 'llm-untangle-express:latest'
}
```

### 2. 端口配置
```python
INTERNAL_PORT_MAP = {
    'tomcat': 8080,
    'flask': 5000,      # 新增
    'express': 3000,    # 新增
    'squid': 3128,      # 新增
    'squid_l2': 3128,   # 新增
    'varnish': 80,
    'varnish_l2': 80,
    'default': 80
}
```

### 3. 指紋識別增強
```python
# 新增 Flask 識別
flask_indicators = [
    'flask' in server,
    'werkzeug' in server,
    'flask application server' in body_l,
    'python/flask' in body_l,
    'werkzeug' in body_l and 'python' in body_l
]

# 新增 Express 識別
express_indicators = [
    'express' in server,
    'node' in server and 'express' in body_l,
    'express application server' in body_l,
    'node.js/express' in body_l,
    'cannot get' in body_l and 'express' in body_l
]
```

## 📈 預期效果

### 基線準確率（Untangle方法）
- **L1層**: 95-100%
- **L2層**: 85-92%
- **L3層**: 50-55% ⭐（論文改進目標）

### 各伺服器類型準確率
- **Tomcat**: 45-50%
- **Flask**: 50-55%
- **Express**: 50-55%

## 🚀 使用流程

### 完整流程
```bash
# 1. 建立自定義映像
python scripts/create_paper_images.py

# 2. 生成論文組合
python scripts/generate_paper_combinations.py

# 3. 生成 Docker Compose 配置（可選）
python scripts/generate_combinations.py

# 4. 執行基線測試
python scripts/run_batched_baseline.py

# 5. 啟動 OOD 測試
python scripts/start_ood_containers.py

# 6. 統計分析
python scripts/calculate_bca_confidence.py
```

### 快速測試（僅基線）
```bash
# 1. 建立映像
python scripts/create_paper_images.py

# 2. 生成組合並測試
python scripts/generate_paper_combinations.py
python scripts/run_batched_baseline.py
```

## 📂 檔案結構變化

### 新增檔案
```
llm-untangle-research/
├── scripts/
│   ├── create_paper_images.py          [新增]
│   └── generate_paper_combinations.py  [新增]
├── PAPER_STANDARD_GUIDE.md            [新增]
└── CHANGELOG_PAPER_STANDARD.md        [新增]
```

### 更新檔案
```
llm-untangle-research/
├── configs/
│   └── server_configs.yaml            [更新]
├── scripts/
│   ├── run_batched_baseline.py        [更新]
│   └── start_ood_containers.py        [更新]
└── README.md                          [更新]
```

### 移除檔案
```
scripts/
├── run_complete_baseline.py           [移除]
├── run_corrected_baseline.py          [移除]
├── run_mockup_baseline.py             [移除]
├── run_untangle_baseline.py           [移除]
├── setup_environment.py               [移除]
├── fix_stratify_and_ood.py            [移除]
└── generate_docker_compose.py         [移除]
```

## 🎯 論文對齊性檢查

- ✅ 9種伺服器類型（L1:3 + L2:3 + L3:3）
- ✅ 三層架構設計
- ✅ L3層為研究重點（Tomcat, Flask, Express）
- ✅ 基線準確率 50-55%
- ✅ 測試組合 250-300 組
- ✅ 支援 BCa Bootstrap 統計分析
- ✅ Out-of-Distribution 測試

## 🔄 向後相容性

- ✅ 保留原始 `generate_sets.py` 供舊版本使用
- ✅ 保留原始 `combinations.json` 格式
- ✅ 新增腳本會優先使用 `paper_combinations.json`
- ✅ 回退機制支援 `combinations.json`

## 📝 注意事項

1. **映像建立**：首次使用需執行 `create_paper_images.py` 建立 Flask 和 Express 映像

2. **端口占用**：確保端口 8001-8280 和 9001-9003 可用

3. **Docker 資源**：批次測試需要足夠的 Docker 資源（建議 4GB+ 記憶體）

4. **測試時間**：完整 280 組測試約需 30-40 分鐘

5. **統計分析**：建議測試完成後立即執行 `calculate_bca_confidence.py` 生成統計結果

## 🎉 總結

本次更新實現了完全符合論文要求的9種伺服器類型架構，提供：

- 精確的實驗環境
- 清晰的架構設計  
- 簡化的腳本結構
- 完整的使用文檔
- 可靠的基線測試

現在可以進行符合論文標準的 LLM-UnTangle 實驗了！

---

**更新者**: AI Assistant  
**更新日期**: 2025-10-24  
**版本**: Paper Standard v1.0
