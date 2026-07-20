import { request, API_PATH } from '../../utils/api'

interface AssetDisplay {
  symbol: string
  name: string
  priceText: string
  changeText: string
  changeCls: string
  sourceText: string
}

function numberOf(value: unknown): number | null {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function toAsset(raw: Record<string, unknown>): AssetDisplay {
  const change = numberOf(raw.change_pct_24h) || 0
  const rise = change >= 0
  const price = numberOf(raw.price)
  return {
    symbol: String(raw.symbol || '--'),
    name: String(raw.name || ''),
    priceText: price == null ? '$--' : '$' + price.toLocaleString('en-US', { maximumFractionDigits: 2 }),
    changeText: (rise ? '+' : '') + change.toFixed(2) + '%',
    changeCls: rise ? 'rise' : 'fall',
    sourceText: raw.source === 'live' ? '实时' : '演示/缓存',
  }
}

Page({
  data: {
    assets: [] as AssetDisplay[],
    value: '--',
    classification: '--',
    riskLevel: '--',
    updatedAt: '--',
    loading: true,
    isLive: false,
  },

  onLoad() { this.fetch() },
  onPullDownRefresh() { this.fetch(() => wx.stopPullDownRefresh()) },

  fetch(done?: () => void) {
    this.setData({ loading: true })
    request<any>(API_PATH.MARKET, { timeout: 15000 })
      .then((res) => {
        const fear = res.fear_greed || {}
        this.setData({
          assets: Array.isArray(res.crypto_assets) ? res.crypto_assets.map(toAsset) : [],
          value: fear.value == null ? '--' : String(fear.value),
          classification: fear.classification || '--',
          riskLevel: res.risk_level || '--',
          updatedAt: res.updated_at || '--',
          isLive: fear.source === 'live',
          loading: false,
        })
      })
      .catch(() => this.setData({ loading: false }))
      .finally(() => done && done())
  },
})
