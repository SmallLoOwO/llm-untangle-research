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

# L3 服務器 → Docker 映像對應
IMAGE_MAP = {
    'apache': 'httpd:2.4-alpine',
    'nginx': 'nginx:alpine', 
    'caddy': 'caddy:alpine',
    'lighttpd': 'sebp/lighttpd:latest',
    'tomcat': 'tomcat:10.1-jdk17',
    'openlitespeed': 'litespeedtech/openlitespeed:1.7-lsphp81'  # 使用更穩定的版本
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
        
        # 根據服務器類型選擇內部端口
        internal_port = INTERNAL_PORT_MAP.get(l3_type, INTERNAL_PORT_MAP['default'])
        
        # 嘗試啟動容器（帶重試）
        success = docker_run(image, container_name, host_port, internal_port)
        
        if success:
            started_containers.append({
                'name': container_name,
                'target': t,
                'port': host_port,
                'server_type': l3_type  # 記錄服務器類型用於等待時間調整
            })
            print(f'    ✅ {combo_id}: {image} -> localhost:{host_port}')
        else:
            print(f'    ❌ {combo_id}: 啟動失敗')
            results.append({
                'combo_id': combo_id,
                'url': t['url'],
                'expected_l3': t.get('expected_l3', t.get('L3')),
                'predicted_l3': 'unknown',
                'status': 'start_failed'
            })
    
    # 等待服務就緒（根據服務器類型調整等待時間）
    print(f'  等待 {len(started_containers)} 個服務就緒...')
    for container in started_containers:
        url = f"http://localhost:{container['port']}"
        server_type = container.get('server_type', 'default')
        ready = wait_http_ready(url, server_type)
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
    
    # 統計結果
    total_tested = len([r for r in all_results if r.get('status') == 'ok'])
    total_correct = len([r for r in all_results if r.get('is_correct')])
    accuracy = (total_correct / total_tested) if total_tested > 0 else 0.0
    
    status_counts = Counter(r['status'] for r in all_results)
    
    # 各服務器類型準確率
    server_stats = defaultdict(lambda: {'total': 0, 'correct': 0})
    for r in all_results:
        if r.get('status') == 'ok':
            expected = r['expected_l3'].lower()
            server_stats[expected]['total'] += 1
            if r.get('is_correct'):
                server_stats[expected]['correct'] += 1
    
    # 輸出結果
    print('\n' + '=' * 50)
    print('📈 批次基線測試結果')
    print('=' * 50)
    print(f'總測試目標: {total}')
    print(f'成功測試: {total_tested}')
    print(f'正確識別: {total_correct}')
    print(f'L3 整體準確率: {accuracy:.1%}')
    print(f'狀態分布: {dict(status_counts)}')
    
    if server_stats:
        print(f'\n📊 各 L3 服務器準確率:')
        for server, stats in sorted(server_stats.items()):
            acc = stats['correct'] / stats['total'] if stats['total'] > 0 else 0
            print(f'  {server:12}: {acc:6.1%} ({stats["correct"]:2d}/{stats["total"]:2d})')
    
    # 論文預期對照
    expected_range = (0.50, 0.55)
    if expected_range[0] <= accuracy <= expected_range[1]:
        status = '✅ 符合論文預期'
    elif accuracy < expected_range[0]:
        status = '⚠️ 低於預期範圍'
    else:
        status = '📈 高於預期範圍'
    
    print(f'\n🎯 論文預期範圍: {expected_range[0]*100:.0f}-{expected_range[1]*100:.0f}% | 實際結果: {status}')
    
    # 保存結果
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'method': 'Untangle Baseline (Batched with Cleanup)',
        'test_summary': {
            'total_targets': total,
            'successful_tests': total_tested,
            'failed_tests': total - total_tested,
            'correct_predictions': total_correct,
            'overall_accuracy': accuracy,
            'status_distribution': dict(status_counts),
            'error_rate': (total - total_tested) / total if total > 0 else 0
        },
        'server_accuracy': {k: {'accuracy': v['correct']/v['total'] if v['total']>0 else 0, **v} 
                           for k, v in server_stats.items()},
        'detailed_results': all_results
    }
    
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = RESULTS_DIR / f'untangle_batched_results_{int(time.time())}.json'
    output_file.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    
    print(f'\n💾 詳細結果已保存: {output_file}')
    print('✅ 可用於 BCa Bootstrap 統計分析')
    
    # 判斷成功標準
    if accuracy >= 0.45:  # 允許合理範圍
        print('🎉 基線測試完成，準確率在合理範圍內')
        return 0
    else:
        print('⚠️ 基線測試完成，但準確率偏低，請檢查配置')
        return 0  # 仍返回 0，因為測試流程成功

if __name__ == '__main__':
    sys.exit(main())