# Cube Radar 🛰️

Cube Sandbox 应用/集成监测工具（方案 A · MVP）。

零成本、本地运行、数据自有。覆盖 Hacker News / GitHub Issues&PR / GitHub Code Search / Reddit / Google News 五大数据源，输出精美的 HTML 报告。

除了常规的"舆论提及监测"，还内置**代码集成扫描器**——通过 Cube 原生 API 指纹（`CubeSandboxClient` / `envdAccessToken` / `X-API-Key` 等）扫描全 GitHub 代码，发现"默默集成、不喊出来"的项目。

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. （可选）编辑配置
vim config.yaml   # 添加 GitHub token 可提高 rate limit

# 3. 一键扫描 + 报告
python __main__.py all --window 7d

# 报告会保存到 reports/report-7d-<timestamp>.html
# 直接用浏览器打开即可
```

## 📋 命令

```bash
python __main__.py scan --window 24h    # 只采集数据
python __main__.py report --window 7d   # 只生成报告（基于已有数据）
python __main__.py all --window 30d     # 采集 + 报告（一步到位）
```

支持的窗口：`24h` / `3d` / `7d` / `30d` / `180d`

## 📊 报告内容

- **4 个核心 KPI**：总提及数、唯一作者、互动总量、峰值日
- **声量趋势曲线**：按天、按平台分层的折线图
- **平台分布饼图 + 占比表**
- **Top 15 热门提及卡片**（按互动量排序）
- **应用集成情况表**：通过代码指纹检测到的 Cube 集成项目，含 repo / 星级 / 指纹数 / 命中文件 / 信号价值评级（★★★★★）
- **PR / Issue 提及表**：GitHub 上提及 Cube 的 issue 和 PR（跨全 GitHub 搜索 + 本仓库 PR）
- **全部提及表格**（最近 50 条）

## 🛠️ 配置

编辑 `config.yaml`：

```yaml
keywords:
  primary:
    - "Cube Sandbox"
    - "CubeSandbox"
    # 添加你想监测的新关键词

github_token: "ghp_xxx"  # 可选，配置后 rate limit 60/h → 5000/h
```

### 代码集成扫描配置

```yaml
sources:
  github_code: true      # 开启代码集成指纹扫描（需要 github_token）

code_search:
  repo_blacklist: "TencentCloud/CubeSandbox"  # 排除自己仓库
  fingerprints: []       # 留空用默认指纹清单，或自定义追加
```

默认指纹清单（在 `collectors/github_code.py` 的 `CODE_FINGERPRINTS`）：
- 类名：`CubeSandboxClient` / `CubeSandboxConfig` / `CubeSandboxProvider`
- 环境变量：`AGENT_SPACE_CUBE` / `CUBESANDBOX_API_KEY` / `CUBESANDBOX_API_URL`
- 包名 import：`cubesandbox in:file language:typescript/python/go/rust`
- 文件路径：`path:*/cube/cube-client*`

> ⚠️ 设计教训：`envdAccessToken` / `trafficAccessToken` / `CUBE_TEMPLATE_ID` 看似 Cube 独有，实际是 E2B envd 协议通用字段，dify/cmux/suna 等仅适配 E2B 的项目也会命中，已从指纹清单移除。

## 🌐 公网部署（GitHub Pages）

报告可以一键部署到 GitHub Pages，得到公网访问地址：

```bash
# 1. reports 目录已初始化为独立 git 仓库，推送到你自己的 GitHub 账号
cd reports
gh repo create cube-radar --public --source=. --push

# 2. 开启 GitHub Pages（从 main 分支根目录托管）
gh api -X POST /repos/<你的用户名>/cube-radar/pages \
  -f "source[branch]=main" -f "source[path]=/"

# 3. 等 1-2 分钟，访问 https://<你的用户名>.github.io/cube-radar/
```

以后更新报告，在项目根目录跑：

```bash
./deploy.sh 7d    # 生成 7d 报告 + 复制为 index.html + 推送
```

GitHub Pages 会在 1-2 分钟内自动更新。

## 🗂️ 文件结构

```
cube-radar/
├── __main__.py          # CLI 入口
├── config.yaml          # 配置文件（含 GitHub token、代码指纹配置）
├── store.py             # SQLite 存储
├── report.py            # HTML 报告生成（含雷达 favicon + 双语 i18n）
├── deploy.sh            # 一键部署到 GitHub Pages
├── collectors/          # 数据采集器
│   ├── hackernews.py    # HN Algolia API
│   ├── github.py        # GitHub Issues/PRs/Stargazers
│   ├── github_code.py   # GitHub Code Search（代码集成指纹扫描）
│   ├── reddit.py        # Reddit JSON
│   ├── google_news.py   # Google News RSS
│   └── relevance.py     # 关键词严格过滤（排除 Minecraft/cube.js 等误命中）
├── data/                # SQLite 数据库（运行后生成）
│   └── radar.db
└── reports/             # HTML 报告输出（已初始化为 git 仓库，推送至 GitHub Pages）
    └── report-*.html
```

## 🔮 路线图

- [x] GitHub Code Search 代码集成指纹扫描（发现"默默集成"的项目）
- [x] 应用集成情况表 + PR/Issue 提及板块
- [x] 雷达 favicon + EN/中文双语切换
- [x] GitHub Pages 公网部署 + 一键 deploy 脚本
- [ ] X / Twitter 关键账号订阅式抓取（基于 RSSHub）
- [ ] dub.co 短链 API 集成（看渠道点击）
- [ ] CSDN / 掘金 / 知乎 关键词搜索抓取
- [ ] 每日定时邮件 / Slack 推送
- [ ] 与 GitHub Traffic API 集成（referrer 数据）
- [ ] Reddit 采集器修复（当前 old.reddit.com 返回 403）
