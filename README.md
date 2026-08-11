# Market Radar Mini Program（沉淀篮）

一个面向中文用户的开源市场研究工具：使用微信原生小程序呈现基金价差核验、美股自选与新闻、前沿资讯、市场情绪和跨市场研究资料，并通过 FastAPI 后端统一处理数据源、缓存与降级。

> 项目只用于信息整理、软件研究与个人学习，不连接券商账户、不自动下单，也不构成投资建议或收益承诺。所有行情、净值、限额和新闻都应以交易所、基金公告、券商页面及原始来源为准。

## 项目状态

- 当前阶段：持续开发中的个人研究工具与开源参考实现。
- 前端：微信原生小程序（WXML、WXSS、TypeScript）。
- 后端：Python、FastAPI、SQLite。
- 部署：支持本机开发、普通 HTTPS 反向代理，以及 CloudBase AnyService 转发到自有后端。
- 测试：目前包含 27 项后端单元测试，并在 GitHub Actions 中执行 Python 测试和 TypeScript 类型检查。

## 核心功能

| 模块 | 功能 | 重要边界 |
| --- | --- | --- |
| 基金价差监控 | 扫描 LOF/QDII 等基金，结合场内价格、净值、申购状态、公开限额、成本和流动性进行筛选 | 不替代基金公告及券商可申购额度确认 |
| 美股自选 | 搜索并添加股票、设置目标价、查看多源行情与关联新闻 | 免费数据源可能延迟、限流或暂时不可用 |
| 前沿资讯 | 聚合科技、AI、政治资讯，翻译外文标题并保留原文链接和来源 | 翻译仅帮助浏览，原文优先 |
| 市场情绪 | 汇总 A 股客观指标、加密市场恐慌贪婪指数以及 BTC/ETH/SOL 行情 | 情绪指标不代表买卖信号 |
| AI 投研 | 跨市场搜索、研究档案、异步任务和个人笔记 | 模型能力需要服务端单独配置 API；结果必须人工核验 |

## 架构

```text
微信小程序
   │
   │ 统一请求封装
   ▼
CloudBase AnyService 或 HTTPS API
   │
   ▼
FastAPI
   ├─ 基金价差引擎
   ├─ 美股行情与新闻聚合
   ├─ 科技 / AI / 政治资讯聚合
   ├─ 市场情绪引擎
   ├─ 跨市场研究引擎
   └─ SQLite（仅运行期数据）
```

设计重点是“结构稳定、来源可追溯、失败可降级”：单个外部数据源超时不会让整个页面白屏，接口会保留来源和可用性状态，前端据此展示真实数据、待核实状态或不可用提示。

## 目录结构

```text
miniprogram/             微信小程序前端
main.py                  FastAPI 入口及美股接口
arbitrage_engine.py      基金价差与容量计算
market_sentiment.py      市场情绪计算
news_engine.py           每日资讯聚合与标题翻译
research_engine.py       研究档案、AI 任务与笔记
deploy/                  systemd / Nginx 示例
test_*.py                后端单元测试
ARBITRAGE.md             基金计算逻辑说明
CLOUDBASE.md             CloudBase AnyService 接入说明
DEPLOYMENT.md            VPS 与 HTTPS 部署说明
PROJECT_0_TO_1.md        从需求到部署的实践复盘
```

## 快速开始

### 1. 启动后端

需要 Python 3.10+。

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Linux/macOS：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000/health`，应返回 `status: ok`。没有配置任何付费 API Key 时，基础功能仍可运行，但部分美股新闻、研究数据和 AI 分析会降级。

### 2. 启动小程序

需要 Node.js 18+ 和微信开发者工具。

```powershell
npm install
npm run build
```

然后：

1. 在微信开发者工具中导入仓库根目录。
2. 本机调试时，将 `miniprogram/utils/config.ts` 的 `USE_LOCAL_API_IN_DEVTOOLS` 临时设为 `true`。
3. 修改 TypeScript 后再次执行 `npm run build`，确保生成的 JavaScript 同步更新。
4. 真机部署请阅读 [CLOUDBASE.md](CLOUDBASE.md) 或 [DEPLOYMENT.md](DEPLOYMENT.md)，并替换示例环境标识、域名和服务器地址。

## 可选服务端配置

真实密钥只能设置在本机环境变量、VPS 的受限环境文件或密钥管理服务中，禁止写入小程序源码和 Git。

| 变量 | 用途 | 未配置时 |
| --- | --- | --- |
| `FINNHUB_API_KEY` | 美股公司新闻、财务指标、SEC 申报和分析师评级 | 使用公开备用源或显示不可用 |
| `AI_BASE_URL` | OpenAI-compatible 服务地址 | AI 任务保持未配置状态 |
| `AI_API_KEY` | AI 服务密钥 | AI 任务保持未配置状态 |
| `AI_MODEL` | 模型 ID | AI 任务保持未配置状态 |
| `AI_TIMEOUT` | AI 请求超时秒数 | 默认使用代码配置 |
| `RESEARCH_DB_PATH` | 研究笔记数据库路径 | 使用 `data/` 下的默认路径 |
| `ARBITRAGE_DB_PATH` | 基金历史数据库路径 | 使用 `data/` 下的默认路径 |

示例见 [.env.example](.env.example)。项目不会自动读取 `.env`；请通过当前 Shell、systemd、容器或其他部署工具注入环境变量。

## API 概览

| 路径 | 说明 |
| --- | --- |
| `GET /health` | 服务健康检查 |
| `GET /api/arbitrage` | 基金价差与申购状态快照 |
| `GET /api/arbitrage/history/{code}` | 单只基金历史记录 |
| `GET /api/stocks/search?q=` | 美股代码搜索 |
| `GET /api/portfolio?symbols=` | 美股行情和关联新闻 |
| `GET /api/news` | 科技、AI、政治资讯 |
| `GET /api/market` | 市场情绪与加密资产行情 |
| `GET /api/research/*` | 研究资料、笔记和任务接口 |

## 验证

```powershell
npm run typecheck
npm test
```

涉及外部数据源的变更还应人工确认：超时行为、来源标签、时间戳、原文链接、空数据状态和降级顺序。不要用一次成功的网页抓取替代长期稳定性验证。

## 数据、隐私与安全

- 不收集或保存券商账号、身份证、短信验证码、交易密码和自动交易授权。
- 自选股和目标价默认保存在小程序本地；研究笔记与运行历史存放在部署者自己的 SQLite 数据库中。
- `data/*.db`、`.env`、私钥和本机配置均被排除在版本控制之外。
- 公网部署前必须加入访问控制、请求限速、日志轮转、数据库备份和最小权限策略。
- 如果发现漏洞，请阅读 [SECURITY.md](SECURITY.md)，不要在公开 Issue 中披露密钥或可利用细节。

## 参与贡献

欢迎提交数据源适配、稳定性修复、测试、文档和无障碍改进。金融数据相关变更必须附带来源、时间口径、失败策略和测试。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

计划中的安全与数据质量工作见 [ROADMAP.md](ROADMAP.md)，已完成的重要版本变化见 [CHANGELOG.md](CHANGELOG.md)。

## 第三方项目与许可证

项目对部分开源项目的功能设计进行了研究，具体归属见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本仓库自身代码采用 [MIT License](LICENSE) 发布；第三方服务、数据和依赖仍分别受其自身条款约束。
