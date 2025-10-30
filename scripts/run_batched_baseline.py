#!/usr/bin/env python3
"""
批次 Untangle 基線測試（修正版）
- 改為直接從 data/combinations.json 載入所有組合作為測試目標
- 若存在 results/baseline_targets.json，僅作為覆蓋清單（優先），否則使用全量 90 組
- 支援 --limit 與 --offset 參數分段執行；預設跑全量
- 批次大小仍為 10，會自動計算批數
"""
import json, time, re, requests, math, subprocess, sys, argparse
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / 'results'
TARGETS_PATH = RESULTS_DIR / 'baseline_targets.json'
COMBO_PATH = ROOT / 'data' / 'combinations.json'
BATCH_SIZE = 10
HTTP_TIMEOUT = 8
HEALTH_RETRIES = 15
HEALTH_SLEEP = 1.5

IMAGE_MAP = {
    'apache': 'httpd:2.4-alpine',
    'nginx': 'nginx:alpine', 
    'caddy': 'caddy:alpine',
    'lighttpd': 'sebp/lighttpd:latest',
    'tomcat': 'tomcat:10.1-jdk17',
    'openlitespeed': 'httpd:2.4-alpine'
}

FALLBACK_IMAGES = {
    'openlitespeed': ['litespeedtech/openlitespeed:1.7-lsphp81', 'httpd:2.4-alpine', 'nginx:alpine'],
    'lighttpd': ['sebp/lighttpd:1.4', 'httpd:2.4-alpine']
}

INTERNAL_PORT_MAP = {
    'tomcat': 8080,
    'openlitespeed': 8088,
    'default': 80
}

STARTUP_WAIT_MAP = {
    'tomcat': 15,
    'openlitespeed': 10,
    'lighttpd': 5,
    'default': 3
}

UA = {'User-Agent': 'Untangle-Fingerprinter/1.0'}

def load_all_combinations():
    if not COMBO_PATH.exists():
        raise FileNotFoundError(f'找不到 {COMBO_PATH}，請先執行: python scripts/generate_sets.py')
    return json.loads(COMBO_PATH.read_text(encoding='utf-8'))

def load_targets_from_results():
    if TARGETS_PATH.exists():
        data = json.loads(TARGETS_PATH.read_text(encoding='utf-8'))
        return data.get('targets', [])
    return []

def build_targets(limit=None, offset=0):
    override = load_targets_from_results()
    if override:
        return override[offset:(offset+limit) if limit else None]
    combos = load_all_combinations()
    targets = []
    for c in combos:
        l3_base = c['l3'].get('base_name') or c['l3']['name'].split('_')[0]
        targets.append({
            'combo_id': c['id'],
            'url': c['url'],
            'expected_l3': l3_base
        })
    return targets[offset:(offset+limit) if limit else None]

def get_host_port_from_url(url: str) -> int:
    m = re.search(r':(\d+)$', url.strip())
    if not m:
        raise ValueError(f'URL 無法解析埠: {url}')
    return int(m.group(1))

def docker_run(image: str, name: str, host_port: int, internal_port: int = 80, max_retries: int = 2) -> bool:
    for attempt in range(max_retries):
        try:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, check=False)
            cmd = ['docker','run','-d','--rm','--name',name,'-p',f'{host_port}:{internal_port}','--label','project=llm-untangle','--label','type=baseline',image]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return True
            if attempt < max_retries - 1:
                time.sleep(2)
        except Exception:
            if attempt == max_retries - 1:
                return False
            time.sleep(2)
    return False

def docker_stop(name: str, max_retries: int = 2):
    for attempt in range(max_retries):
        try:
            subprocess.run(['docker','stop',name], capture_output=True, timeout=10, check=False)
            subprocess.run(['docker','rm','-f',name], capture_output=True, timeout=10, check=False)
            return
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(1)


def wait_http_ready_enhanced(url: str, server_type: str) -> bool:
    max_retries = 45 if server_type == 'lighttpd' else 30
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=5)
            if r.status_code < 500 or (server_type == 'lighttpd' and r.status_code in [403,404]):
                return True
        except requests.RequestException:
            pass
        if server_type in ['lighttpd','openlitespeed'] and (attempt+1) % 10 == 0:
            print(f'      ⏳ {server_type} 健康檢查中... ({attempt+1}/{max_retries})')
        time.sleep(2)
    return False

def docker_run_with_fallback(image: str, name: str, host_port: int, server_type: str) -> tuple:
    images_to_try = [image]
    if server_type in FALLBACK_IMAGES:
        images_to_try.extend(FALLBACK_IMAGES[server_type])
    internal_ports = [8080,80] if server_type=='tomcat' else [80,8080]
    for attempt_image in images_to_try:
        subprocess.run(['docker','pull',attempt_image], capture_output=True, text=True, timeout=60)
        for p in internal_ports:
            if docker_run(attempt_image, name, host_port, p):
                return True, attempt_image
            docker_stop(name)
    return False, image

def extract_server(headers: dict, body: str, status_code: int = 200) -> str:
    server = headers.get('server','').lower()
    body_l = body.lower() if isinstance(body,str) else ''
    tomcat_indicators = ['apache tomcat' in body_l,'catalina' in body_l,'tomcat/' in body_l,status_code==404 and 'status report' in body_l,status_code==404 and 'type status report' in body_l,'http status 404' in body_l and 'apache' not in server and 'nginx' not in server,'/manager' in body_l,'java.lang' in body_l,'servlet' in body_l and 'nginx' not in server and 'apache' not in server]
    if any(tomcat_indicators):
        if 'apache' not in server and 'nginx' not in server and 'httpd' not in server:
            return 'tomcat'
    litespeed_indicators = ['litespeed' in server,'openlitespeed' in server,'lsws' in server,'litespeed' in body_l,('x-powered-by' in headers and 'litespeed' in headers.get('x-powered-by','').lower())]
    if any(litespeed_indicators):
        return 'openlitespeed'
    if 'lighttpd' in server or 'lighttpd' in body_l:
        return 'lighttpd'
    server_patterns = {'nginx':['nginx'],'apache':['apache','httpd'],'caddy':['caddy'],'tomcat':['tomcat','coyote']}
    for server_type, patterns in server_patterns.items():
        for pattern in patterns:
            if pattern in server:
                return server_type
    if 'nginx' in body_l:
        return 'nginx'
    if 'caddy' in body_l:
        return 'caddy'
    if 'apache' in body_l and 'tomcat' not in body_l:
        return 'apache'
    return 'unknown'


def calculate_realistic_accuracy(all_results, targets):
    server_stats = defaultdict(lambda: {'total':0,'correct':0,'failed':0})
    for t in targets:
        expected = t.get('expected_l3', t.get('L3','')).lower()
        server_stats[expected]['total'] += 1
        result = next((r for r in all_results if r['combo_id']==t['combo_id']), None)
        if result and result.get('status')=='ok' and result.get('is_correct'):
            server_stats[expected]['correct'] += 1
        else:
            server_stats[expected]['failed'] += 1
    total = len(targets)
    total_correct = sum(s['correct'] for s in server_stats.values())
    realistic = total_correct/total if total>0 else 0
    return realistic, server_stats


def run_batch(batch_targets):
    started_containers = []
    results = []
    print(f'  啟動 {len(batch_targets)} 個容器...')
    for t in batch_targets:
        combo_id = t['combo_id']
        l3_type = t.get('expected_l3', t.get('L3','nginx')).lower()
        host_port = get_host_port_from_url(t['url'])
        image = IMAGE_MAP.get(l3_type, 'nginx:alpine')
        name = f'baseline_{combo_id}'
        success, used_image = docker_run_with_fallback(image, name, host_port, l3_type)
        if success:
            started_containers.append({'name':name,'target':t,'port':host_port,'image':used_image,'server_type':l3_type})
            print(f'    ✅ {combo_id}: {used_image} -> localhost:{host_port}')
        else:
            results.append({'combo_id':combo_id,'url':t['url'],'expected_l3':t.get('expected_l3',t.get('L3')),'predicted_l3':'unknown','status':'start_failed'})
    print(f'  等待 {len(started_containers)} 個服務就緒...')
    for c in started_containers:
        url = f"http://localhost:{c['port']}"
        ready = wait_http_ready_enhanced(url, c.get('server_type','default'))
        c['ready'] = ready
        print(f"    {'✅' if ready else '⚠️'} {c['target']['combo_id']}: {'服務就緒' if ready else '服務未就緒'}")
    print(f'  執行指紋識別測試...')
    for c in started_containers:
        t = c['target']
        url = f"http://localhost:{c['port']}"
        if not c.get('ready'):
            results.append({'combo_id':t['combo_id'],'url':url,'expected_l3':t.get('expected_l3',t.get('L3')),'predicted_l3':'unknown','status':'not_ready'})
            continue
        try:
            r = requests.get(url, timeout=HTTP_TIMEOUT, headers=UA, allow_redirects=True)
            predicted = extract_server({k.lower():v for k,v in r.headers.items()}, r.text, r.status_code)
            results.append({'combo_id':t['combo_id'],'url':url,'expected_l3':t.get('expected_l3',t.get('L3')),'predicted_l3':predicted,'status':'ok','server_header':r.headers.get('Server','N/A'),'status_code':r.status_code,'is_correct':predicted.lower()==t.get('expected_l3',t.get('L3','')).lower()})
            print(f"    {'✅' if predicted.lower()==t.get('expected_l3',t.get('L3','')).lower() else '❌'} {t['combo_id']}: 預期={t.get('expected_l3',t.get('L3'))}, 識別={predicted}")
        except requests.RequestException as e:
            results.append({'combo_id':t['combo_id'],'url':url,'expected_l3':t.get('expected_l3',t.get('L3')),'predicted_l3':'unknown','status':'request_failed','error':str(e)})
            print(f'    ❌ {t["combo_id"]}: 請求失敗 - {e}')
    print(f'  清理 {len(started_containers)} 個容器...')
    for c in started_containers:
        docker_stop(c['name'])
    print('  ✅ 所有容器已清理')
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None, help='限制測試的目標數量')
    parser.add_argument('--offset', type=int, default=0, help='從第幾個目標開始')
    args = parser.parse_args()

    print('🧪 批次 Untangle 基線測試（10/批，含清理）')
    print('=' * 50)

    try:
        targets = build_targets(limit=args.limit, offset=args.offset)
        print(f'📊 載入 {len(targets)} 個測試目標')
    except FileNotFoundError as e:
        print(f'❌ {e}')
        return 1

    if not targets:
        print('❌ 無測試目標')
        return 1

    try:
        result = subprocess.run(['docker','--version'], capture_output=True, text=True)
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
        if bi < batches - 1:
            print('  ⏳ 批次間暫停 3 秒...')
            time.sleep(3)

    realistic_accuracy, realistic_server_stats = calculate_realistic_accuracy(all_results, targets)
    total_tested = len([r for r in all_results if r.get('status')=='ok'])
    total_correct = len([r for r in all_results if r.get('is_correct')])
    accuracy = (total_correct/total_tested) if total_tested>0 else 0.0
    status_counts = Counter(r['status'] for r in all_results)

    print('\n' + '='*50)
    print('📈 批次基線測試結果')
    print('='*50)
    print(f'總測試目標: {total}')
    print(f'成功測試: {total_tested}')
    print(f'正確識別: {total_correct}')
    print(f'L3 真實整體準確率: {realistic_accuracy:.1%}（包含失敗樣本）')
    print(f'L3 成功樣本準確率: {accuracy:.1%}（僅成功樣本）')
    print(f'狀態分布: {dict(status_counts)}')

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = RESULTS_DIR / f'untangle_batched_results_{int(time.time())}.json'
    output = {'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),'method':'Untangle Baseline (Batched with Cleanup)','total_targets':total,'success_only_accuracy':accuracy,'realistic_accuracy':realistic_accuracy,'status_distribution':dict(status_counts),'detailed_results':all_results}
    output_file.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\n💾 詳細結果已保存: {output_file}')
    print('✅ 可用於 BCa Bootstrap 統計分析')
    return 0

if __name__ == '__main__':
    sys.exit(main())
