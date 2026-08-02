"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const api_1 = require("../../utils/api");
function displayItems(items) {
    return items.map((item) => ({
        title: String(item.title || ''),
        summary: String(item.summary || ''),
        url: String(item.url || ''),
        source: String(item.source || '来源未知'),
        time: String(item.time || item.date || '时间未知'),
        date: String(item.date || ''),
        expanded: false,
        hasSummary: Boolean(item.summary),
    }));
}
Page({
    data: {
        channels: [],
        activeKey: 'technology',
        activeName: '科技',
        activeDescription: '',
        currentNews: [],
        loading: true,
        error: '',
        updatedAt: '--',
        date: '--',
        dailySummary: '',
        disclaimer: '',
        showEmpty: false,
    },
    _refreshTimer: 0,
    onLoad() { this.fetchNews(); },
    onShow() {
        const timer = this._refreshTimer;
        if (timer)
            clearInterval(timer);
        this._refreshTimer = setInterval(() => this.fetchNews(undefined, true), 300000);
    },
    onHide() { this.stopRefresh(); },
    onUnload() { this.stopRefresh(); },
    onPullDownRefresh() { this.fetchNews(() => wx.stopPullDownRefresh()); },
    stopRefresh() {
        const timer = this._refreshTimer;
        if (timer)
            clearInterval(timer);
        this._refreshTimer = 0;
    },
    decorateChannels(rawChannels, activeKey) {
        return rawChannels.map((channel) => ({
            key: String(channel.key || ''),
            name: String(channel.name || ''),
            description: String(channel.description || ''),
            count: Number(channel.count || 0),
            items: displayItems(channel.items || []),
            tabClass: channel.key === activeKey ? 'tab-item tab-active' : 'tab-item',
        }));
    },
    applyChannel(channels, key) {
        const selected = channels.find((channel) => channel.key === key) || channels[0];
        if (!selected) {
            this.setData({ channels: [], currentNews: [], showEmpty: true });
            return;
        }
        const decorated = channels.map((channel) => ({
            ...channel,
            tabClass: channel.key === selected.key ? 'tab-item tab-active' : 'tab-item',
        }));
        this.setData({
            channels: decorated,
            activeKey: selected.key,
            activeName: selected.name,
            activeDescription: selected.description,
            currentNews: selected.items,
            showEmpty: selected.items.length === 0,
        });
    },
    onTabSelect(e) {
        const key = String((e.currentTarget.dataset || {}).key || '');
        this.applyChannel(this.data.channels, key);
    },
    onToggleSummary(e) {
        const index = Number((e.currentTarget.dataset || {}).index);
        if (!Number.isInteger(index) || !this.data.currentNews[index])
            return;
        const items = this.data.currentNews.map((item, itemIndex) => ({
            ...item,
            expanded: itemIndex === index ? !item.expanded : item.expanded,
        }));
        this.setData({ currentNews: items });
    },
    onCopySource(e) {
        const url = String((e.currentTarget.dataset || {}).url || '');
        if (!url)
            return;
        wx.setClipboardData({
            data: url,
            success: () => wx.showToast({ title: '原文链接已复制', icon: 'none' }),
        });
    },
    fetchNews(done, silent = false) {
        if (!silent)
            this.setData({ loading: true, error: '', showEmpty: false });
        (0, api_1.request)(api_1.API_PATH.NEWS, { timeout: 60000 })
            .then((res) => {
            const rawChannels = Array.isArray(res.channels) ? res.channels : [];
            const activeKey = this.data.activeKey || 'technology';
            const channels = this.decorateChannels(rawChannels, activeKey);
            this.setData({
                loading: false,
                error: '',
                updatedAt: res.updated_at || '--',
                date: res.date || '--',
                dailySummary: res.summary || '',
                disclaimer: res.disclaimer || '',
            });
            this.applyChannel(channels, activeKey);
        })
            .catch((error) => {
            console.error('[前沿资讯失败]', error);
            if (!silent)
                this.setData({ loading: false, error: '资讯同步失败，请下拉重试', showEmpty: true });
        })
            .finally(() => done && done());
    },
});
