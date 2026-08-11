# 沉淀篮：从 0 到 1 落地复盘

> 本文记录项目从需求、编码、本地调试、Git、VPS 部署，到 CloudBase 真机接入的完整过程。当前项目定位为个人自用研究工具，不公开提供金融服务，也不构成投资建议。

## 1. 最初目标

把分散的信息集中到一个微信小程序中，形成五个页面：

1. **A 股监控**：LOF/QDII/商品与指数基金套利扫描，结合溢价、申购状态、限额、成本和账户容量筛选。
2. **美股持仓**：搜索并添加股票、设置目标价、监控价格和相关新闻，新闻可折叠并保留原文链接。
3. **前沿资讯**：每天汇总科技、AI、政治资讯。
4. **市场情绪**：综合市场指标，并展示 BTC、ETH、SOL 行情。
5. **AI 投研**：资产搜索、研究档案、任务进度和个人笔记；真正调用模型时需要单独的 API Key。

套利账户参数按个人实际情况配置为：8 个投资人账户、56 条通道、每个投资人可调用资金 1 万元、总资金 8 万元、申购费率按一折估算。系统只做筛选与风险提示，不代替基金公告和券商页面确认。

## 2. 技术栈

### 小程序前端

- 微信原生小程序：WXML、WXSS、TypeScript/JavaScript。
- 页面代码位于 `miniprogram/pages/`。
- 所有请求统一经过 `miniprogram/utils/api.ts`，页面不直接拼接服务器地址。

### 后端

- Python + FastAPI。
- `main.py` 提供统一 REST API。
- `arbitrage_engine.py`：基金套利计算。
- `market_sentiment.py`：市场情绪和加密资产。
- `news_engine.py`：资讯聚合。
- `research_engine.py`：AI 投研、研究任务和笔记。
- SQLite 数据保存在 `data/`，数据库文件被 `.gitignore` 排除。

### 服务器

- 腾讯云广州 Ubuntu 轻量服务器。
- 2 核 CPU、2GB 内存、50GB 系统盘。
- Uvicorn 仅监听 `127.0.0.1:8000`。
- `systemd` 服务名：`miniapp-api`，负责开机自启和异常重启。
- Nginx 作为入口和反向代理。

### 版本管理

- 本地 Git 仓库分支：`main`。
- GitHub：`penp112215-dotcom/market-radar-miniapp`。
- VPS 使用只读 Deploy Key，通过 `ssh.github.com:443` 拉取代码，避免使用个人密码或 PAT。

## 3. 当前最终架构

```text
微信开发者工具 / 手机预览 / 体验版
                 │
                 │ wx.cloud.callContainer
                 ▼
CloudBase 环境 cloud1-d7gdt868jed18e21e
                 │
                 │ AnyService: miniappvps
                 ▼
VPS 1.14.200.232:8080
                 │
                 │ Nginx 反向代理
                 ▼
FastAPI 127.0.0.1:8000
                 │
                 ├─ 外部公开数据源
                 └─ /opt/miniapp/data/*.db
```

这条链路不再依赖 `api.penp15.cn`，也不需要在微信后台配置该域名为 request 合法域名。AnyService 配置如下：

- 环境 ID：`cloud1-d7gdt868jed18e21e`
- 服务标识：`miniappvps`
- 源站类型：通过公网访问源站
- 源站协议：HTTP
- 源站地址：`1.14.200.232:8080`

## 4. 为什么架构发生了变化

### 第一阶段：本机开发

最初由微信开发者工具请求 `http://127.0.0.1:8000`。优点是修改快；缺点是电脑关机后服务停止，手机也不能访问电脑的 localhost。

### 第二阶段：VPS + 域名 + HTTPS

后端迁移到 VPS，安装 Python 环境、systemd、Nginx 和 Let's Encrypt 证书，并配置 `api.penp15.cn`。VPS 内部和 HTTPS 证书均正常。

手机仍无数据的根因不是代码，而是腾讯云对未备案大陆域名的访问拦截。外网检查得到 DNSPod 的备案阻断页面。

### 第三阶段：备案合规评估

个人备案被驳回，主要有三点：

1. 备注包含市场行情、基金套利等金融关键词，需要相应材料或资质。
2. 当前功能不符合个人网站备案内容范围。
3. 域名注册/实名认证信息当时尚未完全同步。

不能只修改备注来隐藏真实功能。因此项目明确调整为个人自用，不提交公开金融小程序审核。

### 第四阶段：CloudBase AnyService

CloudBase AnyService 可以通过服务器 IP 接入现有 VPS，小程序使用私有 SDK 调用，不依赖自有域名备案。最终保留原 VPS 和 FastAPI，只替换小程序到服务器之间的传输入口。

## 5. 五个业务模块如何实现

### 5.1 基金套利

套利不是简单比较场内价格与昨日净值，而是依次判断：

1. 场内价格是否显著高于可用净值/估值。
2. 基金是否开放申购、是否限额、限额口径是否已核实。
3. QDII 净值日期、汇率、海外底层资产时差是否造成估值误差。
4. 申购费、卖出费、交易佣金、滑点和到账时间风险。
5. 8 个投资人账户合计可申购容量。
6. 扣除成本和安全垫后是否仍有净空间。

界面只展示扣除成本和安全垫后的结果，并区分“可执行、待核实、观察、暂停”等状态。

### 5.2 美股持仓

用户自选股票和目标价保存在小程序本地；后端按 symbols 参数批量查询。

行情数据目前采用多源降级：

```text
Yahoo → 腾讯财经 → 东方财富 → unavailable
```

Yahoo 在中国大陆 VPS 上经常超时或被云 IP 风控，因此新增腾讯财经作为大陆快速备用源。新闻仍优先 Yahoo，再尝试中文搜索备用；新闻源失败不影响价格返回。

### 5.3 前沿资讯

最初同时抓取 13 个国内外 RSS。大陆 VPS 访问 Google News、OpenAI、DeepMind、BBC 等跨境源时，冷启动约 19 秒，CloudBase 网关报错 `102002`。

修复后首屏优先并发抓取大陆快速源，冷启动实测约 1 秒，仍能返回科技、AI、政治三个频道共约 31 条；结果缓存 5 分钟。

### 5.4 市场情绪

把多个客观指标归一化后组合为情绪等级，同时单独展示 BTC、ETH、SOL。任何单一数据源失败时都返回结构稳定的结果，避免页面白屏。

### 5.5 AI 投研

当前已经具备研究工作台、资产搜索、研究档案、异步任务和笔记数据库。ChatGPT Plus 不包含 OpenAI API 额度；真正启用 AI 分析时，需要在 VPS 的 `/etc/miniapp-api.env` 配置独立 API Key，密钥不能进入小程序代码或 GitHub。

## 6. 遇到的典型故障与排查思路

### WXML 编译错误

- `wx:else` 必须紧跟相应 `wx:if`，中间不能有不匹配节点。
- WXML 不适合复杂表达式和动态 CSS 运算；应在 TypeScript 中预计算样式字符串。

### 模拟器空白但没有明显错误

先看 Console，而不是只看 WXML。判断请求是否发出、状态码多少、错误发生在前端、网关、Nginx、FastAPI还是外部数据源。

### 502 Bad Gateway

说明 Nginx 能收到请求，但 Uvicorn 没有正常响应。检查：

```bash
sudo systemctl status miniapp-api --no-pager
sudo journalctl -u miniapp-api -n 100 --no-pager
curl http://127.0.0.1:8000/health
```

### 手机全部无数据、电脑本地正常

这是环境差异问题。电脑开发工具可以关闭合法域名校验，手机体验版不能。本项目后来确认是大陆未备案域名被腾讯云拦截，而非 Wi-Fi/5G 问题。

### CloudBase `INVALID_HOST`

代码最初使用服务标识 `miniapp_vps`，控制台实际创建的是 `miniappvps`。服务标识必须完全一致，而且源站连接信息只能填 `1.14.200.232:8080`，不能带 `http://` 或 `/health`。

### GitHub 403

GitHub 不再接受账号密码直接进行 Git HTTPS 操作。最终使用仓库只读 Deploy Key，并配置 SSH 443 端口解决 VPS 访问问题。曾经截图暴露过的 PAT 必须撤销。

### 依赖下载很慢

大陆 VPS 访问 PyPI 可能很慢，可临时使用可信的国内镜像；安装完成后由虚拟环境锁定依赖。

## 7. 日常开发与发布流程

### 本地修改后

```powershell
npx.cmd tsc
python -m unittest discover -v
git status
git add <明确的文件>
git commit -m "清晰的修改说明"
git push origin main
```

TypeScript 修改后必须同步生成 JavaScript，否则开发者工具可能继续执行旧文件。

### VPS 更新后端

```bash
cd /opt/miniapp
git pull --ff-only origin main
/opt/miniapp/.venv/bin/pip install -r requirements.txt
sudo systemctl restart miniapp-api
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8080/health
```

只修改小程序页面时，VPS 不一定要重启；修改 Python 后端时必须拉取并重启。

### 更新体验版

1. 微信开发者工具清缓存并重新编译。
2. 手机预览逐页验证。
3. 点击“上传”，填写版本号和更新说明。
4. 微信公众平台将开发版本设为体验版。
5. 只添加自己的体验成员，不提交公开审核。

## 8. 数据与密钥安全

- `.env`、API Key、GitHub 私钥、数据库不得进入 Git。
- GitHub Deploy Key 只给只读权限。
- `/etc/miniapp-api.env` 权限应为 `600`。
- Uvicorn 的 8000 端口不向公网开放。
- SQLite 更新前先备份 `data/`。
- 当前 8080 是 AnyService 源站入口，Nginx 已校验小程序 AppID 和服务标识；下一步仍建议增加 OpenID 白名单，仅允许指定体验成员。

备份数据库：

```bash
sudo tar -czf /root/miniapp-data-$(date +%F).tar.gz /opt/miniapp/data
```

## 9. 当前完成状态

- 五个页面均已完成基本 UI 和 API 接入。
- FastAPI 已在 VPS 通过 systemd 24 小时运行。
- GitHub 与 VPS 已建立更新链路。
- CloudBase AnyService 已打通开发工具和手机访问。
- 美股行情具备 Yahoo、腾讯财经、东方财富降级。
- 前沿资讯超时已修复。
- 当前自动测试共 27 项，全部通过。
- 稳定版本以 `main` 分支最新通过自动测试的提交为准。

## 10. 下一阶段建议

按优先级排序：

1. 增加 OpenID 白名单和接口访问审计，确保只有指定用户可用。
2. 增加数据库定时备份和服务健康告警。
3. 为美股新闻接入有正式 API Key 的稳定提供商。
4. 为基金公告、申购限额增加更可靠的官方核验来源和数据时间戳。
5. 配置 AI API 后再启用真正的模型分析，并设置每日成本上限。

## 11. 0→1 最重要的学习结论

1. **先定义数据结构，再做界面。** 页面稳定取决于 API 返回结构稳定。
2. **开发环境和真机环境不同。** localhost、合法域名、备案和网络路线必须分别验证。
3. **真实项目必须有降级。** 外部免费接口随时会慢、被限流或改变格式。
4. **日志比猜测重要。** 通过状态码和分层健康检查定位故障。
5. **密钥永远放服务端。** 前端和 GitHub 不能出现 API Key、PAT 和 SSH 私钥。
6. **部署不是最后一步。** systemd、Nginx、监控、备份、更新和回滚都属于产品。
7. **合规是架构约束。** 备案和平台类目不匹配时，应调整产品发布方式，而不是隐藏真实功能。
8. **小步提交。** 每完成一个可验证功能就测试并提交 Git，出了问题才能快速定位和回退。

## 12. 后续任务上下文摘要

项目位于 `D:\Documents\小程序`，当前分支为 `main`。后端通过 systemd 运行 FastAPI，Uvicorn 仅监听本机端口，再由 Nginx 和 CloudBase AnyService 转发。五个模块为基金价差、美股持仓、前沿资讯、市场情绪和 AI 投研；行情与新闻均包含多源降级。当前 27 项自动测试全部通过。公开复用时应替换文档和配置中的个人环境标识、服务器地址与域名。下一优先任务是访问控制、备份告警、数据来源健康检查和稳定美股新闻 API。
