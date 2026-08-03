/**
 * API 地址唯一配置点。
 * 本地开发保持 localhost；部署 VPS 后只需改为已配置的 HTTPS 域名。
 */
const LOCAL_API_BASE_URL = 'http://127.0.0.1:8000'

// 部署 VPS 后只替换这一项；体验版和正式版都会自动使用 HTTPS 地址。
const PRODUCTION_API_BASE_URL = 'https://api.example.com'

function currentEnvironment(): string {
  try {
    return wx.getAccountInfoSync().miniProgram.envVersion || 'develop'
  } catch (error) {
    return 'develop'
  }
}

export const API_BASE_URL = currentEnvironment() === 'develop'
  ? LOCAL_API_BASE_URL
  : PRODUCTION_API_BASE_URL
