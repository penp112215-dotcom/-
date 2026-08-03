"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.API_BASE_URL = void 0;
/**
 * API 地址唯一配置点。
 * 本地开发保持 localhost；部署 VPS 后只需改为已配置的 HTTPS 域名。
 */
const LOCAL_API_BASE_URL = 'http://127.0.0.1:8000';
// 部署 VPS 后只替换这一项；体验版和正式版都会自动使用 HTTPS 地址。
const PRODUCTION_API_BASE_URL = 'https://api.penp15.cn';
function isDeveloperTools() {
    try {
        return wx.getSystemInfoSync().platform === 'devtools';
    }
    catch (error) {
        return false;
    }
}
// 开发者工具模拟器连接本机；预览、体验版和正式版真机全部连接 VPS。
exports.API_BASE_URL = isDeveloperTools()
    ? LOCAL_API_BASE_URL
    : PRODUCTION_API_BASE_URL;
