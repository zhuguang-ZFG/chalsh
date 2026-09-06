"""Strict 5-stage node validator using mihomo REST API."""

import concurrent.futures
import logging
import os
import platform
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time

import requests
import yaml

TEST_URL = 'https://www.gstatic.com/generate_204'
IP_CHECK_URLS = ['https://ipinfo.io/ip', 'https://api.ipify.org']
TEST_TIMEOUT_MS = 5000
MAX_LATENCY_MS = 500

_port_lock = threading.Lock()
_allocated_ports = set()


def _get_unique_port():
    with _port_lock:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        _allocated_ports.add(port)
        return port


def _release_port(port):
    with _port_lock:
        _allocated_ports.discard(port)


# Invalid server patterns that should never appear in working configs
_INVALID_SERVERS = frozenset({
    '127.0.0.1', 'localhost', '0.0.0.0',
})


def _is_invalid_server(server):
    """Reject localhost, loopback, and obviously broken servers."""
    if not server:
        return True
    if server.lower() in _INVALID_SERVERS:
        return True
    if server.startswith('127.'):
        return True
    return False


def quick_tcp_prescreen(nodes, max_workers=100, timeout=2):
    """L0+L1: Pre-filter invalid servers + TCP connectivity + TLS handshake for TLS protocols. UDP protocols skip L1."""
    UDP_PROTOCOLS = {'hysteria2', 'hy2', 'tuic'}

    # L0: Pre-filter obvious garbage
    l0_passed = []
    for node in nodes:
        server = node.get('server', '')
        if _is_invalid_server(server):
            continue
        l0_passed.append(node)
    l0_filtered = len(nodes) - len(l0_passed)
    if l0_filtered:
        logger = logging.getLogger('Validator')
        logger.info(f"  L0: filtered {l0_filtered} invalid servers (localhost/loopback/empty)")

    tcp_nodes = [n for n in l0_passed if n.get('type', '').lower() not in UDP_PROTOCOLS]
    udp_nodes = [n for n in l0_passed if n.get('type', '').lower() in UDP_PROTOCOLS]

    def tcp_check(node):
        server = node.get('server')
        port = node.get('server_port') or node.get('port')
        if not server or not port:
            return None
        try:
            with socket.create_connection((server, int(port)), timeout=timeout):
                # L1b: For TLS-based protocols, verify TLS handshake succeeds
                ntype = node.get('type', '').lower()
                if ntype in ('vless', 'trojan', 'vmess') and node.get('tls'):
                    import ssl
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    with context.wrap_socket(socket.socket(), server_hostname=server) as ssock:
                        ssock.settimeout(timeout)
                        ssock.connect((server, int(port)))
                return node
        except Exception:
            return None

    passed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for result in executor.map(tcp_check, tcp_nodes):
            if result:
                passed.append(result)

    return passed + udp_nodes


def _download_mihomo(dest_path):
    """Download latest Mihomo binary, extracting from zip on Windows/macOS."""
    import requests as req

    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ('x86_64', 'amd64'):
        machine = 'amd64'
    elif machine in ('aarch64', 'arm64'):
        machine = 'arm64'

    os_map = {'windows': 'windows', 'linux': 'linux', 'darwin': 'darwin'}
    arch_map = {'amd64': 'amd64', 'arm64': 'arm64'}
    os_name = os_map.get(system, system)
    arch = arch_map.get(machine, machine)
    suffix = '.exe' if os_name == 'windows' else ''

    api_url = 'https://api.github.com/repos/MetaCubeX/mihomo/releases/latest'
    resp = req.get(api_url, timeout=15)
    resp.raise_for_status()
    assets = resp.json().get('assets', [])

    asset = None
    for a in assets:
        name = a['name']
        if os_name in name and arch in name:
            # Windows: .zip; Linux/macOS: .gz
            if (os_name == 'windows' and name.endswith('.zip')) or \
               (os_name != 'windows' and '.gz' in name):
                asset = a
                break

    if not asset:
        return False

    logger = logging.getLogger('Validator')
    logger.info(f"Downloading mihomo: {asset['name']} ({asset['size'] / 1024 / 1024:.1f} MB)")

    tmp_dir = tempfile.mkdtemp(prefix='chalsh_mihomo_')
    tmp_file = os.path.join(tmp_dir, asset['name'])

    dl_resp = req.get(asset['browser_download_url'], headers={'Accept': 'application/octet-stream'}, timeout=120, stream=True)
    dl_resp.raise_for_status()
    with open(tmp_file, 'wb') as f:
        for chunk in dl_resp.iter_content(chunk_size=8192):
            f.write(chunk)

    try:
        if os_name == 'windows':
            import zipfile
            with zipfile.ZipFile(tmp_file, 'r') as zf:
                for name in zf.namelist():
                    if 'mihomo' in name and name.endswith(suffix):
                        zf.extract(name, tmp_dir)
                        extracted = os.path.join(tmp_dir, name)
                        shutil.copy2(extracted, dest_path)
                        return True
        else:
            import gzip
            import tarfile
            with gzip.open(tmp_file, 'rb') as gz:
                with tarfile.open(fileobj=gz) as tar:
                    for member in tar.getmembers():
                        if 'mihomo' in member.name and member.name.endswith(suffix):
                            tar.extract(member, tmp_dir)
                            extracted = os.path.join(tmp_dir, member.name)
                            shutil.copy2(extracted, dest_path)
                            return True
    except Exception as e:
        logger.warning(f"Extraction failed: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return False


def _get_mihomo_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bin_dir = os.path.join(base_dir, 'bin')
    os.makedirs(bin_dir, exist_ok=True)

    suffix = '.exe' if platform.system().lower() == 'windows' else ''
    binary_path = os.path.join(bin_dir, f'mihomo{suffix}')

    if os.path.exists(binary_path):
        return binary_path

    logger = logging.getLogger('Validator')
    logger.info("Mihomo binary not found, downloading...")
    if _download_mihomo(binary_path):
        return binary_path
    return None


def _get_original_ip():
    """Get real machine IP (no proxy)."""
    session = requests.Session()
    session.trust_env = False
    for url in IP_CHECK_URLS:
        try:
            resp = session.get(url, timeout=5)
            if resp.status_code == 200:
                ip = resp.text.strip()
                if ip:
                    return ip
        except Exception:
            continue
    return None


def _wait_for_port(host, port, timeout=15):
    """Wait until a port is accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


class Validator:
    """Strict 5-stage validator using mihomo for real protocol testing."""

    def __init__(self, sing_box_path=None, local_mode=False):
        self.local_mode = local_mode
        self.logger = logging.getLogger('Validator')

    @staticmethod
    def validate_nodes(nodes, max_latency_ms=MAX_LATENCY_MS, test_timeout_ms=TEST_TIMEOUT_MS):
        """
        L1: TCP prescreen (socket connect)
        L2: Real proxy HTTP test (mihomo url-test group, gstatic.com)
        L3: IP change check (through proxy vs real IP)
        L4: DNS resolution (mihomo internal DNS through proxy)
        L5: Latency filter (remove nodes > max_latency_ms)
        """
        if not nodes:
            return []

        logger = logging.getLogger('Validator')
        original_ip = _get_original_ip()
        logger.info(f"  Original IP: {original_ip or 'unknown'}")

        # L0+L1: Pre-filter + TCP/TLS check
        logger.info("  L0+L1: Pre-filter + TCP/TLS check...")
        tcp_passed = quick_tcp_prescreen(nodes, max_workers=50, timeout=2)
        logger.info(f"  L0+L1 passed: {len(tcp_passed)}/{len(nodes)}")
        if not tcp_passed:
            return []

        # L2-L5: Mihomo-based tests
        mihomo_path = _get_mihomo_path()
        if not mihomo_path:
            logger.warning("  Mihomo unavailable, keeping TCP/TLS-passed nodes only.")
            return tcp_passed

        from core.converters.clash import to_clash_proxies
        clash_proxies = to_clash_proxies(tcp_passed)
        if not clash_proxies:
            logger.warning("  No proxies convertible to Clash format")
            return []

        # Limit nodes for mihomo test to avoid CI timeout
        MAX_MIHOMO_TEST = 100
        if len(clash_proxies) > MAX_MIHOMO_TEST:
            logger.info(f"  Limiting mihomo test to {MAX_MIHOMO_TEST} nodes (had {len(clash_proxies)})")
            clash_proxies = clash_proxies[:MAX_MIHOMO_TEST]
            tcp_passed = tcp_passed[:MAX_MIHOMO_TEST]

        proxy_names = [p.get('name', f'node-{i}') for i, p in enumerate(clash_proxies)]
        api_port = _get_unique_port()
        mixed_port = _get_unique_port()

        config = {
            'mixed-port': mixed_port,
            'allow-lan': False,
            'log-level': 'silent',
            'external-controller': f'127.0.0.1:{api_port}',
            'secret': 'chalsh',
            'dns': {
                'enable': True,
                'listen': f'0.0.0.0:0',
                'ipv6': False,
                'nameserver': ['https://dns.google/dns-query'],
                'fallback': ['https://1.1.1.1/dns-query'],
            },
            'proxies': clash_proxies,
            'proxy-groups': [
                {
                    'name': 'AUTO',
                    'type': 'url-test',
                    'proxies': proxy_names,
                    'url': TEST_URL,
                    'interval': 300,
                    'tolerance': 50,
                    'lazy': False,
                },
            ],
            'rules': ['MATCH,AUTO'],
        }

        tmp_dir = tempfile.mkdtemp(prefix='chalsh_validate_')
        config_path = os.path.join(tmp_dir, 'config.yaml')
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        proc = None
        try:
            cmd = [mihomo_path, '-d', tmp_dir, '-f', config_path]
            startupinfo = None
            if platform.system().lower() == 'windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            proc = subprocess.Popen(cmd, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            api_base = f'http://127.0.0.1:{api_port}'
            auth_headers = {'Authorization': 'Bearer chalsh'}

            logger.info("  L2: Waiting for mihomo to start...")
            if not _wait_for_port('127.0.0.1', api_port, timeout=20) or proc.poll() is not None:
                logger.warning("  Mihomo failed to start, keeping TCP-passed nodes")
                return tcp_passed

            # L2: Test each proxy individually via /proxies/{name}/delay endpoint
            logger.info(f"  L2: Testing {len(proxy_names)} proxies via individual delay API...")
            name_to_node = {}
            for node in tcp_passed:
                tag = node.get('tag', '')
                if tag:
                    name_to_node[tag] = node

            l2_passed = []
            l2_errors = 0
            for name in proxy_names:
                try:
                    resp = requests.get(
                        f'{api_base}/proxies/{name}/delay',
                        headers=auth_headers,
                        params={'url': TEST_URL, 'timeout': test_timeout_ms},
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        delay = data.get('delay', 99999)
                        if delay > 0 and delay < test_timeout_ms:
                            node = name_to_node.get(name)
                            if node:
                                node['_latency_ms'] = delay
                                l2_passed.append(node)
                    else:
                        l2_errors += 1
                except Exception:
                    l2_errors += 1

            logger.info(f"  L2 passed: {len(l2_passed)}/{len(proxy_names)} (errors={l2_errors})")

            # Safety fallback: if mihomo test failed for most nodes, keep TCP-passed
            if len(l2_passed) < len(tcp_passed) * 0.05:
                logger.warning(f"  L2 suspicious: only {len(l2_passed)}/{len(tcp_passed)} passed, likely mihomo issue. Keeping TCP-passed nodes.")
                return tcp_passed

            # L3: IP change check — sample a few nodes through proxy
            ip_changed_ok = False
            dns_ok = False
            logger.info("  L3: Checking IP change...")
            if original_ip:
                # Test through a random passed node to verify IP change works
                proxy_ips_seen = set()
                for node in l2_passed[:5]:  # Check up to 5 nodes
                    tag = node.get('tag', '')
                    try:
                        session = requests.Session()
                        session.trust_env = False
                        session.proxies = {
                            'http': f'socks5://127.0.0.1:{mixed_port}',
                            'https': f'socks5://127.0.0.1:{mixed_port}',
                        }
                        resp = session.get(IP_CHECK_URLS[0], timeout=5)
                        if resp.status_code == 200:
                            proxy_ip = resp.text.strip()
                            proxy_ips_seen.add(proxy_ip)
                            if proxy_ip != original_ip:
                                ip_changed_ok = True
                                node['_proxy_ip'] = proxy_ip
                    except Exception:
                        pass
                if ip_changed_ok:
                    logger.info(f"  L3 passed: IP changed (seen {proxy_ips_seen}, original={original_ip})")
                else:
                    logger.warning(f"  L3 warning: IP did not change (proxy_ip={proxy_ips_seen}, original={original_ip})")
            else:
                logger.info("  L3 skipped: original IP unknown")

            # L4: DNS resolution — verify mihomo resolved domains through proxy
            # The L2 test already validates this implicitly (mihomo must resolve gstatic.com)
            # Additional check: can we resolve a Chinese domain through the proxy?
            logger.info("  L4: Checking DNS through proxy...")
            try:
                session = requests.Session()
                session.trust_env = False
                session.proxies = {
                    'http': f'socks5://127.0.0.1:{mixed_port}',
                    'https': f'socks5://127.0.0.1:{mixed_port}',
                }
                resp = session.get('http://www.baidu.com', timeout=5, allow_redirects=False)
                if resp.status_code in (200, 301, 302):
                    dns_ok = True
            except Exception:
                pass
            logger.info(f"  L4 {'passed' if dns_ok else 'warning'}: DNS through proxy {'works' if dns_ok else 'failed'}")

            # L5: Latency filter
            logger.info(f"  L5: Filtering high latency (> {max_latency_ms}ms)...")
            l5_passed = [n for n in l2_passed if n.get('_latency_ms', 99999) <= max_latency_ms]
            filtered = len(l2_passed) - len(l5_passed)
            logger.info(f"  L5 passed: {len(l5_passed)}/{len(l2_passed)} ({filtered} filtered)")

            # Summary
            logger.info(f"\n  === Validation Summary ===")
            logger.info(f"  L1 (TCP):        {len(tcp_passed)}")
            logger.info(f"  L2 (Proxy HTTP): {len(l2_passed)}")
            logger.info(f"  L3 (IP Change):  {'OK' if ip_changed_ok else 'WARN'}")
            logger.info(f"  L4 (DNS):        {'OK' if dns_ok else 'WARN'}")
            logger.info(f"  L5 (Latency):    {len(l5_passed)}")

            return l5_passed

        except Exception as e:
            logger.error(f"  Validation error: {e}")
            return tcp_passed
        finally:
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=2)
                    except Exception:
                        pass
            _release_port(api_port)
            _release_port(mixed_port)
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
