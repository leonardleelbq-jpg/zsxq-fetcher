# ZSXQ Fetcher

> 🔧 知识星球帖子一键下载 | 🤖 AI 直读星球内容 | 🟢 2026 年唯一在维护的 ZSXQ 工具

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Windows%20%7C%20macOS-✓-blue)]()
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![QQ Group](https://img.shields.io/badge/QQ群-1056687150-12B7F5?logo=tencentqq)](https://qm.qq.com/q/1056687150)

---

## 为什么你需要这个？

知识星球是一个封闭的内容平台——你付费了，但内容锁在网页里。离线看不了，搜索靠手翻，AI 读不了。

**ZSXQ Fetcher 帮你把数据拿回来。** 下载帖子到本地，Markdown 格式离线阅读，还能接入 AI 自动帮你读。

> ⚠️ GitHub 上其他 ZSXQ 下载工具大多已停止维护（2019-2022），API 变更后全部失效。这是 2026 年**唯一能跑**的。

---

## 5 分钟开始

```bash
# 1. 安装
双击 setup.bat

# 2. 获取 token → 填入 scripts/config.json

# 3. 开始下载
python scripts/zsxq_fetcher.py
```

[📖 完整用户手册（保姆级）](docs/用户手册.md)

---

## 能做什么

| 功能 | 命令 |
|------|------|
| 📋 列出所有星球 | `python scripts/zsxq_fetcher.py --list` |
| 📥 下载最新帖子 | `python scripts/zsxq_fetcher.py` |
| 🔢 下载指定数量 | `python scripts/zsxq_fetcher.py --count 50` |
| 🔍 关键词搜索 | `python scripts/zsxq_fetcher.py --search "副业"` |
| 📝 导出 Markdown | `python scripts/zsxq_fetcher.py --format markdown` |
| 🔄 增量同步 | `python scripts/zsxq_fetcher.py --incremental` |
| 📎 下载附件 | `python scripts/zsxq_fetcher.py --download-files` |

---

## 🤖 接入 AI（独家功能）

让 Claude、Codex、Cursor、Windsurf 直接读你的星球——自然语言操作就够了。

```
"列出我的星球"
"搜一下最近关于 AI 的帖子"
"帮我把前 10 条总结一下"
```

支持 MCP 协议，配置一次，永久使用。详见 [用户手册 - 接入 AI](docs/用户手册.md#第五步接入-ai强烈推荐-)。

---

## 为什么这个还能用？

其他工具用的是 HTTP 直接调 API → ZSXQ 改接口 → 全部炸掉。

**我们用 Playwright 模拟真实浏览器。** 行为和正常用户一致，API 怎么改都能自适应。1.5 秒请求间隔，不会触发反爬、不会封号。

| | 竞品（已死） | ZSXQ Fetcher |
|---|---|---|
| 技术 | HTTP 请求 | Playwright 浏览器 |
| API 变更 | 💀 直接挂 | ✅ 自动适应 |
| 反爬风险 | 高 | 低（模拟真人） |
| AI 接入 | ❌ | ✅ MCP 协议 |
| 维护 | 2019-2022 停更 | ✅ 2026 持续更新 |

---

## ⚠️ 合法使用声明

1. 本工具仅供备份**自己已付费购买**的知识星球内容，用于个人离线阅读
2. **禁止**将下载内容公开传播、转售或用于商业目的
3. **禁止**高频请求对平台服务器造成压力
4. 使用本工具产生的任何法律后果由使用者自行承担
5. 请尊重星主的创作版权

---

## 安装

### Windows / macOS

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
python -m playwright install chromium
```

或直接双击 `setup.bat`（Windows）一键完成。

---

## 社区

- 📮 QQ 群：**1056687150**（ZSXQ Fetcher 用户交流）
- 🐛 问题反馈：[GitHub Issues](https://github.com/leonardleelbq-jpg/zsxq-fetcher/issues)
- 📖 使用手册：[docs/用户手册.md](docs/用户手册.md)

---

## Star 历史

如果这个工具对你有帮助，点个 ⭐ 让更多人看到 → 更多用户 → 更多反馈 → 更好的工具。

---

MIT License © 2026 ZSXQ Fetcher Contributors
