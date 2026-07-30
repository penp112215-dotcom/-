"use strict";
// api.ts
// 本地数据引擎请求封装。后端服务地址：http://127.0.0.1:8000
// 注意：开发期需在微信开发者工具「详情 → 本地设置」勾选「不校验合法域名」。
Object.defineProperty(exports, "__esModule", { value: true });
exports.api = exports.API_PATH = void 0;
exports.request = request;
const config_1 = require("./config");
const BASE_URL = config_1.API_BASE_URL;
/** 三个接口路径 — 各页面必须引用对应常量，禁止混用 */
exports.API_PATH = {
    ARBITRAGE: '/api/arbitrage',
    PORTFOLIO: '/api/portfolio',
    STOCK_SEARCH: '/api/stocks/search',
    NEWS: '/api/news',
    MARKET: '/api/market',
    BRIEFING: '/api/briefing',
};
function parseResponseBody(data) {
    if (data == null || data === '') {
        return {};
    }
    if (typeof data === 'string') {
        try {
            return JSON.parse(data);
        }
        catch (e) {
            console.warn('API 响应非 JSON 字符串:', data);
            return {};
        }
    }
    return data;
}
/** 通用请求，resolve 的即为后端 JSON 根对象 */
function request(path, options = {}) {
    const url = path.startsWith('http') ? path : BASE_URL + path;
    return new Promise((resolve, reject) => {
        console.log('[API请求]', url);
        wx.request({
            url,
            method: options.method || 'GET',
            data: options.data,
            header: { 'content-type': 'application/json', ...(options.header || {}) },
            timeout: options.timeout || 120000,
            dataType: 'json',
            success: (res) => {
                console.log('[API返回]', url, res.data, 'status:', res.statusCode);
                const statusCode = res.statusCode || 0;
                if (statusCode >= 400) {
                    reject({ statusCode, data: res.data, url });
                    return;
                }
                const body = parseResponseBody(res.data);
                resolve(body);
            },
            fail: (err) => {
                console.error('[API失败]', url, err);
                reject(err);
            },
        });
    });
}
/** 便捷方法（路径与 API_PATH 一一对应，不可互换） */
exports.api = {
    arbitrage: () => request(exports.API_PATH.ARBITRAGE, { timeout: 90000 }),
    portfolio: () => request(exports.API_PATH.PORTFOLIO, { timeout: 180000 }),
    news: () => request(exports.API_PATH.NEWS),
};
