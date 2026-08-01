import { request, API_PATH } from '../../utils/api'

interface IndexItem {
  code: string
  name: string
  price: number
  change_pct: number
}

interface AiStatus {
  configured: boolean
  provider: string
  model: string
  message: string
}

interface SearchItem {
  symbol: string
  name: string
  quote_code: string
  market: string
  security_type: string
}

interface AssetSnapshot {
  status: string
  symbol: string
  name: string
  quote_code: string
  price?: number | null
  change_pct?: number | null
  high?: number | null
  low?: number | null
  pe?: number | null
  pb?: number | null
  turnover_rate?: number | null
  market_cap?: number | null
  source?: string
}

interface ResearchNote {
  id: string
  title: string
  content: string
  symbol: string
  note_type: string
  updated_at: string
}

interface ResearchTask {
  id: string
  title: string
  status: string
  progress: number
  stage: string
  result: string
  error: string
}

interface ResearchDossier {
  status: string
  updated_at: string
  market_scope: string
  snapshot: AssetSnapshot
  financials: any
  valuation: any
  announcements: any
  reports: any
  fund_flow: any
  completeness: { available: number; total: number; text: string }
}

interface DisplayIndex extends IndexItem {
  priceText: string
  changeText: string
  changeCls: string
}

interface DisplayAsset extends AssetSnapshot {
  priceText: string
  changeText: string
  changeCls: string
  peText: string
  pbText: string
  turnoverText: string
  marketCapText: string
}

const EMPTY_AI: AiStatus = {
  configured: false,
  provider: '未配置',
  model: '',
  message: '配置模型后启用AI研究',
}

function numberText(value?: number | null, digits = 2): string {
  return value == null || !Number.isFinite(Number(value))
    ? '--'
    : Number(value).toFixed(digits)
}

function percentText(value?: number | null): string {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  const number = Number(value)
  return (number > 0 ? '+' : '') + number.toFixed(2) + '%'
}

function moneyText(value?: number | null): string {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  const number = Number(value)
  if (Math.abs(number) >= 100000000) return (number / 100000000).toFixed(2) + '亿'
  if (Math.abs(number) >= 10000) return (number / 10000).toFixed(2) + '万'
  return Math.round(number).toLocaleString('zh-CN')
}

function displayIndex(item: IndexItem): DisplayIndex {
  const change = Number(item.change_pct || 0)
  return {
    ...item,
    priceText: numberText(item.price),
    changeText: percentText(change),
    changeCls: change >= 0 ? 'index-change rise' : 'index-change fall',
  }
}

function displayAsset(item: AssetSnapshot): DisplayAsset {
  const change = Number(item.change_pct || 0)
  return {
    ...item,
    priceText: numberText(item.price, 3),
    changeText: percentText(change),
    changeCls: change >= 0 ? 'asset-change rise' : 'asset-change fall',
    peText: numberText(item.pe),
    pbText: numberText(item.pb),
    turnoverText: percentText(item.turnover_rate),
    marketCapText: moneyText(item.market_cap),
  }
}

function displayDossier(item: ResearchDossier): any {
  const financial = (item.financials || {}).latest || {}
  const flow = (item.fund_flow || {}).latest || {}
  return {
    ...item,
    valuation: {
      ...(item.valuation || {}),
      peText: numberText((item.valuation || {}).pe),
      pbText: numberText((item.valuation || {}).pb),
      forwardPeText: numberText((item.valuation || {}).forward_pe),
    },
    financials: {
      ...(item.financials || {}),
      period: financial.period || '--',
      revenueText: moneyText(financial.revenue),
      revenueYoyText: percentText(financial.revenue_yoy),
      netProfitText: moneyText(financial.net_profit),
      netProfitYoyText: percentText(financial.net_profit_yoy),
      roeText: percentText(financial.roe),
      grossMarginText: percentText(financial.gross_margin),
      netMarginText: percentText(financial.net_margin),
      debtRatioText: percentText(financial.debt_ratio),
    },
    fund_flow: {
      ...(item.fund_flow || {}),
      date: flow.date || '--',
      mainNetText: moneyText(flow.main_net),
      largeNetText: moneyText(flow.large_net),
      superLargeNetText: moneyText(flow.super_large_net),
      mainNetCls: Number(flow.main_net || 0) >= 0 ? 'flow-value rise' : 'flow-value fall',
    },
  }
}

Page({
  data: {
    loading: true,
    error: '',
    updatedAt: '--',
    indices: [] as DisplayIndex[],
    ai: EMPTY_AI,
    query: '',
    searching: false,
    searchItems: [] as SearchItem[],
    asset: null as DisplayAsset | null,
    dossier: null as any,
    dossierLoading: false,
    noteTitle: '',
    noteContent: '',
    notes: [] as ResearchNote[],
    savingNote: false,
    activeTask: null as ResearchTask | null,
  },
  _taskTimer: 0 as number,

  onLoad() {
    this.loadOverview()
    this.loadNotes()
  },

  onUnload() {
    const timer = (this as any)._taskTimer
    if (timer) clearInterval(timer)
  },

  onPullDownRefresh() {
    Promise.all([this.loadOverview(), this.loadNotes()])
      .finally(() => wx.stopPullDownRefresh())
  },

  loadOverview(): Promise<void> {
    this.setData({ loading: true, error: '' })
    return request<any>(API_PATH.RESEARCH_OVERVIEW, { timeout: 20000 })
      .then((res) => {
        this.setData({
          indices: (res.indices || []).map(displayIndex),
          ai: res.ai || EMPTY_AI,
          updatedAt: res.updated_at || '--',
          loading: false,
          error: res.status === 'partial' ? '部分市场数据暂不可用' : '',
        })
      })
      .catch(() => {
        this.setData({ loading: false, error: '无法连接AI投研服务' })
      })
  },

  onQueryInput(e: WechatMiniprogram.Input) {
    this.setData({ query: String(e.detail.value || '') })
  },

  onSearch() {
    const query = this.data.query.trim()
    if (!query) {
      wx.showToast({ title: '请输入股票名称或代码', icon: 'none' })
      return
    }
    this.setData({ searching: true, searchItems: [], asset: null, dossier: null })
    request<any>(API_PATH.RESEARCH_SEARCH, {
      data: { q: query },
      timeout: 15000,
    })
      .then((res) => this.setData({ searchItems: res.items || [] }))
      .catch(() => wx.showToast({ title: '搜索暂不可用', icon: 'none' }))
      .finally(() => this.setData({ searching: false }))
  },

  onSelectAsset(e: WechatMiniprogram.BaseEvent) {
    const quoteCode = String((e.currentTarget.dataset || {}).quoteCode || '')
    if (!quoteCode) return
    wx.showLoading({ title: '读取数据' })
    request<AssetSnapshot>(API_PATH.RESEARCH_ASSET, {
      data: { quote_code: quoteCode },
      timeout: 20000,
    })
      .then((asset) => {
        if (asset.status !== 'success') throw new Error('unavailable')
        this.setData({ asset: displayAsset(asset), searchItems: [] })
        this.loadDossier(quoteCode)
      })
      .catch(() => wx.showToast({ title: '个股数据暂不可用', icon: 'none' }))
      .finally(() => wx.hideLoading())
  },

  loadDossier(quoteCode: string) {
    this.setData({ dossierLoading: true, dossier: null })
    request<ResearchDossier>(API_PATH.RESEARCH_DOSSIER, {
      data: { quote_code: quoteCode },
      timeout: 60000,
    })
      .then((dossier) => this.setData({ dossier: displayDossier(dossier) }))
      .catch(() => wx.showToast({ title: '部分研究数据暂不可用', icon: 'none' }))
      .finally(() => this.setData({ dossierLoading: false }))
  },

  onOpenSource(e: WechatMiniprogram.BaseEvent) {
    const url = String((e.currentTarget.dataset || {}).url || '')
    if (!url) return
    wx.setClipboardData({
      data: url,
      success: () => wx.showToast({ title: '原文链接已复制', icon: 'none' }),
    })
  },

  onRunReview() {
    this.createTask('review', '今日市场复盘', '根据指数和市场数据生成中立复盘', {
      indices: this.data.indices,
      updated_at: this.data.updatedAt,
    })
  },

  onRunResearch() {
    const asset = this.data.asset
    if (!asset) {
      wx.showToast({ title: '请先搜索并选择股票', icon: 'none' })
      return
    }
    this.createTask('research', `${asset.name} 个股研究`, '整理五维客观研究框架', asset)
  },

  onRunDebate() {
    const asset = this.data.asset
    if (!asset) {
      wx.showToast({ title: '请先选择辩论标的', icon: 'none' })
      return
    }
    this.createTask('debate', `${asset.name} 多空辩论`, '基于同一份客观数据梳理多空分歧', asset)
  },

  createTask(taskType: string, title: string, prompt: string, context: any) {
    if (!this.data.ai.configured) {
      wx.showModal({
        title: 'AI服务尚未配置',
        content: '行情、搜索和研究记录已经可用。后续在VPS环境变量中配置模型后即可运行AI任务。',
        showCancel: false,
      })
      return
    }
    wx.showLoading({ title: '创建任务' })
    request<ResearchTask>(API_PATH.RESEARCH_TASKS, {
      method: 'POST',
      data: {
        task_type: taskType,
        title,
        prompt,
        symbol: this.data.asset ? this.data.asset.symbol : '',
        context,
      },
      timeout: 15000,
    })
      .then((task) => {
        this.setData({ activeTask: task })
        this.startTaskPolling(task.id)
      })
      .catch(() => wx.showToast({ title: '任务创建失败', icon: 'none' }))
      .finally(() => wx.hideLoading())
  },

  startTaskPolling(taskId: string) {
    const oldTimer = (this as any)._taskTimer
    if (oldTimer) clearInterval(oldTimer)
    const poll = () => {
      request<ResearchTask>(`${API_PATH.RESEARCH_TASKS}/${taskId}`, { timeout: 10000 })
        .then((task) => {
          this.setData({ activeTask: task })
          if (['completed', 'failed', 'needs_config'].includes(task.status)) {
            const timer = (this as any)._taskTimer
            if (timer) clearInterval(timer)
          }
        })
        .catch(() => undefined)
    }
    poll()
    ;(this as any)._taskTimer = setInterval(poll, 3000)
  },

  onNoteTitleInput(e: WechatMiniprogram.Input) {
    this.setData({ noteTitle: String(e.detail.value || '') })
  },

  onNoteContentInput(e: WechatMiniprogram.TextareaInput) {
    this.setData({ noteContent: String(e.detail.value || '') })
  },

  loadNotes(): Promise<void> {
    return request<any>(API_PATH.RESEARCH_NOTES, { timeout: 10000 })
      .then((res) => this.setData({ notes: res.items || [] }))
      .catch(() => undefined)
  },

  onSaveNote() {
    const content = this.data.noteContent.trim()
    if (!content) {
      wx.showToast({ title: '请输入研究内容', icon: 'none' })
      return
    }
    const asset = this.data.asset
    this.setData({ savingNote: true })
    request(API_PATH.RESEARCH_NOTES, {
      method: 'POST',
      data: {
        title: this.data.noteTitle.trim() || (asset ? `${asset.name} 研究记录` : '研究记录'),
        content,
        symbol: asset ? asset.symbol : '',
        note_type: 'manual',
      },
      timeout: 10000,
    })
      .then(() => {
        this.setData({ noteTitle: '', noteContent: '' })
        wx.showToast({ title: '已保存', icon: 'success' })
        return this.loadNotes()
      })
      .catch(() => wx.showToast({ title: '保存失败', icon: 'none' }))
      .finally(() => this.setData({ savingNote: false }))
  },

  onDeleteNote(e: WechatMiniprogram.BaseEvent) {
    const id = String((e.currentTarget.dataset || {}).id || '')
    if (!id) return
    wx.showModal({
      title: '删除研究记录',
      content: '确定删除这条记录吗？',
      success: (res) => {
        if (!res.confirm) return
        request(`${API_PATH.RESEARCH_NOTES}/${id}`, { method: 'DELETE' })
          .then(() => this.loadNotes())
          .catch(() => wx.showToast({ title: '删除失败', icon: 'none' }))
      },
    })
  },
})
