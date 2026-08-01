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
  status_changes: number
  elapsed_ms: number
}

interface ArbitrageAlert {
  code: string
  name: string
  title: string
  detail: string
  level: string
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
  official_nav?: number | null
  estimated_nav?: number | null
  official_premium_pct?: number | null
  estimated_premium_pct?: number | null
  nav_basis: string
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
  average_premium_3d_pct?: number | null
  premium_vs_3d_pct?: number | null
  history_samples: number
  status_changed: boolean
}

interface DisplayItem extends ArbitrageItem {
  cardCls: string
  signalCls: string
  signalText: string
  edgeCls: string
  expanded: boolean
  priceText: string
  navText: string
  officialNavText: string
  estimatedNavText: string
  average3dText: string
  trendText: string
  trendCls: string
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
  alerts?: ArbitrageAlert[]
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
  status_changes: 0,
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

function percent(value?: number | null, withSign = false): string {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  const number = Number(value)
  const sign = withSign && number > 0 ? '+' : ''
  return sign + number.toFixed(2) + '%'
}

function nav(value?: number | null): string {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  return Number(value).toFixed(4)
}

function filterItems(items: DisplayItem[], key: string): DisplayItem[] {
  if (key === 'all') return items
  if (key === 'changed') return items.filter((item) => item.status_changed)
  return items.filter((item) => item.signal === key)
}

function toDisplay(item: ArbitrageItem): DisplayItem {
  const positive = Number(item.net_edge_pct || 0) > 0
  const trend = item.premium_vs_3d_pct
  return {
    ...item,
    cardCls: positive ? 'fund-card fund-card-positive' : 'fund-card',
    signalCls: signalClass(item.signal),
    signalText: item.signal_text || '观察',
    edgeCls: positive ? 'edge-value edge-positive' : 'edge-value',
    expanded: false,
    priceText: Number(item.exit_price || item.price || 0).toFixed(4),
    navText: Number(item.reference_nav || 0).toFixed(4),
    officialNavText: nav(item.official_nav),
    estimatedNavText: nav(item.estimated_nav),
    average3dText: percent(item.average_premium_3d_pct),
    trendText: trend == null ? '积累中' : percent(trend, true),
    trendCls: Number(trend || 0) > 0 ? 'trend trend-up' : 'trend',
    grossText: Number(item.gross_premium_pct || 0).toFixed(2) + '%',
    netText: (positive ? '+' : '') + Number(item.net_edge_pct || 0).toFixed(2) + '%',
    perInvestorText: money(Number(item.per_investor_limit || 0)),
    capacityText: money(Number(item.total_capacity || 0)),
    profitText: money(Number(item.expected_profit || 0)),
    amountText: money(Number(item.amount || 0)),
    confidenceText: item.data_confidence === 'low'
      ? '低'
      : item.data_confidence === 'high'
        ? '高'
        : '中',
  }
}

Page({
  data: {
    account: EMPTY_ACCOUNT,
    accountTotalText: money(EMPTY_ACCOUNT.total_cash),
    summary: EMPTY_SUMMARY,
    allItems: [] as DisplayItem[],
    items: [] as DisplayItem[],
    filters: [
      { key: 'all', label: '全部' },
      { key: 'changed', label: '有变化' },
      { key: 'opportunity', label: '可执行' },
      { key: 'verify', label: '待核实' },
      { key: 'watch', label: '观察' },
      { key: 'closed', label: '暂停' },
    ],
    activeFilter: 'all',
    displayUpdatedAt: '--',
    message: '',
    alerts: [] as ArbitrageAlert[],
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

  onRefresh() {
    this.fetch()
  },

  onFilterTap(e: WechatMiniprogram.BaseEvent) {
    const key = String((e.currentTarget.dataset || {}).key || 'all')
    const allItems = this.data.allItems
    const items = filterItems(allItems, key)
    this.setData({ activeFilter: key, items })
  },

  onItemTap(e: WechatMiniprogram.BaseEvent) {
    const code = String((e.currentTarget.dataset || {}).code || '')
    const allItems = this.data.allItems.map((item) => ({
      ...item,
      expanded: item.code === code ? !item.expanded : item.expanded,
    }))
    const activeFilter = this.data.activeFilter
    const items = filterItems(allItems, activeFilter)
    this.setData({ allItems, items })
  },

  fetch(done?: () => void) {
    this.setData({ loading: true, error: '' })
    request<ArbitrageResponse>(API_PATH.ARBITRAGE, { timeout: 30000 })
      .then((res) => {
        const account = res.account || EMPTY_ACCOUNT
        const allItems = (res.items || [])
          .map(toDisplay)
          .sort((a, b) => b.net_edge_pct - a.net_edge_pct)
        const activeFilter = this.data.activeFilter
        const items = filterItems(allItems, activeFilter)
        this.setData({
          account,
          accountTotalText: money(account.total_cash),
          summary: res.summary || EMPTY_SUMMARY,
          alerts: res.alerts || [],
          allItems,
          items,
          displayUpdatedAt: res.updated_at || '--',
          message: res.message || '',
          loading: false,
          error: res.status === 'unavailable'
            ? (res.message || '公开数据暂不可用')
            : '',
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
