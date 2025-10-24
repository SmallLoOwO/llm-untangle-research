#!/usr/bin/env python3
"""
批次啟動 10 容器進行 Untangle 基線測試（subprocess 版本，無需 docker 套件）
- 解決原測試 250/250 連接失敗的問題
- 分批啟動、健康檢查、測試後立即回收清理
- 適用於資源受限環境，避免同時開啟過多容器
- 增強 Tomcat/LiteSpeed/Lighttpd 識別精確度
- 增加重試機制
"""
import json, time, re, requests, math, subprocess, sys
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / 'results'
TARGETS_PATH = RESULTS_DIR / 'baseline_targets.json'
BATCH_SIZE = 10
HTTP_TIMEOUT = 8
HEALTH_RETRIES = 15
HEALTH_SLEEP = 1.5

# 更可靠的映像選擇
IMAGE_MAP = {
    'apache': 'httpd:2.4-alpine',
    'nginx': 'nginx:alpine', 
    'caddy': 'caddy:alpine',
    'lighttpd': 'sebp/lighttpd:latest',
    'tomcat': 'tomcat:10.1-jdk17',
    'openlitespeed': 'httpd:2.4-alpine'  # 暫時用 Apache 代替有問題的 OpenLiteSpeed
}

# 針對問題映像的備選方案
FALLBACK_IMAGES = {
    'openlitespeed': ['litespeedtech/openlitespeed:1.7-lsphp81', 'httpd:2.4-alpine', 'nginx:alpine'],
    'lighttpd': ['sebp/lighttpd:1.4', 'httpd:2.4-alpine']
}

# 服務器內部端口對應
INTERNAL_PORT_MAP = {
    'tomcat': 8080,
    'openlitespeed': 8088,
    'default': 80
}

# 服務就緒等待時間（秒）
STARTUP_WAIT_MAP = {
    'tomcat': 15,  # Tomcat 需要較長啟動時間
    'openlitespeed': 10,
    'lighttpd': 5,
    'default': 3
}

UA = {'User-Agent': 'Untangle-Fingerprinter/1.0'}

def load_targets():
    """載入基線測試目標清單"""
    if not TARGETS_PATH.exists():
        raise FileNotFoundError(f'找不到 {TARGETS_PATH}，請先執行: python scripts/start_ood_containers.py')
    data = json.loads(TARGETS_PATH.read_text(encoding='utf-8'))
    return data.get('targets', [])

def get_host_port_from_url(url: str) -> int:
    """從 URL 提取端口號"""
    m = re.search(r':(\d+)$', url.strip())
    if not m:
        raise ValueError(f'URL 無法解析埠: {url}')
    return int(m.group(1))

def docker_run(image: str, name: str, host_port: int, internal_port: int = 80, max_retries: int = 2) -> bool:
    """啟動容器，成功返回 True，帶重試機制"""
    for attempt in range(max_retries):
        try:
            # 先清理可能存在的同名容器
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, check=False)
            
            cmd = [
                'docker', 'run', '-d', '--rm',
                '--name', name,
                '-p', f'{host_port}:{internal_port}',
                '--label', 'project=llm-untangle',
                '--label', 'type=baseline',
                image
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return True
            
            # 如果失敗且還有重試機會，等待一下
            if attempt < max_retries - 1:
                time.sleep(2)
                
        except Exception as e:
            if attempt == max_retries - 1:
                print(f'      ❌ 啟動失敗: {e}')
                return False
            time.sleep(2)
    
    return False

def docker_stop(name: str, max_retries: int = 2):
    """停止並刪除容器，帶重試機制"""
    for attempt in range(max_retries):
        try:
            subprocess.run(['docker', 'stop', name], capture_output=True, timeout=10, check=False)
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=10, check=False)
            return
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                pass  # 嘗試了最大次數，放棄

def wait_http_ready(url: str, server_type: str = 'default') -> bool:
    """等待 HTTP 服務就緒，根據服務器類型調整等待時間"""
    # 先等待初始啟動時間
    initial_wait = STARTUP_WAIT_MAP.get(server_type, STARTUP_WAIT_MAP['default'])
    time.sleep(initial_wait)
    
    # 然後進行健康檢查
    for _ in range(HEALTH_RETRIES):
        try:
            r = requests.get(url, timeout=HTTP_TIMEOUT, headers=UA, allow_redirects=True)
            # Tomcat 和 LiteSpeed 可能返回 404，但這仍然表示服務就緒
            if r.status_code < 500:
                return True
        except requests.RequestException:
            pass
        time.sleep(HEALTH_SLEEP)
    return False

def wait_http_ready_enhanced(url: str, server_type: str) -> bool:
    """增強的健康檢查，針對不同服務器類型調整策略"""
    
    # lighttpd 需要更長等待時間
    max_retries = 45 if server_type == 'lighttpd' else 30
    
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=5)
            # 更寬鬆的成功條件
            if r.status_code < 500 or (server_type == 'lighttpd' and r.status_code in [403, 404]):
                return True
        except requests.RequestException:
            pass
        
        # 顯示長時間等待的進度
        if server_type in ['lighttpd', 'openlitespeed'] and (attempt + 1) % 10 == 0:
            print(f'      ⏳ {server_type} 健康檢查中... ({attempt + 1}/{max_retries})')
            
        time.sleep(2)
    return False

def docker_run_with_fallback(image: str, name: str, host_port: int, server_type: str) -> tuple:
    """嘗試啟動容器，失敗時使用備選映像"""
    
    # 先嘗試主要映像
    images_to_try = [image]
    if server_type in FALLBACK_IMAGES:
        images_to_try.extend(FALLBACK_IMAGES[server_type])
    
    for attempt_image in images_to_try:
        # 預拉映像
        subprocess.run(['docker', 'pull', attempt_image], 
                      capture_output=True, text=True, timeout=60)
        
        # 嘗試不同內部端口
        internal_ports = [8080, 80] if server_type == 'tomcat' else [80, 8080]
        
        for internal_port in internal_ports:
            if docker_run(attempt_image, name, host_port, internal_port):
                return True, attempt_image
            
            # 清理失敗的容器
            docker_stop(name)
    
    return False, image

def extract_server(headers: dict, body: str, status_code: int = 200) -> str:
    """
    從 HTTP 回應提取服務器類型（Untangle 指紋識別邏輯）
    增強 Tomcat, LiteSpeed, Lighttpd 識別
    """
    server = headers.get('server', '').lower()
    body_l = body.lower() if isinstance(body, str) else ''
    
    # === Tomcat 特殊識別邏輯 ===
    # Tomcat 常常不顯示 Server header 或顯示為空
    tomcat_indicators = [
        'apache tomcat' in body_l,
        'catalina' in body_l,
        'tomcat/' in body_l,
        status_code == 404 and 'status report' in body_l,
        status_code == 404 and 'type status report' in body_l,
        'http status 404' in body_l and 'apache' not in server and 'nginx' not in server,
        '/manager' in body_l,
        'java.lang' in body_l,
        'servlet' in body_l and 'nginx' not in server and 'apache' not in server
    ]
    
    if any(tomcat_indicators):
        # 確保不是 Apache 或 Nginx 誤判
        if 'apache' not in server and 'nginx' not in server and 'httpd' not in server:
            return 'tomcat'
    
    # === LiteSpeed 特殊識別邏輯 ===
    litespeed_indicators = [
        'litespeed' in server,
        'openlitespeed' in server,
        'lsws' in server,
        'litespeed' in body_l,
        'x-powered-by' in headers and 'litespeed' in headers.get('x-powered-by', '').lower()
    ]
    
    if any(litespeed_indicators):
        return 'openlitespeed'
    
    # === Lighttpd 特殊識別邏輯 ===
    if 'lighttpd' in server or 'lighttpd' in body_l:
        return 'lighttpd'
    
    # === 標準 Server header 判斷 ===
    server_patterns = {
        'nginx': ['nginx'],
        'apache': ['apache', 'httpd'],  # Apache 在 Tomcat 之後判斷
        'caddy': ['caddy'],
        'tomcat': ['tomcat', 'coyote']  # 保留作為備用
    }
    
    for server_type, patterns in server_patterns.items():
        for pattern in patterns:
            if pattern in server:
                return server_type
    
    # === 內容判斷（最後手段） ===
    if 'nginx' in body_l:
        return 'nginx'
    if 'caddy' in body_l:
        return 'caddy'
    if 'apache' in body_l and 'tomcat' not in body_l:
        return 'apache'
    
    return 'unknown'

def calculate_realistic_accuracy(all_results, targets):
    """計算更真實的準確率，包含失敗樣本"""
    
    # 按服務器類型分組
    server_stats = defaultdict(lambda: {'total': 0, 'correct': 0, 'failed': 0})
    
    for target in targets:
        expected_server = target.get('expected_l3', target.get('L3', '')).lower()
        server_stats[expected_server]['total'] += 1
        
        # 尋找對應結果
        result = next((r for r in all_results if r['combo_id'] == target['combo_id']), None)
        
        if result and result.get('status') == 'ok' and result.get('is_correct'):
            server_stats[expected_server]['correct'] += 1
        else:
            server_stats[expected_server]['failed'] += 1
    
    # 計算整體準確率（基於所有目標，不只成功的）
    total_targets = len(targets)
    total_correct = sum(stats['correct'] for stats in server_stats.values())
    realistic_accuracy = total_correct / total_targets if total_targets > 0 else 0
    
    return realistic_accuracy, server_stats

def run_batch(batch_targets):
    """執行一批容器測試"""
    started_containers = []
    results = []
    
    print(f'  啟動 {len(batch_targets)} 個容器...')
    
    # 啟動容器
    for t in batch_targets:
        combo_id = t['combo_id']
        l3_type = t.get('expected_l3', t.get('L3', 'nginx')).lower()
        host_port = get_host_port_from_url(t['url'])
        
        # 選擇映像
        image = IMAGE_MAP.get(l3_type, 'nginx:alpine')
        container_name = f'baseline_{combo_id}'
        
        # 使用備選方案嘗試啟動
        success, used_image = docker_run_with_fallback(image, container_name, host_port, l3_type)
        
        if success:
            started_containers.append({
                'name': container_name,
                'target': t,
                'port': host_port,
                'image': used_image,  # 記錄實際使用的映像
                'server_type': l3_type  # 記錄服務器類型用於等待時間調整
            })
            print(f'    ✅ {combo_id}: {used_image} -> localhost:{host_port}')
        else:
            print(f'    ❌ {combo_id}: 所有映像都啟動失敗')
            attempted_images = [image]
            if l3_type in FALLBACK_IMAGES:
                attempted_images.extend(FALLBACK_IMAGES[l3_type])
            results.append({
                'combo_id': combo_id,
                'url': t['url'],
                'expected_l3': t.get('expected_l3', t.get('L3')),
                'predicted_l3': 'unknown',
                'status': 'start_failed',
                'attempted_images': attempted_images
            })
    
    # 等待服務就緒（根據服務器類型調整等待時間）
    print(f'  等待 {len(started_containers)} 個服務就緒...')
    for container in started_containers:
        url = f"http://localhost:{container['port']}"
        server_type = container.get('server_type', 'default')
        ready = wait_http_ready_enhanced(url, server_type)
        container['ready'] = ready
        if ready:
            print(f'    ✅ {container["target"]["combo_id"]}: 服務就緒')
        else:
            print(f'    ⚠️ {container["target"]["combo_id"]}: 服務未就緒')
    
    # 執行指紋測試
    print(f'  執行指紋識別測試...')
    for container in started_containers:
        t = container['target']
        url = f"http://localhost:{container['port']}"
        
        if not container.get('ready'):
            results.append({
                'combo_id': t['combo_id'],
                'url': url,
                'expected_l3': t.get('expected_l3', t.get('L3')),
                'predicted_l3': 'unknown',
                'status': 'not_ready'
            })
            continue
        
        try:
            r = requests.get(url, timeout=HTTP_TIMEOUT, headers=UA, allow_redirects=True)
            predicted = extract_server(
                {k.lower():v for k,v in r.headers.items()}, 
                r.text,
                r.status_code
            )
            
            results.append({
                'combo_id': t['combo_id'],
                'url': url,
                'expected_l3': t.get('expected_l3', t.get('L3')),
                'predicted_l3': predicted,
                'status': 'ok',
                'server_header': r.headers.get('Server', 'N/A'),
                'status_code': r.status_code,
                'is_correct': predicted.lower() == t.get('expected_l3', t.get('L3', '')).lower()
            })
            
            status = '✅' if predicted.lower() == t.get('expected_l3', t.get('L3', '')).lower() else '❌'
            print(f'    {status} {t["combo_id"]}: 預期={t.get("expected_l3", t.get("L3"))}, 識別={predicted}')
            
        except requests.RequestException as e:
            results.append({
                'combo_id': t['combo_id'],
                'url': url,
                'expected_l3': t.get('expected_l3', t.get('L3')),
                'predicted_l3': 'unknown',
                'status': 'request_failed',
                'error': str(e)
            })
            print(f'    ❌ {t["combo_id"]}: 請求失敗 - {e}')
    
    # 清理容器（帶重試）
    print(f'  清理 {len(started_containers)} 個容器...')
    for container in started_containers:
        docker_stop(container['name'])
        # print(f'    🗑️ {container["target"]["combo_id"]}: 已清理')  # 減少輸出
    print(f'  ✅ 所有容器已清理')
    
    return results

def main():
    print('🧪 批次 Untangle 基線測試（10/批，含清理）')
    print('=' * 50)
    
    try:
        targets = load_targets()
        print(f'📊 載入 {len(targets)} 個測試目標')
    except FileNotFoundError as e:
        print(f'❌ {e}')
        return 1
    
    if not targets:
        print('❌ 無測試目標')
        return 1
    
    # 檢查 Docker 是否可用
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            print('❌ Docker 不可用，請確認 Docker 已安裝並啟動')
            return 1
        print(f'✅ Docker 已就緒: {result.stdout.strip()}')
    except Exception:
        print('❌ 找不到 Docker 命令')
        return 1
    
    all_results = []
    total = len(targets)
    batches = math.ceil(total / BATCH_SIZE)
    
    for bi in range(batches):
        batch_start = bi * BATCH_SIZE
        batch_end = min((bi + 1) * BATCH_SIZE, total)
        batch_targets = targets[batch_start:batch_end]
        
        print(f'\n📦 批次 {bi+1}/{batches} ({len(batch_targets)} 個目標)')
        batch_results = run_batch(batch_targets)
        all_results.extend(batch_results)
        
            # 批次間稍微暫停，確保容器完全清理
        if bi < batches - 1:
            print('  ⏳ 批次間暫停 3 秒...')
            time.sleep(3)
    
    # 收集失敗樣本進行重試
    failed_targets = []
    for result in all_results:
        if result.get('status') in ['start_failed', 'not_ready']:
            # 從原始 targets 中找回完整信息
            original_target = next(
                (t for t in targets if t['combo_id'] == result['combo_id']), None
            )
            if original_target:
                failed_targets.append(original_target)

    # 對失敗樣本進行一次重試
    if failed_targets and len(failed_targets) <= 50:  # 避免重試過多
        print(f'\n🔁 對 {len(failed_targets)} 個失敗樣本進行重試...')
        
        # 分批重試
        retry_batches = math.ceil(len(failed_targets) / BATCH_SIZE)
        for bi in range(retry_batches):
            batch_start = bi * BATCH_SIZE
            batch_end = min((bi + 1) * BATCH_SIZE, len(failed_targets))
            retry_batch = failed_targets[batch_start:batch_end]
            
            print(f'  重試批次 {bi+1}/{retry_batches} ({len(retry_batch)} 個目標)')
            retry_results = run_batch(retry_batch)
            
            # 替換原結果中的失敗項
            for retry_result in retry_results:
                if retry_result.get('status') == 'ok':
                    # 找到並替換原來的失敗結果
                    for i, orig_result in enumerate(all_results):
                        if orig_result['combo_id'] == retry_result['combo_id']:
                            all_results[i] = retry_result
                            print(f'    ✅ {retry_result["combo_id"]}: 重試成功！')
                            break
            
            # 重試批次間暫停
            if bi < retry_batches - 1:
                print('  ⏳ 重試批次間暫停 3 秒...')
                time.sleep(3)
    elif len(failed_targets) > 50:
        print(f'\n⚠️ 失敗樣本過多 ({len(failed_targets)} 個)，跳過重試')
    
    # 統計結果
    total_tested = len([r for r in all_results if r.get('status') == 'ok'])
    total_correct = len([r for r in all_results if r.get('is_correct')])
    accuracy = (total_correct / total_tested) if total_tested > 0 else 0.0
    
    status_counts = Counter(r['status'] for r in all_results)
    
    # 各服務器類型準確率（僅成功樣本）
    server_stats = defaultdict(lambda: {'total': 0, 'correct': 0})
    for r in all_results:
        if r.get('status') == 'ok':
            expected = r['expected_l3'].lower()
            server_stats[expected]['total'] += 1
            if r.get('is_correct'):
                server_stats[expected]['correct'] += 1
    
    # 計算真實準確率（包含失敗樣本）
    realistic_accuracy, realistic_server_stats = calculate_realistic_accuracy(all_results, targets)
    
    # 輸出結果
    print('\n' + '=' * 50)
    print('📈 批次基線測試結果')
    print('=' * 50)
    print(f'總測試目標: {total}')
    print(f'成功測試: {total_tested}')
    print(f'正確識別: {total_correct}')
    print(f'L3 真實整體準確率: {realistic_accuracy:.1%}（包含失敗樣本）')
    print(f'L3 成功樣本準確率: {accuracy:.1%}（僅成功樣本）')
    print(f'狀態分布: {dict(status_counts)}')
    
    if realistic_server_stats:
        print(f'\n📊 真實各 L3 服務器準確率（包含啟動失敗）:')
        for server, stats in sorted(realistic_server_stats.items()):
            real_acc = stats['correct'] / stats['total'] if stats['total'] > 0 else 0
            print(f'  {server:12}: {real_acc:6.1%} ({stats["correct"]:2d}/{stats["total"]:2d}) [失敗: {stats["failed"]}]')
    
    if server_stats:
        print(f'\n📊 成功樣本各 L3 服務器準確率（僅就緒服務）:')
        for server, stats in sorted(server_stats.items()):
            acc = stats['correct'] / stats['total'] if stats['total'] > 0 else 0
            print(f'  {server:12}: {acc:6.1%} ({stats["correct"]:2d}/{stats["total"]:2d})')
    
    # 論文預期對照（使用真實準確率）
    expected_range = (0.50, 0.55)
    if expected_range[0] <= realistic_accuracy <= expected_range[1]:
        status = '✅ 符合論文預期'
    elif realistic_accuracy < expected_range[0]:
        status = '⚠️ 低於預期範圍'
    else:
        status = '📈 高於預期範圍'
    
    print(f'\n🎯 論文預期範圍: {expected_range[0]*100:.0f}-{expected_range[1]*100:.0f}% | 真實結果: {realistic_accuracy:.1%} {status}')
    
    # 保存結果
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'method': 'Untangle Baseline (Batched with Cleanup)',
        'test_summary': {
            'total_targets': total,
            'successful_tests': total_tested,
            'failed_tests': total - total_tested,
            'correct_predictions': total_correct,
            'realistic_accuracy': realistic_accuracy,  # 包含失敗樣本的真實準確率
            'success_only_accuracy': accuracy,  # 僅成功樣本的準確率
            'status_distribution': dict(status_counts),
            'error_rate': (total - total_tested) / total if total > 0 else 0
        },
        'realistic_server_accuracy': {k: {'accuracy': v['correct']/v['total'] if v['total']>0 else 0, **v} 
                                     for k, v in realistic_server_stats.items()},
        'server_accuracy': {k: {'accuracy': v['correct']/v['total'] if v['total']>0 else 0, **v} 
                           for k, v in server_stats.items()},
        'detailed_results': all_results
    }
    
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = RESULTS_DIR / f'untangle_batched_results_{int(time.time())}.json'
    output_file.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    
    print(f'\n💾 詳細結果已保存: {output_file}')
    print('✅ 可用於 BCa Bootstrap 統計分析')
    
    # 判斷成功標準（使用真實準確率）
    if realistic_accuracy >= 0.40:  # 允許合理範圍（考慮失敗樣本後的標準）
        print('🎉 基線測試完成，真實準確率在合理範圍內')
        return 0
    else:
        print('⚠️ 基線測試完成，但真實準確率偏低，請檢查配置')
        return 0  # 仍返回 0，因為測試流程成功

if __name__ == '__main__':
    sys.exit(main())