import hashlib

class Deduplicator:
    """Three-tier deduplication: link → server:port:protocol → full node hash."""

    def __init__(self):
        self.seen_hashes = set()
        self.seen_server_ports = set()

    def is_duplicate(self, node):
        """Check if node is a duplicate based on full property hash."""
        node_hash = self._calculate_hash(node)
        if node_hash in self.seen_hashes:
            return True
        self.seen_hashes.add(node_hash)
        return False

    def is_redundant_server(self, node):
        """
        Check if server:port:protocol combo already seen.
        Keeps only the first node per server+port+protocol combination.
        """
        server = node.get('server', '')
        port = str(node.get('server_port') or node.get('port', ''))
        ntype = node.get('type', '')

        if not server or not port:
            return False

        key = f"{server}:{port}:{ntype}"
        if key in self.seen_server_ports:
            return True
        self.seen_server_ports.add(key)
        return False

    def reset(self):
        self.seen_hashes.clear()
        self.seen_server_ports.clear()

    def _calculate_hash(self, data):
        """
        Calculate a deterministic hash based on node identity properties.
        Two nodes with the same identity (same server, port, type, and auth/transport)
        should produce the same hash.
        """
        try:
            ntype = data.get('type', '')
            server = data.get('server', '')
            port = str(data.get('server_port') or data.get('port', ''))

            parts = [ntype, server, port]

            if ntype in ('vmess', 'vless'):
                parts.append(data.get('uuid', ''))
                parts.append(str(data.get('flow', '')))
                parts.append(str(data.get('tls', False)))
                transport = data.get('transport', {})
                if transport:
                    parts.append(transport.get('type', ''))
                    if transport.get('type') == 'ws':
                        parts.append(transport.get('path', ''))
                        parts.append(transport.get('headers', {}).get('Host', ''))
                    elif transport.get('type') == 'grpc':
                        parts.append(transport.get('service_name', ''))
                    elif transport.get('type') == 'http':
                        parts.append(','.join(sorted(transport.get('host', []))))
                        parts.append(transport.get('path', ''))
            elif ntype == 'trojan':
                parts.append(data.get('password', ''))
                transport = data.get('transport', {})
                if transport:
                    parts.append(transport.get('type', ''))
                    if transport.get('type') == 'ws':
                        parts.append(transport.get('path', ''))
                        parts.append(transport.get('headers', {}).get('Host', ''))
                    elif transport.get('type') == 'grpc':
                        parts.append(transport.get('service_name', ''))
            elif ntype == 'shadowsocks':
                parts.append(data.get('method', ''))
                parts.append(data.get('password', ''))
            elif ntype in ('hysteria2', 'hy2', 'tuic'):
                parts.append(data.get('uuid', '') or data.get('password', ''))
                parts.append(str(data.get('sni', '')))
            else:
                # Fallback: hash the entire node
                parts.append(str(sorted(data.items())))

            raw = '|'.join(parts)
            return hashlib.sha256(raw.encode()).hexdigest()
        except Exception:
            return hashlib.sha256(str(data).encode()).hexdigest()
