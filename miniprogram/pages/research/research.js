"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const api_1 = require("../../utils/api");
const EMPTY_AI = {
    configured: false,
    provider: '未配置',
    model: '',
    message: '配置模型后启用AI研究',
};
function numberText(value, digits = 2) {
    return value == null || !Number.isFinite(Number(value))
        ? '--'
        : Number(value).toFixed(digits);
}
function percentText(value) {
    if (value == null || !Number.isFinite(Number(value)))
        return '--';
    const number = Number(value);
    return (number > 0 ? '+' : '') + number.toFixed(2) + '%';
}
function moneyText(value) {
    if (value == null || !Number.isFinite(Number(value)))
        return '--';
    const number = Number(value);
    if (Math.abs(number) >= 100000000)
        return (number / 100000000).toFixed(2) + '亿';
    if (Math.abs(number) >= 10000)
        return (number / 10000).toFixed(2) + '万';
    return Math.round(number).toLocaleString('zh-CN');
}
function displayIndex(item) {
    const change = Number(item.change_pct || 0);
    return {
        ...item,
        priceText: numberText(item.price),
        changeText: percentText(change),
        changeCls: change >= 0 ? 'index-change rise' : 'index-change fall',
    };
}
function displayAsset(item) {
    const change = Number(item.change_pct || 0);
    return {
        ...item,
        priceText: numberText(item.price, 3),
        changeText: percentText(change),
        changeCls: change >= 0 ? 'asset-change rise' : 'asset-change fall',
        peText: numberText(item.pe),
        pbText: numberText(item.pb),
        turnoverText: percentText(item.turnover_rate),
        marketCapText: moneyText(item.market_cap),
    };
}
function displayDossier(item) {
    const financial = (item.financials || {}).latest || {};
    const flow = (item.fund_flow || {}).latest || {};
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
    };
}
Page({
    data: {
        loading: true,
        error: '',
        updatedAt: '--',
        indices: [],
        ai: EMPTY_AI,
        query: '',
        searching: false,
        searchMessage: '输入股票名称或代码，停止输入后会自动搜索',
        searchItems: [],
        asset: null,
        dossier: null,
        dossierLoading: false,
        noteTitle: '',
        noteContent: '',
        notes: [],
        savingNote: false,
        activeTask: null,
    },
    _taskTimer: 0,
    _searchTimer: 0,
    onLoad() {
        this.loadOverview();
        this.loadNotes();
    },
    onUnload() {
        const timer = this._taskTimer;
        if (timer)
            clearInterval(timer);
        const searchTimer = this._searchTimer;
        if (searchTimer)
            clearTimeout(searchTimer);
    },
    onPullDownRefresh() {
        Promise.all([this.loadOverview(), this.loadNotes()])
            .finally(() => wx.stopPullDownRefresh());
    },
    loadOverview() {
        this.setData({ loading: true, error: '' });
        return (0, api_1.request)(api_1.API_PATH.RESEARCH_OVERVIEW, { timeout: 20000 })
            .then((res) => {
            this.setData({
                indices: (res.indices || []).map(displayIndex),
                ai: res.ai || EMPTY_AI,
                updatedAt: res.updated_at || '--',
                loading: false,
                error: res.status === 'partial' ? '部分市场数据暂不可用' : '',
            });
        })
            .catch(() => {
            this.setData({ loading: false, error: '无法连接AI投研服务' });
        });
    },
    onQueryInput(e) {
        const query = String(e.detail.value || '').trim();
        this.setData({
            query,
            searchMessage: query ? '等待搜索…' : '输入股票名称或代码，停止输入后会自动搜索',
        });
        const oldTimer = this._searchTimer;
        if (oldTimer)
            clearTimeout(oldTimer);
        if (query.length < 2)
            return;
        this._searchTimer = setTimeout(() => this.performSearch(query), 450);
    },
    onSearch() {
        const query = this.data.query.trim();
        if (!query) {
            wx.showToast({ title: '请输入股票名称或代码', icon: 'none' });
            return;
        }
        this.performSearch(query);
    },
    performSearch(query) {
        if (!query || this.data.searching)
            return;
        this.setData({
            searching: true,
            searchMessage: '正在搜索…',
            searchItems: [],
            asset: null,
            dossier: null,
        });
        (0, api_1.request)(api_1.API_PATH.RESEARCH_SEARCH, {
            data: { q: query },
            timeout: 15000,
        })
            .then((res) => {
            const items = (res.items || []);
            if (!items.length) {
                this.setData({ searchItems: [], searchMessage: '没有找到匹配的股票，请换名称或代码' });
                return;
            }
            const normalized = query.toUpperCase().replace(/[^A-Z0-9]/g, '');
            const exact = items.find((item) => item.symbol.toUpperCase() === normalized);
            this.setData({
                searchItems: exact ? [] : items,
                searchMessage: exact ? `已找到 ${exact.name}，正在读取详情…` : `找到 ${items.length} 个结果，请选择`,
            });
            if (exact)
                this.selectAsset(exact.quote_code);
        })
            .catch((error) => {
            console.error('[投研搜索失败]', error);
            this.setData({ searchMessage: '无法连接本地服务，请确认后端已启动，并关闭合法域名校验' });
            wx.showToast({ title: '搜索连接失败', icon: 'none' });
        })
            .finally(() => this.setData({ searching: false }));
    },
    onSelectAsset(e) {
        const quoteCode = String((e.currentTarget.dataset || {}).quoteCode || '');
        this.selectAsset(quoteCode);
    },
    selectAsset(quoteCode) {
        if (!quoteCode)
            return;
        wx.showLoading({ title: '读取数据' });
        (0, api_1.request)(api_1.API_PATH.RESEARCH_ASSET, {
            data: { quote_code: quoteCode },
            timeout: 20000,
        })
            .then((asset) => {
            if (asset.status !== 'success')
                throw new Error('unavailable');
            this.setData({
                asset: displayAsset(asset),
                searchItems: [],
                searchMessage: `已载入 ${asset.name}`,
            });
            this.loadDossier(quoteCode);
        })
            .catch((error) => {
            console.error('[个股详情失败]', error);
            this.setData({ searchMessage: '已找到股票，但详情读取失败，请稍后重试' });
            wx.showToast({ title: '个股数据暂不可用', icon: 'none' });
        })
            .finally(() => wx.hideLoading());
    },
    loadDossier(quoteCode) {
        this.setData({ dossierLoading: true, dossier: null });
        (0, api_1.request)(api_1.API_PATH.RESEARCH_DOSSIER, {
            data: { quote_code: quoteCode },
            timeout: 60000,
        })
            .then((dossier) => this.setData({ dossier: displayDossier(dossier) }))
            .catch(() => wx.showToast({ title: '部分研究数据暂不可用', icon: 'none' }))
            .finally(() => this.setData({ dossierLoading: false }));
    },
    onOpenSource(e) {
        const url = String((e.currentTarget.dataset || {}).url || '');
        if (!url)
            return;
        wx.setClipboardData({
            data: url,
            success: () => wx.showToast({ title: '原文链接已复制', icon: 'none' }),
        });
    },
    onRunReview() {
        this.createTask('review', '今日市场复盘', '根据指数和市场数据生成中立复盘', {
            indices: this.data.indices,
            updated_at: this.data.updatedAt,
        });
    },
    onRunResearch() {
        const asset = this.data.asset;
        if (!asset) {
            wx.showToast({ title: '请先搜索并选择股票', icon: 'none' });
            return;
        }
        this.createTask('research', `${asset.name} 个股研究`, '整理五维客观研究框架', asset);
    },
    onRunDebate() {
        const asset = this.data.asset;
        if (!asset) {
            wx.showToast({ title: '请先选择辩论标的', icon: 'none' });
            return;
        }
        this.createTask('debate', `${asset.name} 多空辩论`, '基于同一份客观数据梳理多空分歧', asset);
    },
    createTask(taskType, title, prompt, context) {
        if (!this.data.ai.configured) {
            wx.showModal({
                title: 'AI服务尚未配置',
                content: '行情、搜索和研究记录已经可用。后续在VPS环境变量中配置模型后即可运行AI任务。',
                showCancel: false,
            });
            return;
        }
        wx.showLoading({ title: '创建任务' });
        (0, api_1.request)(api_1.API_PATH.RESEARCH_TASKS, {
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
            this.setData({ activeTask: task });
            this.startTaskPolling(task.id);
        })
            .catch(() => wx.showToast({ title: '任务创建失败', icon: 'none' }))
            .finally(() => wx.hideLoading());
    },
    startTaskPolling(taskId) {
        const oldTimer = this._taskTimer;
        if (oldTimer)
            clearInterval(oldTimer);
        const poll = () => {
            (0, api_1.request)(`${api_1.API_PATH.RESEARCH_TASKS}/${taskId}`, { timeout: 10000 })
                .then((task) => {
                this.setData({ activeTask: task });
                if (['completed', 'failed', 'needs_config'].includes(task.status)) {
                    const timer = this._taskTimer;
                    if (timer)
                        clearInterval(timer);
                }
            })
                .catch(() => undefined);
        };
        poll();
        this._taskTimer = setInterval(poll, 3000);
    },
    onNoteTitleInput(e) {
        this.setData({ noteTitle: String(e.detail.value || '') });
    },
    onNoteContentInput(e) {
        this.setData({ noteContent: String(e.detail.value || '') });
    },
    loadNotes() {
        return (0, api_1.request)(api_1.API_PATH.RESEARCH_NOTES, { timeout: 10000 })
            .then((res) => this.setData({ notes: res.items || [] }))
            .catch(() => undefined);
    },
    onSaveNote() {
        const content = this.data.noteContent.trim();
        if (!content) {
            wx.showToast({ title: '请输入研究内容', icon: 'none' });
            return;
        }
        const asset = this.data.asset;
        this.setData({ savingNote: true });
        (0, api_1.request)(api_1.API_PATH.RESEARCH_NOTES, {
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
            this.setData({ noteTitle: '', noteContent: '' });
            wx.showToast({ title: '已保存', icon: 'success' });
            return this.loadNotes();
        })
            .catch(() => wx.showToast({ title: '保存失败', icon: 'none' }))
            .finally(() => this.setData({ savingNote: false }));
    },
    onDeleteNote(e) {
        const id = String((e.currentTarget.dataset || {}).id || '');
        if (!id)
            return;
        wx.showModal({
            title: '删除研究记录',
            content: '确定删除这条记录吗？',
            success: (res) => {
                if (!res.confirm)
                    return;
                (0, api_1.request)(`${api_1.API_PATH.RESEARCH_NOTES}/${id}`, { method: 'DELETE' })
                    .then(() => this.loadNotes())
                    .catch(() => wx.showToast({ title: '删除失败', icon: 'none' }));
            },
        });
    },
});
