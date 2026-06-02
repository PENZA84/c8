import re
import yaml
import threading
import base64
import requests
import csv
import queue
from loguru import logger
from tqdm import tqdm
from retry import retry
from urllib.parse import unquote
from datetime import datetime
from collections import defaultdict

# ======================
# 全局数据
# ======================
new_sub_list = []
new_clash_list = []
new_v2_list = []
all_nodes_list = []  # 最终提取的节点内容
processed_urls = set()
url_queue = queue.Queue()

lock = threading.Lock()
max_concurrency = threading.Semaphore(64)
MAX_URLS = 10000  # 防止递归无限扩散

session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=0)
session.mount('http://', adapter)
session.mount('https://', adapter)

# ======================
# 工具函数
# ======================
def is_valid_protocol(text):
    # 严格排除 vmess/trojan，仅保留指定协议
    return any(x in text for x in ['vless://', 'hy2://', 'hysteria2://', 'hysteria://', 'tuic://'])

def safe_b64_decode(data):
    try:
        data = data.strip()
        pad = '=' * (-len(data) % 4)
        return base64.b64decode(data + pad, validate=False).decode(errors='ignore')
    except:
        return ""

# ======================
# 核心：订阅深度解析
# ======================
@logger.catch
def process_subscription(url, bar):
    headers = {'User-Agent': 'clash-verge/v2.0.2'}
    try:
        res = session.get(url, headers=headers, timeout=8)
        if res.status_code != 200: return
        
        content = res.text
        
        # 1. 解码 Base64 并提取节点
        decoded_content = safe_b64_decode(content)
        if decoded_content:
            # 提取节点
            nodes = re.findall(r'(vless://|hy2://|hysteria2://|hysteria://|tuic://)[^\s|]+', decoded_content)
            if nodes:
                with lock:
                    all_nodes_list.extend([n for n in nodes if is_valid_protocol(n)])
                    new_v2_list.append(url)
        
        # 2. 如果是 Clash YAML，提取节点信息
        if 'proxies:' in content:
            with lock: new_clash_list.append(url)
        
        # 3. 递归挖掘：提取其中的 URL 并按白名单过滤
        allow_list = ['sub', 'subscribe', 'proxy', 'proxies', 'raw.githubusercontent.com', 'tt.vg', 'shz.al']
        found_links = re.findall(r'https?://[^\s"\'<>]+', content)
        
        with lock:
            if len(processed_urls) < MAX_URLS:
                for link in found_links:
                    clean_link = link.strip().rstrip(')')
                    if any(x in clean_link for x in allow_list) and clean_link not in processed_urls:
                        processed_urls.add(clean_link)
                        url_queue.put(clean_link)
    except:
        pass
    
    with lock: bar.update(1)

# ======================
# 主程序
# ======================
if __name__ == '__main__':
    # 1. 读取 latest.yaml 并填入队列
    try:
        with open('latest.yaml', 'r', encoding="utf-8") as f:
            data = yaml.safe_load(f)
            for key, urls in data.items():
                for url in urls:
                    if url not in processed_urls:
                        processed_urls.add(url)
                        url_queue.put(url)
        logger.info(f'从 latest.yaml 加载了 {url_queue.qsize()} 个订阅源')
    except FileNotFoundError:
        logger.warning('未找到 latest.yaml，请先运行基础抓取脚本')

    # 2. 开始深度递归解析
    bar = tqdm(total=url_queue.qsize(), desc='深度解析中')
    threads = []
    
    while not url_queue.empty():
        url = url_queue.get()
        t = threading.Thread(target=process_subscription, args=(url, bar))
        t.start()
        threads.append(t)
        
        # 简单控制并发，防止线程过多
        if len(threads) > 32:
            for t in threads: t.join()
            threads = []

    for t in threads: t.join()
    bar.close()

    # 3. 导出所有提取到的节点
    with open('all_nodes.txt', 'w', encoding="utf-8") as f:
        f.write('\n'.join(set(all_nodes_list)))
    
    logger.info(f'解析完成。已提取节点数: {len(all_nodes_list)}，已保存至 all_nodes.txt')
