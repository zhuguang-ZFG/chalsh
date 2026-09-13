"""Local proxy server — spins up Clash Meta kernel for immediate VPN use."""

import os
import subprocess
import sys
import time
import signal
import logging
import platform

import yaml

logger = logging.getLogger(__name__)


def _download_mihomo(dest_path):
    """Download latest Mihomo (Clash Meta) binary."""
    import requests

    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ('x86_64', 'amd64'):
        machine = 'amd64'
    elif machine in ('aarch64', 'arm64'):
        machine = 'arm64'

    os_map = {'windows': 'windows', 'linux': 'linux', 'darwin': 'darwin'}
    arch_map = {'amd64': 'amd64', 'arm64': 'arm64', 'aarch64': 'arm64'}

    os_name = os_map.get(system, system)
    arch = arch_map.get(machine, machine)

    suffix = '.exe' if os_name == 'windows' else ''
    filename = f'mihomo-{os_name}-{arch}{suffix}'

    api_url = 'https://api.github.com/repos/MetaCubeX/mihomo/releases/latest'
    resp = requests.get(api_url, timeout=15)
    resp.raise_for_status()
    assets = resp.json().get('assets', [])

    asset = None
    for a in assets:
        if filename in a['name'] and not a['name'].endswith('.gz'):
            asset = a
            break

    if not asset:
        # Fallback: try matching without exact suffix
        for a in assets:
            if os_name in a['name'] and arch in a['name']:
                asset = a
                break

    if not asset:
        logger.error(f"Could not find Mihomo binary for {os_name}/{arch}")
        return False

    logger.info(f"Downloading Mihomo: {asset['name']} ({asset['size'] / 1024 / 1024:.1f} MB)")
    dl_resp = requests.get(asset['browser_download_url'], headers={'Accept': 'application/octet-stream'}, timeout=120, stream=True)
    dl_resp.raise_for_status()
    with open(dest_path, 'wb') as f:
        for chunk in dl_resp.iter_content(chunk_size=8192):
            f.write(chunk)
    os.chmod(dest_path, 0o755)
    return True


def _get_mihomo_path():
    """Find or download Mihomo binary."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bin_dir = os.path.join(base_dir, 'bin')
    os.makedirs(bin_dir, exist_ok=True)

    system = platform.system().lower()
    suffix = '.exe' if system == 'windows' else ''
    binary_path = os.path.join(bin_dir, f'mihomo{suffix}')

    if os.path.exists(binary_path):
        return binary_path

    logger.info("Mihomo binary not found, downloading...")
    if _download_mihomo(binary_path):
        return binary_path
    return None


def _build_mihomo_config(clash_yaml_path, port):
    """Build a minimal Mihomo config from clash.yaml."""
    with open(clash_yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    proxies = config.get('proxies', [])
    if not proxies:
        logger.error("No proxies found in clash.yaml")
        return None

    proxy_names = [p.get('name', f"node-{i}") for i, p in enumerate(proxies)]

    mihomo_config = {
        'mixed-port': port,
        'allow-lan': False,
        'log-level': 'info',
        'proxies': proxies,
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
                'name': 'DIRECT',
                'type': 'select',
                'proxies': ['DIRECT'],
            },
        ],
        'rules': [
            'GEOSITE,cn,DIRECT',
            'GEOIP,cn,DIRECT',
            'MATCH,AUTO',
        ],
    }

    # Write to temp file
    config_path = os.path.join(os.path.dirname(clash_yaml_path), 'mihomo_config.yaml')
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(mihomo_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return config_path


def start_proxy(clash_yaml_path, port=7890):
    """Start a local Mihomo proxy server."""
    binary = _get_mihomo_path()
    if not binary:
        logger.error("Cannot start proxy: Mihomo binary not available")
        return

    config_path = _build_mihomo_config(clash_yaml_path, port)
    if not config_path:
        return

    logger.info(f"Starting local proxy on port {port}...")
    logger.info(f"  Mixed port: {port}")
    logger.info(f"  HTTP proxy: http://127.0.0.1:{port}")
    logger.info(f"  SOCKS5 proxy: socks5://127.0.0.1:{port}")
    logger.info("  Press Ctrl+C to stop")

    cmd = [binary, '-d', os.path.dirname(config_path), '-f', config_path]
    proc = subprocess.Popen(cmd)

    def _signal_handler(signum, frame):
        logger.info("\nShutting down proxy...")
        proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        logger.info("Proxy stopped.")
