// api.ts
// 开发者工具走本机 HTTP；预览、体验版和真机走 CloudBase AnyService 私有链路。

import {
  ANYSERVICE_NAME,
  API_BASE_URL,
  CLOUDBASE_ENV_ID,
  shouldUseCloudBase,
} from './config'

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
  RESEARCH_DOSSIER: '/api/research/dossier',
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

function requestThroughCloudBase<T>(
  path: string,
  options: RequestOptions
): Promise<T> {
  if (!CLOUDBASE_ENV_ID) {
    return Promise.reject({
      errMsg: 'CloudBase 环境 ID 尚未配置',
      path,
    })
  }
  const cloud = wx.cloud as any
  if (!cloud || !cloud.callContainer) {
    return Promise.reject({
      errMsg: '当前微信基础库不支持 CloudBase',
      path,
    })
  }

  console.log('[CloudBase请求]', path)
  return cloud.callContainer({
    config: { env: CLOUDBASE_ENV_ID },
    path,
    method: options.method || 'GET',
    data: options.data,
    header: {
      'X-WX-SERVICE': 'tcbanyservice',
      'X-AnyService-Name': ANYSERVICE_NAME,
      'content-type': 'application/json',
      ...(options.header || {}),
    },
    timeout: options.timeout || 120000,
  } as any).then((res: any) => {
    const statusCode = Number(res.statusCode || 0)
    console.log('[CloudBase返回]', path, res.data, 'status:', statusCode)
    if (statusCode >= 400) {
      return Promise.reject({ statusCode, data: res.data, path })
    }
    return parseResponseBody(res.data) as T
  }).catch((error: any) => {
    console.error('[CloudBase失败]', path, error)
    return Promise.reject(error)
  })
}

function requestLocally<T>(
  path: string,
  options: RequestOptions
): Promise<T> {
  const url = path.startsWith('http') ? path : BASE_URL + path
  return new Promise<T>((resolve, reject) => {
    console.log('[本地API请求]', url)
    wx.request({
      url,
      method: options.method || 'GET',
      data: options.data,
      header: { 'content-type': 'application/json', ...(options.header || {}) },
      timeout: options.timeout || 120000,
      dataType: 'json',
      success: (res) => {
        const statusCode = res.statusCode || 0
        console.log('[本地API返回]', url, res.data, 'status:', statusCode)
        if (statusCode >= 400) {
          reject({ statusCode, data: res.data, url })
          return
        }
        resolve(parseResponseBody(res.data) as T)
      },
      fail: (error) => {
        console.error('[本地API失败]', url, error)
        reject(error)
      },
    })
  })
}

/** 通用请求，resolve 的即为后端 JSON 根对象 */
export function request<T = Record<string, any>>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  return shouldUseCloudBase()
    ? requestThroughCloudBase<T>(path, options)
    : requestLocally<T>(path, options)
}

/** 便捷方法（路径与 API_PATH 一一对应，不可互换） */
export const api = {
  arbitrage: () => request(API_PATH.ARBITRAGE, { timeout: 90000 }),
  portfolio: () => request(API_PATH.PORTFOLIO, { timeout: 180000 }),
  news: () => request(API_PATH.NEWS),
}
