// api.ts
// 本地数据引擎请求封装。后端服务地址：http://127.0.0.1:8000
// 注意：开发期需在微信开发者工具「详情 → 本地设置」勾选「不校验合法域名」。

import { API_BASE_URL } from './config'

const BASE_URL = API_BASE_URL

/** 三个接口路径 — 各页面必须引用对应常量，禁止混用 */
export const API_PATH = {
  ARBITRAGE: '/api/arbitrage',
  PORTFOLIO: '/api/portfolio',
  STOCK_SEARCH: '/api/stocks/search',
  NEWS: '/api/news',
  MARKET: '/api/market',
  BRIEFING: '/api/briefing',
  RESEARCH_OVERVIEW: '/api/research/overview',
  RESEARCH_SEARCH: '/api/research/search',
  RESEARCH_ASSET: '/api/research/asset',
  RESEARCH_NOTES: '/api/research/notes',
  RESEARCH_TASKS: '/api/research/tasks',
} as const

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE'

interface RequestOptions {
  method?: Method
  data?: Record<string, any> | string
  header?: Record<string, string>
  timeout?: number
}

function parseResponseBody(data: any): any {
  if (data == null || data === '') {
    return {}
  }
  if (typeof data === 'string') {
    try {
      return JSON.parse(data)
    } catch (e) {
      console.warn('API 响应非 JSON 字符串:', data)
      return {}
    }
  }
  return data
}

/** 通用请求，resolve 的即为后端 JSON 根对象 */
export function request<T = Record<string, any>>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const url = path.startsWith('http') ? path : BASE_URL + path
  return new Promise<T>((resolve, reject) => {
    console.log('[API请求]', url)
    wx.request({
      url,
      method: options.method || 'GET',
      data: options.data,
      header: { 'content-type': 'application/json', ...(options.header || {}) },
      timeout: options.timeout || 120000,
      dataType: 'json',
      success: (res) => {
        console.log('[API返回]', url, res.data, 'status:', res.statusCode)
        const statusCode = res.statusCode || 0
        if (statusCode >= 400) {
          reject({ statusCode, data: res.data, url })
          return
        }
        const body = parseResponseBody(res.data) as T
        resolve(body)
      },
      fail: (err) => {
        console.error('[API失败]', url, err)
        reject(err)
      },
    })
  })
}

/** 便捷方法（路径与 API_PATH 一一对应，不可互换） */
export const api = {
  arbitrage: () => request(API_PATH.ARBITRAGE, { timeout: 90000 }),
  portfolio: () => request(API_PATH.PORTFOLIO, { timeout: 180000 }),
  news: () => request(API_PATH.NEWS),
}
