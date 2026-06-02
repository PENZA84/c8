import yaml
import urllib.parse

# ======================
# 配置
# ======================
ALLOWED_PROTOCOLS = ('vless://', 'hy2://', 'hysteria2://', 'hysteria://', 'tuic://')

def format_hysteria2(node):
    """还原 hysteria2 完整 URI"""
    server = node.get('server', '')
    port = node.get('port', '')
    password = node.get('password', node.get('uuid', '')) # 部分配置用uuid当密码
    
    # 构建基础 URI
    base = f"hysteria2://{password}@{server}:{port}"
    
    # 提取参数
    params = {}
    if node.get('sni'): params['sni'] = node['sni']
    if node.get('insecure'): params['insecure'] = '1'
    if node.get('obfs'): params['obfs'] = node['obfs']
    
    query = urllib.parse.urlencode(params)
    return f"{base}?{query}" if query else base

def to_uri(node):
    """将结构化节点转换为完整 URI"""
    # 1. 原生 URI 直接过滤
    if node.get('type') == 'uri':
        uri = node.get('uri', '')
        return uri if uri.startswith(ALLOWED_PROTOCOLS) else None
    
    # 2. YAML 字典还原
    ptype = node.get('type', '').lower()
    
    # 针对 Hysteria2 特殊还原
    if ptype in ['hy2', 'hysteria2']:
        return format_hysteria2(node)
    
    # 针对 VLESS 等其他协议的通用还原
    if ptype == 'vless':
        uuid = node.get('uuid', '')
        server = node.get('server', '')
        port = node.get('port', 443)
        return f"vless://{uuid}@{server}:{port}"
        
    return None

def main():
    try:
        with open('all_nodes.yaml', 'r', encoding="utf-8") as f:
            nodes = yaml.safe_load(f)
        
        if not isinstance(nodes, list): nodes = []

        uris = []
        for n in nodes:
            uri = to_uri(n)
            if uri: uris.append(uri)
        
        with open('all_nodes.txt', 'w', encoding="utf-8") as f:
            f.write('\n'.join(sorted(set(uris))))
        
        print(f"转换完成，共生成 {len(set(uris))} 条完整 URI")
    except Exception as e:
        print(f"转换失败: {e}")

if __name__ == '__main__':
    main()
