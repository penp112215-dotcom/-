import { request, API_PATH } from '../../utils/api'

interface AccountSummary {
  investors: number
  on_exchange_per_investor: number
  off_exchange_per_investor: number
  cash_per_investor: number
  total_channels: number
  total_cash: number
}

interface ScanSummary {
  market_total: number
  analyzed: number
  opportunities: number
  need_verification: number
  watching: number
  elapsed_ms: number
}

interface ArbitrageItem {
  code: string
  name: string
  market: string
  fund_type: string
  price: number
  exit_price: number
  pricing_basis: string
  amount: number
  reference_nav: number
  nav_label: string
  nav_date: string
  gross_premium_pct: number
  subscription_fee_pct: number
  sell_fee_pct: number
  slippage_pct: number
  safety_buffer_pct: number
  net_edge_pct: number
  subscription_status: string
  per_investor_limit: number
  published_per_investor_limit: number
  liquidity_capacity: number
  total_capacity: number
  eligible_channels: number
  limit_scope: string
  limit_confirmed: boolean
  expected_profit: number
  data_confidence: string
  signal: string
  signal_text: string
}

interface DisplayItem extends ArbitrageItem {
  cardCls: string
  signalCls: string
  signalText: string
  priceText: string
  navText: string
  grossText: string
  netText: string
  perInvestorText: string
  capacityText: string
  profitText: string
  amountText: string
  confidenceText: string
}

interface ArbitrageResponse {
  status?: string
  message?: string
  updated_at?: string
  account?: AccountSummary
  summary?: ScanSummary
  items?: ArbitrageItem[]
}

const EMPTY_ACCOUNT: AccountSummary = {
  investors: 8,
  on_exchange_per_investor: 6,
  off_exchange_per_investor: 1,
  cash_per_investor: 10000,
  total_channels: 56,
  total_cash: 80000,
}

const EMPTY_SUMMARY: ScanSummary = {
  market_total: 0,
  analyzed: 0,
  opportunities: 0,
  need_verification: 0,
  watching: 0,
  elapsed_ms: 0,
}

function money(value: number): string {
  if (!Number.isFinite(value)) return '¥--'
  return '¥' + Math.round(value).toLocaleString('zh-CN')
}

function signalClass(signal: string): string {
  if (signal === 'opportunity') return 'signal signal-ready'
  if (signal === 'verify') return 'signal signal-verify'
  if (signal === 'watch') return 'signal signal-watch'
  if (signal === 'closed') return 'signal signal-closed'
  return 'signal signal-none'
}

function toDisplay(item: ArbitrageItem): DisplayItem {
  const positive = Number(item.net_edge_pct || 0) > 0
  return {
    ...item,
    cardCls: positive ? 'fund-card fund-card-positive' : 'fund-card',
    signalCls: signalClass(item.signal),
    signalText: item.signal_text || '观察',
    priceText: Number(item.exit_price || item.price || 0).toFixed(4),
    navText: Number(item.reference_nav || 0).toFixed(4),
    grossText: Number(item.gross_premium_pct || 0).toFixed(2) + '%',
    netText: (positive ? '+' : '') + Number(item.net_edge_pct || 0).toFixed(2) + '%',
    perInvestorText: money(Number(item.per_investor_limit || 0)),
    capacityText: money(Number(item.total_capacity || 0)),
    profitText: money(Number(item.expected_profit || 0)),
    amountText: money(Number(item.amount || 0)),
    confidenceText: item.data_confidence === 'low' ? '低' : item.data_confidence === 'high' ? '高' : '中',
  }
}

Page({
  data: {
    account: EMPTY_ACCOUNT,
    summary: EMPTY_SUMMARY,
    allItems: [] as DisplayItem[],
    items: [] as DisplayItem[],
    filters: [
      { key: 'all', label: '全部' },
      { key: 'verify', label: '待核实' },
      { key: 'watch', label: '观察' },
      { key: 'closed', label: '暂停' },
    ],
    activeFilter: 'all',
    displayUpdatedAt: '--',
    message: '',
    loading: true,
    error: '',
  },
  _timer: 0 as number,

  onLoad() {
    this.fetch()
    ;(this as any)._timer = setInterval(() => this.fetch(), 60000)
  },

  onUnload() {
    const timer = (this as any)._timer
    if (timer) clearInterval(timer)
  },

  onPullDownRefresh() {
    this.fetch(() => wx.stopPullDownRefresh())
  },

  onFilterTap(e: WechatMiniprogram.BaseEvent) {
    const key = String((e.currentTarget.dataset || {}).key || 'all')
    const allItems = this.data.allItems
    const items = key === 'all'
      ? allItems
      : allItems.filter((item) => item.signal === key)
    this.setData({ activeFilter: key, items })
  },

  fetch(done?: () => void) {
    this.setData({ loading: true, error: '' })
    request<ArbitrageResponse>(API_PATH.ARBITRAGE, { timeout: 30000 })
      .then((res) => {
        const allItems = (res.items || []).map(toDisplay)
        const activeFilter = this.data.activeFilter
        const items = activeFilter === 'all'
          ? allItems
          : allItems.filter((item) => item.signal === activeFilter)
        this.setData({
          account: res.account || EMPTY_ACCOUNT,
          summary: res.summary || EMPTY_SUMMARY,
          allItems,
          items,
          displayUpdatedAt: res.updated_at || '--',
          message: res.message || '',
          loading: false,
          error: res.status === 'unavailable' ? (res.message || '公开数据暂不可用') : '',
        })
      })
      .catch((err) => {
        console.error('套利扫描失败', err)
        this.setData({
          loading: false,
          error: '无法连接套利数据服务，未展示模拟机会',
        })
      })
      .finally(() => done && done())
  },
})
