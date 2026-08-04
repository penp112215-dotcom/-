# CloudBase AnyService 接入说明

本项目默认在微信开发者工具、预览、体验版和真机中统一使用 CloudBase AnyService 私有链路访问现有 VPS，不依赖自有域名。需要调试本机 Python 服务时，可把 `miniprogram/utils/config.ts` 中的 `USE_LOCAL_API_IN_DEVTOOLS` 临时改为 `true`。

## 1. 创建并关联云开发环境

1. 在微信开发者工具中打开当前小程序。
2. 点击“云开发”，开通环境并记录环境 ID。
3. 确认该环境与当前小程序 AppID `wx7fb5a8c99417a78b` 关联。
4. 将环境 ID 填入 `miniprogram/utils/config.ts` 的 `CLOUDBASE_ENV_ID`。

## 2. 配置 VPS 源站入口

把仓库更新到 VPS 后执行：

```bash
sudo cp /opt/miniapp/deploy/nginx-anyservice.conf /etc/nginx/sites-available/miniapp-anyservice
sudo ln -s /etc/nginx/sites-available/miniapp-anyservice /etc/nginx/sites-enabled/miniapp-anyservice
sudo nginx -t
sudo systemctl reload nginx
```

在腾讯云轻量服务器防火墙中放行 TCP 端口 `8080`，然后验证：

```bash
curl http://1.14.200.232:8080/health
```

应返回 `{"status":"ok"}`。

## 3. 创建 AnyService 服务

在腾讯云开发 CloudBase 控制台进入“AnyService”，选择“新建服务接入”：

- 服务名称：`小程序 VPS 后端`
- 服务标识：`miniapp_vps`
- 源站类型：`通过公网访问源站`
- 源站协议：`HTTP`
- 源站连接信息：`1.14.200.232:8080`

AnyService 服务所在环境必须与小程序 `wx.cloud.init` 使用的环境 ID 一致。

## 4. 真机验证

重新编译并上传体验版。真机请求会携带：

- `X-WX-SERVICE: tcbanyservice`
- `X-AnyService-Name: miniapp_vps`

不需要在微信公众平台添加 `api.penp15.cn` 为 request 合法域名。

## 5. 更新规则

更改 `config.ts` 后运行 TypeScript 编译，确保对应的 `config.js` 同步更新：

```powershell
npx.cmd tsc
```
