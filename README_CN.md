# chalsh

**免费代理节点，每日自动更新。订阅即用，客户端自动刷新。**

<div align="center">

[![English](https://img.shields.io/badge/English-Switch-blue?style=for-the-badge&logo=markdown)](README.md)
[![简体中文](https://img.shields.io/badge/简体中文-当前-green?style=for-the-badge&logo=markdown)](README_CN.md)

</div>

---

## 快速开始 — 3 步

### 第一步：复制订阅 URL

推送本仓库到 GitHub 后，使用输出文件的 **raw** 地址：

| 格式 | 订阅 URL | 适用客户端 |
|------|----------|-----------|
| **Clash YAML** | `https://raw.githubusercontent.com/<你的用户名>/chalsh/main/clash.yaml` | Clash Verge、ClashX、ClashN |
| **Base64 列表** | `https://raw.githubusercontent.com/<你的用户名>/chalsh/main/all` | v2rayN、v2rayNG、NekoBox |

> 将 `<你的用户名>` 替换为你的 GitHub 用户名。

### 第二步：在客户端中添加订阅

#### Clash Verge Rev（Windows/macOS/Linux）

1. 打开 Clash Verge Rev
2. 进入 **订阅** 标签页
3. 点击 **新建订阅**
4. 粘贴第一步的 Clash YAML URL
5. 设置 **更新间隔** 为 `24`（小时）
6. 点击 **确定** — 节点将每 24 小时自动刷新

#### ClashX（macOS）

1. 打开 ClashX
2. **配置** → **远程配置** → **管理**
3. 点击 **+** → 粘贴 URL → 设置 **自动更新** 为 `每天`
4. **确定**

#### ClashN（Windows）

1. 打开 ClashN
2. **订阅** → **订阅设置**
3. 粘贴 URL → **添加** → **确定**
4. **订阅** → **通过互联网更新订阅**
5. 设置自动更新：**设置** → **自动更新间隔** → `1440`（分钟 = 24 小时）

#### Mihomo（CLI）

在 `profiles` 中添加：

```yaml
profiles:
  - name: chalsh
    type: http
    url: https://raw.githubusercontent.com/<你的用户名>/chalsh/main/clash.yaml
    interval: 86400  # 24 小时（秒）
```

### 第三步：连接上网

1. 在客户端中进入 **代理** 标签
2. 选择 `chalsh` 配置
3. 选择节点或使用 `AUTO` 组（自动选最快）
4. 开启 **系统代理**

---

## 本地运行

如果不想依赖 GitHub Actions，可以在本地手动运行：

```bash
pip install -r requirements.txt

# 抓取 + 验证节点，启动本地代理（端口 7890）
python main.py --validate --serve

# 仅抓取输出到指定目录
python main.py --output ./output
```

| 参数 | 作用 |
|------|------|
| `--validate` | HTTP 延迟测试，过滤失效节点 |
| `--serve` | 启动本地 Mihomo 代理 127.0.0.1:7890 |
| `--port <N>` | 自定义代理端口（默认 7890） |
| `--output <dir>` | 输出目录（默认 `output`） |
| `--workers <N>` | 并发抓取数（默认 10） |

---

## 节点来源

| 来源 | 协议 |
|------|------|
| Pawdroid/Free-servers | vmess, ss, trojan |
| free18/v2ray | vless, vmess, ss, trojan |
| awesome-vpn/awesome-vpn | vmess, vless, ss, trojan, hysteria2 |
| lerjtl/Testfree | vmess, ss, trojan, vless |
| nodesfree/v2raynode | vmess, vless |
| snakem982/proxypool | vmess, ss, trojan |
| Barabama/FreeNodes | vmess, ss, trojan |
| crashgfw/free-airport-nodes | vmess, vless, ss, trojan, hy2 |

通过 `config/sources.json` 或 `EXTRA_URLS` 环境变量可添加更多来源。

---

## 更新频率

| 触发方式 | 时间 |
|---------|------|
| GitHub Actions（自动） | 每日 00:00 UTC（北京时间 08:00） |
| GitHub Actions（手动） | Actions 标签 → Run workflow |
| 本地运行 | `python main.py --validate` |
| 客户端自动刷新 | 在客户端中设置（推荐 24 小时） |

---

## 免责声明

- 本项目聚合**互联网公开的**代理节点
- **仅供学习研究使用**
- 请遵守当地法律法规
- **不保证可用性** — 节点随时可能失效
- 我们不拥有或控制这些节点

---

<p align="center">
  <b>人人享有自由互联网</b>
</p>
