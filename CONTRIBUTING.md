# 贡献指南

感谢你愿意帮助改进 Market Radar Mini Program。项目优先接受能够提高数据可追溯性、稳定性、测试覆盖和部署可复现性的贡献。

## 开始之前

1. 先搜索现有 Issue，确认问题尚未被记录。
2. 较大的功能请先创建 Issue，说明目标、数据来源、风险和预期界面。
3. 不要提交真实 API Key、Cookie、账号信息、数据库、服务器地址或个人投资记录。
4. 不要加入自动下单、绕过平台限制、规避访问控制或宣称确定收益的功能。

## 本地开发

```bash
python -m venv .venv
python -m pip install -r requirements.txt
npm install
```

启动后端：

```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

本机微信开发者工具调试时，可临时把 `miniprogram/utils/config.ts` 中的 `USE_LOCAL_API_IN_DEVTOOLS` 设为 `true`。提交前不要把个人 CloudBase 环境和服务地址写入通用配置。

## 提交前检查

```bash
npm run typecheck
npm test
```

如修改了 TypeScript 页面，再执行：

```bash
npm run build
```

确认生成的 JavaScript 与 TypeScript 一并提交。

## 数据源贡献要求

新增或修改行情、净值、限额、新闻数据源时，请在 PR 中说明：

- 官方页面或 API 文档链接；
- 数据更新时间、时区和延迟；
- 免费额度、频率限制和使用条款；
- 中国大陆 VPS 与真机环境的可达性；
- 超时、限流、字段缺失时的降级行为；
- 页面向用户显示的来源标签；
- 对应的单元测试或可复现验证步骤。

基金套利相关计算还必须注明净值日期、申购状态、限额口径、费率、滑点和安全垫。缺少关键输入时，结果应标记为“待核实”或“不可执行”，不能用模拟值冒充实时结果。

## Pull Request 约定

- 一个 PR 尽量只解决一个问题。
- 标题清楚描述结果，例如 `fix: preserve source link when translation fails`。
- 在描述中列出改动、验证结果、风险和截图。
- 保持接口返回结构兼容；若必须变更字段，请同步修改前端、测试和文档。
- 尊重 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 中的第三方版权和许可证。

提交贡献即表示你有权提交相关代码，并同意该贡献按本仓库的 MIT License 发布。

