import { request, API_PATH } from '../../utils/api'

interface NewsItem {
  title: string
  summary: string
  url: string
  source: string
  feedName: string
  sourceTierText: string
  translated: boolean
  time: string
  date: string
  expanded: boolean
  hasSummary: boolean
}

interface NewsChannel {
  key: string
  name: string
  description: string
  count: number
  items: NewsItem[]
  tabClass: string
}

function displayItems(items: Record<string, any>[]): NewsItem[] {
  return items.map((item) => ({
    title: String(item.title || ''),
    summary: String(item.summary || ''),
    url: String(item.url || ''),
    source: String(item.source || '来源未知'),
    feedName: String(item.feed_name || ''),
    sourceTierText: item.source_tier === 'first_party' ? '官方一手' : '媒体/聚合',
    translated: item.translation_status === 'translated',
    time: String(item.time || item.date || '时间未知'),
    date: String(item.date || ''),
    expanded: false,
    hasSummary: Boolean(item.summary),
  }))
}

Page({
  data: {
    channels: [] as NewsChannel[],
    activeKey: 'technology',
    activeName: '科技',
    activeDescription: '',
    currentNews: [] as NewsItem[],
    loading: true,
    error: '',
    updatedAt: '--',
    date: '--',
    dailySummary: '',
    disclaimer: '',
    showEmpty: false,
  },
  _refreshTimer: 0 as number,

  onLoad() { this.fetchNews() },
  onShow() {
    const timer = (this as any)._refreshTimer
    if (timer) clearInterval(timer)
    ;(this as any)._refreshTimer = setInterval(() => this.fetchNews(undefined, true), 300000)
  },
  onHide() { this.stopRefresh() },
  onUnload() { this.stopRefresh() },
  onPullDownRefresh() { this.fetchNews(() => wx.stopPullDownRefresh()) },

  stopRefresh() {
    const timer = (this as any)._refreshTimer
    if (timer) clearInterval(timer)
    ;(this as any)._refreshTimer = 0
  },

  decorateChannels(rawChannels: Record<string, any>[], activeKey: string): NewsChannel[] {
    return rawChannels.map((channel) => ({
      key: String(channel.key || ''),
      name: String(channel.name || ''),
      description: String(channel.description || ''),
      count: Number(channel.count || 0),
      items: displayItems(channel.items || []),
      tabClass: channel.key === activeKey ? 'tab-item tab-active' : 'tab-item',
    }))
  },

  applyChannel(channels: NewsChannel[], key: string) {
    const selected = channels.find((channel) => channel.key === key) || channels[0]
    if (!selected) {
      this.setData({ channels: [], currentNews: [], showEmpty: true })
      return
    }
    const decorated = channels.map((channel) => ({
      ...channel,
      tabClass: channel.key === selected.key ? 'tab-item tab-active' : 'tab-item',
    }))
    this.setData({
      channels: decorated,
      activeKey: selected.key,
      activeName: selected.name,
      activeDescription: selected.description,
      currentNews: selected.items,
      showEmpty: selected.items.length === 0,
    })
  },

  onTabSelect(e: WechatMiniprogram.BaseEvent) {
    const key = String((e.currentTarget.dataset || {}).key || '')
    this.applyChannel(this.data.channels, key)
  },

  onToggleSummary(e: WechatMiniprogram.BaseEvent) {
    const index = Number((e.currentTarget.dataset || {}).index)
    if (!Number.isInteger(index) || !this.data.currentNews[index]) return
    const items = this.data.currentNews.map((item, itemIndex) => ({
      ...item,
      expanded: itemIndex === index ? !item.expanded : item.expanded,
    }))
    this.setData({ currentNews: items })
  },

  onCopySource(e: WechatMiniprogram.BaseEvent) {
    const url = String((e.currentTarget.dataset || {}).url || '')
    if (!url) return
    wx.setClipboardData({
      data: url,
      success: () => wx.showToast({ title: '原文链接已复制', icon: 'none' }),
    })
  },

  fetchNews(done?: () => void, silent = false) {
    if (!silent) this.setData({ loading: true, error: '', showEmpty: false })
    request<any>(API_PATH.NEWS, { timeout: 60000 })
      .then((res) => {
        const rawChannels = Array.isArray(res.channels) ? res.channels : []
        const activeKey = this.data.activeKey || 'technology'
        const channels = this.decorateChannels(rawChannels, activeKey)
        this.setData({
          loading: false,
          error: '',
          updatedAt: res.updated_at || '--',
          date: res.date || '--',
          dailySummary: res.summary || '',
          disclaimer: res.disclaimer || '',
        })
        this.applyChannel(channels, activeKey)
      })
      .catch((error) => {
        console.error('[前沿资讯失败]', error)
        if (!silent) this.setData({ loading: false, error: '资讯同步失败，请下拉重试', showEmpty: true })
      })
      .finally(() => done && done())
  },
})
