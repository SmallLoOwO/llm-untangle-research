# 第一階段完成檢查清單（Checklist）

此檔案用於快速確認「第一階段：基礎環境與數據準備」是否完成。可直接在專案根目錄執行指令來檢查每一項目。

---

## 一、環境就緒

- [ ] Python 3.10+ 與虛擬環境啟用
```
python --version
# 預期: 3.10 或以上

# Windows 啟用 venv
venv\Scripts\activate
```

- [ ] 依賴安裝完成
```
pip install -r requirements.txt
python scripts\setup_environment.py
# 預期: 套件驗證皆為 [✓]
```

- [ ] Docker Desktop 正常
```
docker --version
docker run hello-world
# 預期: Hello from Docker!
```

---

## 二、產生三層組合與資料集

- [ ] 生成 280 組三層組合
```
python scripts\generate_sets.py
# 預期: ✓ 已生成 280 組並儲存到 data/combinations.json
```

- [ ] 確認 combinations.json 存在
```
dir data\combinations.json
# 預期: 檔案存在，大小 > 0
```

- [ ] 劃分訓練/驗證/測試與 OOD 集（穩健版）
```
python scripts\prepare_datasets.py
# 預期: 顯示使用的分層策略，並輸出 CSV/JSON
```

- [ ] 確認輸出檔案存在
```
dir data\processed
# 預期: train.csv, val.csv, test.csv 存在

dir data\ood
# 預期: ood_combinations.json 存在
```

---

## 三、Docker 配置生成（可先跳過，若只驗證數據流程）

- [ ] 依組合生成 Compose 檔
```
python scripts\generate_combinations.py
# 預期: 於 docker_configs\ 產生多個 compose_combo_*.yml
```

- [ ] 驗證隨機一組 Compose 檔可啟動（範例）
```
docker compose -f docker_configs\compose_combo_001.yml up -d
# 預期: 建立 3 個容器（_l1/_l2/_l3），均為 running 狀態
```

---

## 四、基線測試（可選）

- [ ] 收集 HTTP 響應並執行基線（模擬）
```
python scripts\run_untangle_baseline.py
# 預期: 產出 results\untangle_baseline_*.json
```

---

## 五、自動化一鍵執行（可選）

- [ ] Windows 一鍵執行第一階段
```
run_stage1.bat
# 預期: 依序完成 生成組合 -> 劃分資料集 -> 產出 Docker 配置
```

---

## 快速故障排除

- 若看到 `FileNotFoundError: data/combinations.json`：
  - 先執行 `python scripts\generate_sets.py`
  - 在專案根目錄下執行 `python scripts\prepare_datasets.py`

- 若看到 `ValueError: least populated class in y has only 1 member`：
  - 已改為「穩健版」分層，請更新專案 `git pull origin main` 後重試

- 若 Docker 啟動失敗：
  - 打開 Docker Desktop，設定 Resources → Memory 至 8GB、CPUs 至 4

---

完成以上所有勾選，即代表第一階段已順利完成。
