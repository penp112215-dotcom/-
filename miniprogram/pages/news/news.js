"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const api_1 = require("../../utils/api");
Page({
    data: {
        tabs: [], // 从后端动态获取的新闻源名称列表（如华尔街见闻、36氪）
        activeTab: '', // 当前选中的标签源
        currentNews: [], // 当前标签源下的新闻列表
        allSources: {}, // 缓存所有源的数据
        loading: true,
        updatedAt: '--'
    },
    onLoad() {
        this.fetchNews();
    },
    onPullDownRefresh() {
        this.fetchNews(() => wx.stopPullDownRefresh());
    },
    // 点击横向标签栏时的切换逻辑
    onTabSelect(e) {
        const tabName = e.currentTarget.dataset.tab;
        const sources = this.data.allSources;
        this.setData({
            activeTab: tabName,
            currentNews: sources && sources[tabName] ? sources[tabName] : []
        });
    },
    fetchNews(cb) {
        this.setData({ loading: true });
        (0, api_1.request)(api_1.API_PATH.NEWS, { timeout: 10000 })
            .then((res) => {
            const sources = res.sources || {};
            const tabList = Object.keys(sources);
            const defaultTab = tabList.length > 0 ? tabList[0] : '';
            this.setData({
                allSources: sources,
                tabs: tabList,
                activeTab: defaultTab,
                currentNews: defaultTab ? sources[defaultTab] : [],
                updatedAt: res.updated_at || '刚刚',
                loading: false
            });
            if (cb)
                cb();
            wx.hideLoading();
        })
            .catch(() => {
            this.setData({ loading: false });
            if (cb)
                cb();
            wx.hideLoading();
        });
    }
});
