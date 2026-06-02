import re
import yaml
import base64
import requests
import threading
import queue
from loguru import logger

# ======================
# 配置与数据
# ======================
MAX_URLS = 10000
WORKER_THREADS = 32
url_queue = queue.Queue()
processed_urls = set()
all_nodes_data = []  # 存储完整的节点字典
lock = threading.Lock()

# 维持会话池以复用连接
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=64, pool_maxsize=64)
session.mount('https://', adapter)

# 核心正则 (非捕获)
NODE_URI_REGEX = re.compile(r'(?:vless|hy2|hysteria2|hysteria|tuic)://[^\s"\'<>]+')
LINK_REGEX = re.compile(r'https?://[^\s"\'<>]+')

# ======================
# 深度提取函数
# ======================
def extract_clash_yaml(content):
    """解析完整的 Clash YAML 节点，返回字典列表"""
    nodes = []
    try:
        data = yaml.safe_load(content)
        if isinstance(data, dict) and 'proxies' in data:
            for p in data['proxies']:
                # 直接保留整个字典，完整保存所有配置项
                nodes.append(p)
    except:
        pass
    return nodes

def worker():
    while True:
        try:
            url = url_queue.get(timeout=3)
        except queue.Empty:
            break
            
        try:
            res = session.get(url, timeout=10, headers={'User-Agent': 'clash-verge/v2.0.2'}, allow_redirects=True)
            content = res.text
            
            # 1. 完整节点提取
            found_data = []
            
            # 如果包含 proxies，则作为 YAML 解析
            if "proxies:" in content:
                found_data.extend(extract_clash_yaml(content))
            
            # 无论是否为 YAML，都尝试提取文本中的 URI (兼容 Base64)
            if not re.fullmatch(r'[A-Za-z0-9+/=\r\n]+', content.strip()): # 非纯Base64判断
                uris = NODE_URI_REGEX.findall(content)
                found_data.extend([{'type': 'uri', 'uri': u} for u in uris])
            
            if found_data:
                with lock:
                    all_nodes_data.extend(found_data)
            
            # 2. 递归发现更多订阅 (处理跳转后的真实 URL)
            if len(processed_urls) < MAX_URLS:
                new_links = LINK_REGEX.findall(content)
                new_links.append(res.url) # 添加跳转后的真实地址
                
                with lock:
                    for link in set(new_links):
                        if any(k in link for k in ['sub', 'subscribe', 'proxy', 'raw.githubusercontent.com', 'clash']) and link not in processed_urls:
                            processed_urls.add(link)
                            url_queue.put(link)
        except:
            pass
        finally:
            url_queue.task_done()

if __name__ == '__main__':
    with open('latest.yaml', 'r', encoding="utf-8") as f:
        for urls in yaml.safe_load(f).values():
            for url in urls:
                if url not in processed_urls:
                    processed_urls.add(url)
                    url_queue.put(url)

    logger.info(f"开始深度挖掘，队列: {url_queue.qsize()}")
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(WORKER_THREADS)]
    for t in threads: t.start()
    url_queue.join()
    
    # 导出完整节点对象
    with open('all_nodes.yaml', 'w', encoding="utf-8") as f:
        yaml.dump(all_nodes_data, f, allow_unicode=True)
    
    logger.info(f"解析完成，共获取节点对象: {len(all_nodes_data)}，已保存至 all_nodes.yaml")
