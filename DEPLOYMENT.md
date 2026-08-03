# 微信小程序 VPS 部署与正式发布

适用环境：腾讯云广州 Ubuntu、2 核 CPU、2GB 内存、50GB 系统盘。后端使用
`systemd + Python venv + Uvicorn + Nginx + HTTPS`，不使用 Docker，以节省内存。

## 0. 上线前必须准备

1. 一个自己可管理的域名，例如 `example.com`。
2. 一个 API 子域名，例如 `api.example.com`，A 记录指向 `1.14.200.232`。
3. 确认域名满足腾讯云大陆服务器和微信小程序的备案/接入要求。
4. 微信公众平台中当前小程序的管理员权限。
5. VPS SSH 登录权限，推荐密钥登录，不要通过聊天发送密码。

正式环境不能使用 `127.0.0.1` 或裸 IP。微信小程序的 `wx.request` 应访问已配置的
HTTPS request 合法域名。

## 1. 腾讯云安全组

入站仅开放：

- TCP 22：SSH；初期最好仅允许自己的公网 IP。
- TCP 80：申请证书和 HTTP 跳转。
- TCP 443：小程序 HTTPS API。

不要向公网开放 8000；Uvicorn 只监听 `127.0.0.1:8000`，由 Nginx 转发。

## 2. 首次登录并安装系统依赖

```bash
ssh root@1.14.200.232
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx
sudo timedatectl set-timezone Asia/Shanghai
sudo adduser --system --group --home /opt/miniapp miniapp
```

## 3. 下载项目

公开仓库：

```bash
sudo git clone https://github.com/penp112215-dotcom/-.git /opt/miniapp
```

如果仓库是私有仓库，请在 VPS 配置只读 Deploy Key，再用 SSH 地址克隆。不要把 GitHub
Token 写进脚本或仓库。

```bash
sudo chown -R miniapp:miniapp /opt/miniapp
sudo -u miniapp python3 -m venv /opt/miniapp/.venv
sudo -u miniapp /opt/miniapp/.venv/bin/pip install --upgrade pip wheel
sudo -u miniapp /opt/miniapp/.venv/bin/pip install -r /opt/miniapp/requirements.txt
sudo -u miniapp mkdir -p /opt/miniapp/data
```

## 4. 后端环境变量

创建仅 root 可读的环境文件：

```bash
sudo nano /etc/miniapp-api.env
sudo chmod 600 /etc/miniapp-api.env
```

未购买 AI API 时保持前三项为空，其他行情、套利、资讯功能仍可运行：

```ini
AI_PROVIDER=OpenAI
AI_BASE_URL=
AI_API_KEY=
AI_MODEL=
AI_TIMEOUT=120
```

将来配置 API Key 时只修改 VPS 的 `/etc/miniapp-api.env`，绝不能写入小程序源码或 Git。

## 5. 安装 systemd 常驻服务

```bash
sudo cp /opt/miniapp/deploy/miniapp-api.service /etc/systemd/system/miniapp-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now miniapp-api
sudo systemctl status miniapp-api --no-pager
curl http://127.0.0.1:8000/health
```

应看到 `{"status":"ok"}`。查看日志：

```bash
sudo journalctl -u miniapp-api -n 100 --no-pager
sudo journalctl -u miniapp-api -f
```

## 6. 配置 Nginx

先把模板中的 `api.example.com` 全部替换为真实 API 域名：

```bash
sudo cp /opt/miniapp/deploy/nginx-miniapp.conf /etc/nginx/conf.d/miniapp-api.conf
sudo nano /etc/nginx/conf.d/miniapp-api.conf
sudo nginx -t
sudo systemctl reload nginx
```

确认 DNS 已生效：

```bash
getent hosts api.example.com
curl http://api.example.com/health
```

## 7. 申请 HTTPS 证书

```bash
sudo certbot --nginx -d api.example.com --redirect
sudo certbot renew --dry-run
curl https://api.example.com/health
```

HTTPS 健康检查必须返回 `{"status":"ok"}`，浏览器不得出现证书警告。

## 8. 切换小程序正式 API 地址

在本地编辑：

```text
miniprogram/utils/config.ts
```

把：

```ts
const PRODUCTION_API_BASE_URL = 'https://api.example.com'
```

替换为真实域名，然后执行：

```powershell
npx.cmd tsc
```

微信开发者工具里的开发版仍使用 `http://127.0.0.1:8000`；体验版和正式版会自动切换到 HTTPS 地址。

## 9. 微信公众平台配置

1. 登录 `https://mp.weixin.qq.com/`。
2. 进入开发管理/开发设置中的服务器域名。
3. 在 `request 合法域名` 添加 `https://api.example.com`，不要带路径和端口。
4. 在微信开发者工具切换到“不忽略合法域名校验”的模式重新测试。
5. 使用真机预览逐页验证五个板块。

推荐逐项检查：

- 基金套利能返回数据、筛选和历史记录。
- 美股自选、目标价、中文新闻与来源链接正常。
- 前沿资讯的科技、AI、政治频道均有内容。
- 市场情绪和 BTC/ETH/SOL 能刷新。
- AI 投研在未配置 API 时提示待配置，而不是白屏。

## 10. 上传、审核和发布

1. 更新版本号，例如 `1.0.0`，填写清晰更新说明。
2. 微信开发者工具点击“上传”。
3. 微信公众平台进入版本管理，将开发版本设为体验版并真机验收。
4. 补齐服务类目、用户隐私保护指引、数据来源和投资风险提示。
5. 提交审核；如审核要求测试路径或账号，提供能覆盖全部页面的测试说明。
6. 审核通过后在版本管理中点击发布。

本项目涉及行情、基金套利和资讯，页面必须持续保留“仅供研究、不构成投资建议”说明；
不要宣传保本、稳赚或确定性收益。

## 11. 后续更新

每次发布新后端：

```bash
cd /opt/miniapp
sudo -u miniapp git pull --ff-only origin main
sudo -u miniapp /opt/miniapp/.venv/bin/pip install -r requirements.txt
sudo systemctl restart miniapp-api
curl http://127.0.0.1:8000/health
curl https://api.example.com/health
```

数据库位于 `/opt/miniapp/data/`，更新代码时不要删除。备份示例：

```bash
sudo tar -czf /root/miniapp-data-$(date +%F).tar.gz /opt/miniapp/data
```

## 12. 常见故障

- `502 Bad Gateway`：检查 `systemctl status miniapp-api` 和 8000 端口。
- 小程序提示 URL 不合法：检查微信后台 request 合法域名和 HTTPS 域名是否完全一致。
- HTTPS 失败：检查 DNS、安全组 80/443、`nginx -t` 和 Certbot 日志。
- 资讯部分来源为空：大陆网络可能无法访问境外 RSS；系统会保留国内备用源。
- GitHub 无法访问：可先从本地上传发布包到 `/opt/miniapp`，或配置可用的代码镜像。
- 内存不足：保持 Uvicorn `--workers 1`，不要在 2GB VPS 上同时运行多个重型抓取容器。
