import { request, API_PATH } from '../../utils/api'

const STORAGE_KEY = 'us_stock_holdings_v1'

interface Holding {
  symbol: string
  name: string
  targetPrice: number | null
  targetType: 'buy' | 'sell'
}

interface StockNews {
  title: string
  publisher: string
  published_at: string
  url: string
  impact_label?: string
}

interface StockApiItem {
  symbol: string
  name: string
  price: number | null
  preclose: number | null
  change_pct: number | null
  currency: string
  exchange: string
  source: string
  news?: StockNews[]
}

interface SearchItem {
  symbol: string
  name: string
  exchange: string
  type: string
}

interface StockDisplay extends StockApiItem {
  priceText: string
  changeText: string
  changeCls: string
  targetText: string
  targetTypeText: string
  alertText: string
  alertCls: string
  targetHit: boolean
  sourceText: string
  news: StockNews[]
  visibleNews: StockNews[]
  newsExpanded: boolean
  newsToggleText: string
  hasMoreNews: boolean
}

interface PortfolioResponse {
  category?: string
  updated_at?: string
  us_stocks?: StockApiItem[]
}

interface SearchResponse {
  items?: SearchItem[]
}

const DEFAULT_HOLDINGS: Holding[] = [
  { symbol: 'MSFT', name: 'Microsoft Corporation', targetPrice: null, targetType: 'buy' },
  { symbol: 'CEG', name: 'Constellation Energy', targetPrice: null, targetType: 'buy' },
  { symbol: 'NVDA', name: 'NVIDIA Corporation', targetPrice: null, targetType: 'buy' },
]

function numberOrNull(value: unknown): number | null {
  const parsed = Number(value)
  return value !== '' && value != null && Number.isFinite(parsed) ? parsed : null
}

function money(value: number | null): string {
  if (value == null) return '$--'
  return '$' + value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function normalizeHolding(raw: any): Holding | null {
  const symbol = String(raw && raw.symbol || '').toUpperCase().trim()
  if (!/^[A-Z0-9.\-]{1,15}$/.test(symbol)) return null
  return {
    symbol,
    name: String(raw.name || symbol),
    targetPrice: numberOrNull(raw.targetPrice),
    targetType: raw.targetType === 'sell' ? 'sell' : 'buy',
  }
}

function loadHoldings(): Holding[] {
  try {
    const saved = wx.getStorageSync(STORAGE_KEY)
    if (Array.isArray(saved)) {
      return saved.map(normalizeHolding).filter(Boolean) as Holding[]
    }
  } catch (err) {
    console.warn('读取美股自选失败', err)
  }
  wx.setStorageSync(STORAGE_KEY, DEFAULT_HOLDINGS)
  return DEFAULT_HOLDINGS
}

function toDisplay(
  raw: StockApiItem,
  holding: Holding,
  newsExpanded = false
): StockDisplay {
  const price = numberOrNull(raw.price)
  const change = numberOrNull(raw.change_pct)
  const rise = (change || 0) >= 0
  const target = holding.targetPrice
  let alertText = '未设置目标价'
  let alertCls = 'target-status target-neutral'
  let targetHit = false

  if (target != null && price != null) {
    if (holding.targetType === 'buy') {
      const reached = price <= target
      targetHit = reached
      const distance = Math.max(0, (price - target) / price * 100)
      alertText = reached ? '已到加仓价' : `距加仓价 ${distance.toFixed(1)}%`
      alertCls = reached ? 'target-status target-hit' : 'target-status'
    } else {
      const reached = price >= target
      targetHit = reached
      const distance = Math.max(0, (target - price) / price * 100)
      alertText = reached ? '已到止盈价' : `距止盈价 ${distance.toFixed(1)}%`
      alertCls = reached ? 'target-status target-hit' : 'target-status'
    }
  } else if (target != null) {
    alertText = '行情暂不可用'
  }

  const news = Array.isArray(raw.news) ? raw.news.slice(0, 10) : []
  return {
    ...raw,
    symbol: holding.symbol,
    name: raw.name && raw.name !== holding.symbol ? raw.name : holding.name,
    price,
    change_pct: change,
    priceText: money(price),
    changeText: change == null ? '--' : `${rise ? '+' : ''}${change.toFixed(2)}%`,
    changeCls: rise ? 'change rise' : 'change fall',
    targetText: target == null ? '未设置' : money(target),
    targetTypeText: holding.targetType === 'buy' ? '加仓价' : '止盈价',
    alertText,
    alertCls,
    targetHit,
    sourceText: raw.source === 'yahoo' ? '实时行情' : '行情暂不可用',
    news,
    visibleNews: newsExpanded ? news : news.slice(0, 3),
    newsExpanded,
    newsToggleText: newsExpanded ? '收起新闻' : `展开全部 ${news.length} 条`,
    hasMoreNews: news.length > 3,
  }
}

Page({
  data: {
    holdings: [] as Holding[],
    stocks: [] as StockDisplay[],
    updatedAt: '--',
    loading: true,
    refreshing: false,
    error: '',
    alertCount: 0,
    expandedSymbols: [] as string[],
    showSearch: false,
    searchQuery: '',
    directSymbol: '',
    searchResults: [] as SearchItem[],
    searching: false,
    searchTouched: false,
    showTargetModal: false,
    draftStock: null as SearchItem | null,
    draftTarget: '',
    draftTargetType: 'buy' as 'buy' | 'sell',
  },
  _timer: 0 as number,
  _searchTimer: 0 as number,

  onLoad() {
    const holdings = loadHoldings()
    this.setData({ holdings })
    this.fetch()
    ;(this as any)._timer = setInterval(() => this.fetch(), 60000)
  },

  onUnload() {
    const timer = (this as any)._timer
    const searchTimer = (this as any)._searchTimer
    if (timer) clearInterval(timer)
    if (searchTimer) clearTimeout(searchTimer)
  },

  onPullDownRefresh() {
    this.fetch(() => wx.stopPullDownRefresh())
  },

  noop() {},

  saveHoldings(holdings: Holding[]) {
    wx.setStorageSync(STORAGE_KEY, holdings)
    this.setData({ holdings })
  },

  onToggleSearch() {
    this.setData({
      showSearch: !this.data.showSearch,
      searchQuery: '',
      directSymbol: '',
      searchResults: [],
      searchTouched: false,
    })
  },

  onSearchInput(e: any) {
    const value = String(e.detail.value || '')
    const directSymbol = /^[A-Za-z][A-Za-z0-9.\-]{0,14}$/.test(value.trim())
      ? value.trim().toUpperCase()
      : ''
    this.setData({ searchQuery: value, directSymbol, searchTouched: false })
    const timer = (this as any)._searchTimer
    if (timer) clearTimeout(timer)
    if (!value.trim()) {
      this.setData({ searchResults: [], searching: false })
      return
    }
    ;(this as any)._searchTimer = setTimeout(() => this.searchStocks(value), 400)
  },

  onSearchConfirm() {
    this.searchStocks(this.data.searchQuery)
  },

  searchStocks(query: string) {
    const clean = String(query || '').trim()
    if (!clean) return
    this.setData({ searching: true, searchTouched: true })
    request<SearchResponse>(
      API_PATH.STOCK_SEARCH + '?q=' + encodeURIComponent(clean),
      { timeout: 12000 }
    )
      .then((res) => {
        this.setData({
          searchResults: Array.isArray(res.items) ? res.items : [],
          searching: false,
        })
      })
      .catch(() => {
        this.setData({ searchResults: [], searching: false })
      })
  },

  onSelectSearch(e: any) {
    const symbol = String((e.currentTarget.dataset || {}).symbol || '')
    const selected = this.data.searchResults.find((item) => item.symbol === symbol)
    if (!selected) return
    this.openTargetModal(selected)
  },

  onSelectDirect() {
    const symbol = this.data.directSymbol
    if (!symbol) return
    this.openTargetModal({ symbol, name: symbol, exchange: 'US', type: '美股' })
  },

  openTargetModal(stock: SearchItem) {
    const existing = this.data.holdings.find((item) => item.symbol === stock.symbol)
    this.setData({
      showTargetModal: true,
      draftStock: stock,
      draftTarget: existing && existing.targetPrice != null ? String(existing.targetPrice) : '',
      draftTargetType: existing ? existing.targetType : 'buy',
    })
  },

  onEditTarget(e: any) {
    const symbol = String((e.currentTarget.dataset || {}).symbol || '')
    const holding = this.data.holdings.find((item) => item.symbol === symbol)
    if (!holding) return
    this.openTargetModal({
      symbol: holding.symbol,
      name: holding.name,
      exchange: 'US',
      type: '美股',
    })
  },

  onTargetInput(e: any) {
    this.setData({ draftTarget: String(e.detail.value || '') })
  },

  onTargetTypeTap(e: any) {
    const type = String((e.currentTarget.dataset || {}).type || 'buy')
    this.setData({ draftTargetType: type === 'sell' ? 'sell' : 'buy' })
  },

  onCloseTarget() {
    this.setData({ showTargetModal: false, draftStock: null })
  },

  onConfirmTarget() {
    const stock = this.data.draftStock
    const target = Number(this.data.draftTarget)
    if (!stock || !Number.isFinite(target) || target <= 0) {
      wx.showToast({ title: '请输入有效目标价', icon: 'none' })
      return
    }
    const next: Holding = {
      symbol: stock.symbol,
      name: stock.name || stock.symbol,
      targetPrice: target,
      targetType: this.data.draftTargetType,
    }
    const holdings = this.data.holdings.filter((item) => item.symbol !== next.symbol)
    holdings.push(next)
    this.saveHoldings(holdings)
    this.setData({
      showTargetModal: false,
      draftStock: null,
      showSearch: false,
      searchQuery: '',
      searchResults: [],
    })
    wx.showToast({ title: '已加入持仓', icon: 'success' })
    this.fetch()
  },

  onRemove(e: any) {
    const symbol = String((e.currentTarget.dataset || {}).symbol || '')
    wx.showModal({
      title: `移除 ${symbol}`,
      content: '将同时移除本机保存的目标价，是否继续？',
      confirmColor: '#e74b4b',
      success: (res) => {
        if (!res.confirm) return
        const holdings = this.data.holdings.filter((item) => item.symbol !== symbol)
        this.saveHoldings(holdings)
        this.fetch()
      },
    })
  },

  onNewsTap(e: any) {
    const url = String((e.currentTarget.dataset || {}).url || '')
    if (!url) return
    wx.setClipboardData({
      data: url,
      success: () => wx.showToast({ title: '新闻链接已复制', icon: 'none' }),
    })
  },

  onToggleNews(e: any) {
    const symbol = String((e.currentTarget.dataset || {}).symbol || '')
    const expandedSymbols = this.data.expandedSymbols.includes(symbol)
      ? this.data.expandedSymbols.filter((item) => item !== symbol)
      : [...this.data.expandedSymbols, symbol]
    const stocks = this.data.stocks.map((stock) => {
      if (stock.symbol !== symbol) return stock
      const newsExpanded = !stock.newsExpanded
      return {
        ...stock,
        newsExpanded,
        visibleNews: newsExpanded ? stock.news : stock.news.slice(0, 3),
        newsToggleText: newsExpanded ? '收起新闻' : `展开全部 ${stock.news.length} 条`,
      }
    })
    this.setData({ expandedSymbols, stocks })
  },

  fetch(done?: () => void) {
    const holdings = this.data.holdings
    if (!holdings.length) {
      this.setData({
        stocks: [],
        loading: false,
        refreshing: false,
        alertCount: 0,
        error: '',
      })
      if (done) done()
      return
    }

    this.setData({
      loading: this.data.stocks.length === 0,
      refreshing: this.data.stocks.length > 0,
      error: '',
    })
    const symbols = holdings.map((item) => item.symbol).join(',')
    request<PortfolioResponse>(
      API_PATH.PORTFOLIO + '?symbols=' + encodeURIComponent(symbols),
      { timeout: 30000 }
    )
      .then((res) => {
        const rawItems = Array.isArray(res.us_stocks) ? res.us_stocks : []
        const rawMap: Record<string, StockApiItem> = {}
        rawItems.forEach((item) => { rawMap[item.symbol] = item })
        const expandedSymbols = this.data.expandedSymbols
        const stocks = holdings.map((holding) => toDisplay(
          rawMap[holding.symbol] || {
            symbol: holding.symbol,
            name: holding.name,
            price: null,
            preclose: null,
            change_pct: null,
            currency: 'USD',
            exchange: '',
            source: 'unavailable',
            news: [],
          },
          holding,
          expandedSymbols.includes(holding.symbol)
        ))
        this.setData({
          stocks,
          updatedAt: res.updated_at || '--',
          loading: false,
          refreshing: false,
          alertCount: stocks.filter((item) => item.targetHit).length,
        })
      })
      .catch(() => {
        this.setData({
          loading: false,
          refreshing: false,
          error: '暂时无法连接美股数据服务',
        })
      })
      .finally(() => done && done())
  },
})
