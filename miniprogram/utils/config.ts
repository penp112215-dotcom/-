/** API 与 CloudBase 的唯一配置点。 */
const LOCAL_API_BASE_URL = 'http://127.0.0.1:8000'

/**
 * 在「微信开发者工具 → 云开发」创建环境后，把环境 ID 填到这里。
 * 示例：cloud1-1gxxxxxxxxxxxxxx
 */
export const CLOUDBASE_ENV_ID = 'cloud1-d7gdt868jed18e21e'

/** CloudBase AnyService 控制台中的“服务标识”。 */
export const ANYSERVICE_NAME = 'miniapp_vps'

/** 设为 true 时开发者工具才连接本机；默认所有环境都使用 CloudBase。 */
export const USE_LOCAL_API_IN_DEVTOOLS = false

export function isDeveloperTools(): boolean {
  try {
    return wx.getSystemInfoSync().platform === 'devtools'
  } catch (error) {
    return false
  }
}

export function shouldUseCloudBase(): boolean {
  return !isDeveloperTools() || !USE_LOCAL_API_IN_DEVTOOLS
}

// 仅在显式开启本机调试开关时使用。
export const API_BASE_URL = LOCAL_API_BASE_URL
