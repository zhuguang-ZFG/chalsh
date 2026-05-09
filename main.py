#!/usr/bin/env python3
"""chalsh — lightweight free VPN node aggregator and local proxy."""

import json
import os
import sys
import argparse
import base64
from datetime import datetime
import urllib.parse
import concurrent.futures
import logging

import yaml
from dotenv import load_dotenv
load_dotenv('.secrets')
load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
sys.path.append(os.path.join(current_dir, 'core', 'parsers'))

from core.spider import Spider
from core.deduplicator import Deduplicator
from core.validator import Validator
from core.converters.clash import to_clash_proxies

try:
    import vmess
    import vless
    import ss
    import trojan
    import hysteria2
    import tuic
except ImportError:
    from core.parsers import vmess, vless, ss, trojan, hysteria2, tuic

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

PROTOCOL_PARSERS = {
    'vmess': vmess,
    'vless': vless,
    'ss': ss,
    'trojan': trojan,
    'hysteria2': hysteria2,
    'hy2': hysteria2,
    'tuic': tuic
}


def get_parser(protocol):
    return PROTOCOL_PARSERS.get(protocol)


def parse_source_params(param_str):
    options = {}
    if not param_str:
        return options
    try:
        params = urllib.parse.parse_qs(param_str, keep_blank_values=True)
        if 'max' in params and params['max']:
            try:
                options['max_nodes'] = int(params['max'][0])
            except:
                pass
        if 'ignore' in params and params['ignore']:
            ignore = [p.strip() for p in params['ignore'][0].split(',') if p.strip()]
            if ignore:
                options['ignore_protocols'] = ignore
    except:
        pass
    return options


def apply_source_filters(links, options):
    if not links:
        return []
    ignore = set([p.lower() for p in options.get('ignore_protocols', [])])
    if ignore:
        filtered = []
        for link in links:
            protocol = link.split('://')[0].lower() if '://' in link else ''
            if protocol and protocol in ignore:
                continue
            filtered.append(link)
        links = filtered
    max_nodes = options.get('max_nodes')
    if isinstance(max_nodes, int) and max_nodes > 0:
        links = links[:max_nodes]
    return links


def resolve_date_url(url):
    try:
        return datetime.now().strftime(url)
    except:
        return url


def expand_sources_list(list_path, spider):
    entries = []
    allow_blocked = os.getenv('ALLOW_BLOCKED_SOURCES') == '1'
    if not os.path.exists(list_path):
        return entries
    with open(list_path, 'r') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            if line == 'EOF':
                break
            blocked = False
            if line.startswith('!'):
                blocked = True
                line = line[1:].strip()
            if blocked and not allow_blocked:
                continue
            is_date = False
            if line.startswith('+date'):
                is_date = True
                line = line[len('+date'):].strip()
            is_list = False
            if line.startswith('*'):
                is_list = True
                line = line[1:].strip()
            param_str = ''
            if '#' in line:
                line, param_str = line.split('#', 1)
            url = line.strip()
            if not url:
                continue
            if is_date:
                url = resolve_date_url(url)
            options = parse_source_params(param_str)
            if is_list:
                try:
                    content = spider.fetch_url(url)
                    if content:
                        for item in content.splitlines():
                            item = item.strip()
                            if not item or item.startswith('#'):
                                continue
                            item_url = item.split('#')[0].strip()
                            if item_url.startswith('http'):
                                entries.append((item_url, options))
                except Exception as e:
                    logger.debug(f"Error fetching list {url}: {e}")
            else:
                entries.append((url, options))
    return entries


def main():
    parser = argparse.ArgumentParser(description='chalsh — free VPN node aggregator')
    parser.add_argument('--validate', action='store_true', help='Validate nodes via HTTP latency')
    parser.add_argument('--output', type=str, default='output', help='Output directory')
    parser.add_argument('--workers', type=int, default=10, help='Number of fetch workers')
    parser.add_argument('--max-latency', type=int, default=800, help='Max latency in ms for validation (default 800)')
    parser.add_argument('--timeout', type=int, default=5, help='Test timeout in seconds (default 5)')
    parser.add_argument('--local', action='store_true', help='Local mode: skip TCP checks (GFW environment)')
    parser.add_argument('--serve', action='store_true', help='Start local proxy server after fetching')
    parser.add_argument('--port', type=int, default=7890, help='Local proxy port (default 7890)')
    args = parser.parse_args()

    is_ci = os.getenv('GITHUB_ACTIONS') == 'true'
    local_mode = args.local or not is_ci
    if local_mode:
        logger.info("Mode: LOCAL (direct TCP checks disabled — GFW environment)")
    else:
        logger.info("Mode: CI (full validation)")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = args.output if os.path.isabs(args.output) else os.path.join(base_dir, args.output)
    os.makedirs(output_dir, exist_ok=True)

    logger.info("=" * 50)
    logger.info("chalsh — free VPN node aggregator")
    logger.info("=" * 50)

    spider = Spider(max_workers=args.workers)
    deduplicator = Deduplicator()
    all_links = []

    # Load sources
    logger.info("\n[1/4] Loading sources...")
    sources_json_env = os.getenv('SOURCES_JSON', '')
    if sources_json_env:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(sources_json_env)
            config_path = f.name
        logger.info("      Using SOURCES_JSON from environment")
    else:
        config_path = os.path.join(base_dir, 'config', 'sources.json')
        logger.info("      Using config/sources.json")
    with open(config_path, 'r') as f:
        sources = json.load(f)
    if sources_json_env:
        try:
            os.remove(config_path)
        except Exception:
            pass

    extra_urls = [u.strip() for u in os.getenv('EXTRA_URLS', '').splitlines() if u.strip()]
    logger.info(f"      Found {len(sources.get('urls', []))} URL sources")
    logger.info(f"      Found {len(extra_urls)} extra URLs")

    # Fetch all URLs
    logger.info("\n[2/4] Fetching nodes...")
    url_sources = sources.get('urls', [])
    urls_to_fetch = list(extra_urls)
    url_options = {url: {} for url in extra_urls}

    for entry in url_sources:
        if isinstance(entry, dict):
            if entry.get('enabled') is False:
                continue
            url = entry.get('url')
            if not url:
                continue
            if entry.get('update_method') == 'change_date':
                url = resolve_date_url(url)
            opts = {}
            if entry.get('max_nodes'):
                opts['max_nodes'] = entry['max_nodes']
            if entry.get('ignore_protocols'):
                opts['ignore_protocols'] = entry['ignore_protocols']
            urls_to_fetch.append(url)
            url_options[url] = opts
        elif isinstance(entry, str):
            urls_to_fetch.append(entry)
            url_options[entry] = {}

    results = spider.fetch_urls_parallel(urls_to_fetch)
    for url, content in results.items():
        if content:
            links = spider.parse_subscription(content)
            links = apply_source_filters(links, url_options.get(url, {}))
            logger.info(f"      {url}: {len(links)} links")
            all_links.extend(links)

    # Also process sources.list
    list_path = os.path.join(base_dir, 'config', 'sources.list')
    for url, options in expand_sources_list(list_path, spider):
        try:
            if url.startswith('http'):
                content = spider.fetch_url(url)
                links = spider.parse_subscription(content)
            else:
                links = [url]
            links = apply_source_filters(links, options)
            logger.info(f"      {url}: {len(links)} links")
            all_links.extend(links)
        except Exception as e:
            logger.debug(f"      Failed to process {url}: {e}")

    unique_links = list(set(all_links))
    logger.info(f"\n[3/4] Total unique links: {len(unique_links)}")

    # Parse and deduplicate
    logger.info("Parsing and deduplicating nodes...")
    raw_parsed_nodes = []

    def parse_link_simple(link):
        try:
            protocol = link.split('://')[0].lower()
            p = get_parser(protocol)
            if p:
                return p.parse(link), link
        except Exception:
            pass
        return None, link

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_link = {executor.submit(parse_link_simple, link): link for link in unique_links}
        for future in concurrent.futures.as_completed(future_to_link):
            try:
                node, link = future.result()
                if node:
                    raw_parsed_nodes.append((node, link))
            except Exception:
                pass

    sing_box_outbounds = []
    link_to_node_map = {}
    duplicates = 0
    for node, link in raw_parsed_nodes:
        nodes_to_add = list(node) if isinstance(node, tuple) else [node]
        for n in nodes_to_add:
            if deduplicator.is_duplicate(n) or deduplicator.is_redundant_server(n):
                duplicates += 1
                continue
            original_tag = n.get('tag', '')
            sing_box_outbounds.append(n)
            link_to_node_map[original_tag] = link

    logger.info(f"  Parsed: {len(sing_box_outbounds)} nodes, filtered {duplicates} duplicates")
    valid_nodes = sing_box_outbounds

    # Validate if requested
    if args.validate and len(valid_nodes) > 0:
        logger.info("\nValidating nodes (multi-stage test)...")
        valid_nodes = Validator.validate_nodes(
            valid_nodes,
            max_latency_ms=args.max_latency,
            test_timeout_ms=args.timeout * 1000,
        )
        logger.info(f"  Valid nodes: {len(valid_nodes)}")

    # Save outputs
    logger.info("\n[4/4] Saving outputs...")

    # clash.yaml — full config with proxy-groups and rules
    clash_proxies = to_clash_proxies(valid_nodes)
    proxy_names = [p.get('name', f'node-{i}') for i, p in enumerate(clash_proxies)]

    full_clash = {
        'mixed-port': 7890,
        'allow-lan': False,
        'bind-address': '*',
        'mode': 'rule',
        'log-level': 'info',
        'dns': {
            'enable': True,
            'listen': '0.0.0.0:1053',
            'enhanced-mode': 'fake-ip',
            'fake-ip-range': '198.18.0.1/16',
            'nameserver': ['https://dns.google/dns-query', 'https://1.1.1.1/dns-query'],
            'fallback': ['https://dns.alidns.com/dns-query'],
        },
        'proxies': clash_proxies,
        'proxy-groups': [
            {
                'name': 'AUTO',
                'type': 'url-test',
                'proxies': proxy_names,
                'url': 'https://www.gstatic.com/generate_204',
                'interval': 300,
                'tolerance': 50,
            },
            {
                'name': 'PROXY',
                'type': 'select',
                'proxies': ['AUTO'] + proxy_names[:10],
            },
        ],
        'rules': [
            'DOMAIN-SUFFIX,local,DIRECT',
            'DOMAIN-KEYWORD,lan,DIRECT',
            'IP-CIDR,127.0.0.0/8,DIRECT,no-resolve',
            'IP-CIDR,192.168.0.0/16,DIRECT,no-resolve',
            'IP-CIDR,10.0.0.0/8,DIRECT,no-resolve',
            'IP-CIDR,172.16.0.0/12,DIRECT,no-resolve',
            'GEOSITE,cn,DIRECT',
            'GEOIP,cn,DIRECT',
            'MATCH,AUTO',
        ],
    }

    clash_path = os.path.join(output_dir, 'clash.yaml')
    with open(clash_path, 'w', encoding='utf-8') as f:
        yaml.dump(full_clash, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info(f"  Saved: {clash_path} ({len(clash_proxies)} proxies)")

    # all (base64 subscription)
    links_output = []
    for node in valid_nodes:
        tag = node.get('tag', '')
        original_link = link_to_node_map.get(tag, '')
        if original_link:
            links_output.append(original_link)
        else:
            server = node.get('server', '')
            port = node.get('server_port') or node.get('port', '')
            ntype = node.get('type', '')
            links_output.append(f"{ntype}://{tag}@{server}:{port}")

    all_path = os.path.join(output_dir, 'all')
    with open(all_path, 'w') as f:
        f.write(base64.b64encode('\n'.join(links_output).encode()).decode())
    logger.info(f"  Saved: {all_path}")

    logger.info(f"\n{'=' * 50}")
    logger.info(f"  Total valid nodes: {len(valid_nodes)}")
    logger.info(f"{'=' * 50}")

    # Optional: start local proxy
    if args.serve and len(valid_nodes) > 0:
        from core.proxy_server import start_proxy
        start_proxy(clash_path, port=args.port)


if __name__ == "__main__":
    main()
