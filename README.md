# chalsh

**Free proxy nodes, updated daily. Subscribe and auto-update.**

<div align="center">

[![简体中文](https://img.shields.io/badge/简体中文-Current-blue?style=for-the-badge&logo=markdown)](README_CN.md)

</div>

---

## Quick Start — 3 Steps

### Step 1: Copy your subscription URL

After pushing this repo to GitHub, use the **raw** URL of the output file:

| Format | Subscription URL | For Clients |
|--------|-----------------|-------------|
| **Clash YAML** | `https://raw.githubusercontent.com/<you>/chalsh/main/clash.yaml` | Clash Verge, ClashX, ClashN |
| **Base64 List** | `https://raw.githubusercontent.com/<you>/chalsh/main/all` | v2rayN, v2rayNG, NekoBox |

> Replace `<you>` with your GitHub username after pushing.

### Step 2: Add subscription in your Clash client

#### Clash Verge Rev (Windows/macOS/Linux)

1. Open Clash Verge Rev
2. Go to **Subscriptions** tab
3. Click **New Subscription**
4. Paste the Clash YAML URL from Step 1
5. Set **Update Interval** to `24` (hours)
6. Click **OK** — nodes will auto-refresh every 24h

#### ClashX (macOS)

1. Open ClashX
2. **Config** → **Remote Config** → **Manage**
3. Click **+** → paste the URL → set **Auto Update** to `Daily`
4. **OK**

#### ClashN (Windows)

1. Open ClashN
2. **Subscription** → **Subscription Settings**
3. Paste the URL → **Add** → **OK**
4. **Subscription** → **Update Subscription via Internet**
5. Set auto-update in settings: **Settings** → **Auto Update Interval** → `1440` (minutes = 24h)

#### Mihomo (CLI)

In your `profiles` section, add:

```yaml
profiles:
  - name: chalsh
    type: http
    url: https://raw.githubusercontent.com/<you>/chalsh/main/clash.yaml
    interval: 86400  # 24 hours in seconds
```

### Step 3: Connect

1. Go to **Proxies** tab in your client
2. Select the `chalsh` profile
3. Pick a node or use `AUTO` group (auto-selects fastest)
4. Enable **System Proxy**

---

## Local Run

If you prefer running locally instead of relying on GitHub Actions:

```bash
pip install -r requirements.txt

# Fetch + validate nodes, start local proxy on port 7890
python main.py --validate --serve

# Just fetch and output to a directory
python main.py --output ./output
```

| Flag | Effect |
|------|--------|
| `--validate` | HTTP latency check, filter dead nodes |
| `--serve` | Start local Mihomo proxy at 127.0.0.1:7890 |
| `--port <N>` | Custom proxy port (default 7890) |
| `--output <dir>` | Output directory (default `output`) |
| `--workers <N>` | Concurrent fetch workers (default 10) |

---

## Node Sources

| Source | Protocols |
|--------|-----------|
| Pawdroid/Free-servers | vmess, ss, trojan |
| free18/v2ray | vless, vmess, ss, trojan |
| awesome-vpn/awesome-vpn | vmess, vless, ss, trojan, hysteria2 |
| lerjtl/Testfree | vmess, ss, trojan, vless |
| nodesfree/v2raynode | vmess, vless |
| snakem982/proxypool | vmess, ss, trojan |
| Barabama/FreeNodes | vmess, ss, trojan |
| crashgfw/free-airport-nodes | vmess, vless, ss, trojan, hy2 |

Add more via `config/sources.json` or `EXTRA_URLS` env var.

---

## Update Schedule

| Trigger | Time |
|---------|------|
| GitHub Actions (auto) | Daily 00:00 UTC (08:00 Beijing) |
| GitHub Actions (manual) | Actions tab → Run workflow |
| Local run | `python main.py --validate` |
| Client auto-refresh | Set in client (recommended: 24h) |

---

## Disclaimer

- Aggregates **publicly available** proxy nodes only
- For educational and research purposes
- Users are responsible for complying with local laws
- No warranty — nodes may stop working at any time
- We do not own or control these nodes

---

<p align="center">
  <b>Free Internet for Everyone</b>
</p>
