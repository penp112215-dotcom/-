"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.API_BASE_URL = exports.USE_LOCAL_API_IN_DEVTOOLS = exports.ANYSERVICE_NAME = exports.CLOUDBASE_ENV_ID = void 0;
exports.isDeveloperTools = isDeveloperTools;
exports.shouldUseCloudBase = shouldUseCloudBase;
/** API 与 CloudBase 的唯一配置点。 */
const LOCAL_API_BASE_URL = 'http://127.0.0.1:8000';
/**
 * 在「微信开发者工具 → 云开发」创建环境后，把环境 ID 填到这里。
 * 示例：cloud1-1gxxxxxxxxxxxxxx
 */
exports.CLOUDBASE_ENV_ID = 'cloud1-d7gdt868jed18e21e';
/** CloudBase AnyService 控制台中的“服务标识”。 */
exports.ANYSERVICE_NAME = 'miniapp_vps';
/** 设为 true 时开发者工具才连接本机；默认所有环境都使用 CloudBase。 */
exports.USE_LOCAL_API_IN_DEVTOOLS = false;
function isDeveloperTools() {
    try {
        return wx.getSystemInfoSync().platform === 'devtools';
    }
    catch (error) {
        return false;
    }
}
function shouldUseCloudBase() {
    return !isDeveloperTools() || !exports.USE_LOCAL_API_IN_DEVTOOLS;
}
// 仅在显式开启本机调试开关时使用。
exports.API_BASE_URL = LOCAL_API_BASE_URL;
