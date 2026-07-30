"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const api_1 = require("../../utils/api");
const EMPTY_ACCOUNT = {
    investors: 8,
    on_exchange_per_investor: 6,
    off_exchange_per_investor: 1,
    cash_per_investor: 10000,
    total_channels: 56,
    total_cash: 80000,
};
const EMPTY_SUMMARY = {
    market_total: 0,
    analyzed: 0,
    opportunities: 0,
    need_verification: 0,
    watching: 0,
    elapsed_ms: 0,
};
function money(value) {
    if (!Number.isFinite(value))
        return '¥--';
    return '¥' + Math.round(value).toLocaleString('zh-CN');
}
function signalClass(signal) {
    if (signal === 'opportunity')
        return 'signal signal-ready';
    if (signal === 'verify')
        return 'signal signal-verify';
    if (signal === 'watch')
        return 'signal signal-watch';
    if (signal === 'closed')
        return 'signal signal-closed';
    return 'signal signal-none';
}
function toDisplay(item) {
    const positive = Number(item.net_edge_pct || 0) > 0;
    return {
        ...item,
        cardCls: positive ? 'fund-card fund-card-positive' : 'fund-card',
        signalCls: signalClass(item.signal),
        signalText: item.signal_text || '观察',
        edgeCls: positive ? 'edge-value edge-positive' : 'edge-value',
        expanded: false,
        priceText: Number(item.exit_price || item.price || 0).toFixed(4),
        navText: Number(item.reference_nav || 0).toFixed(4),
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
    };
}
Page({
    data: {
        account: EMPTY_ACCOUNT,
        accountTotalText: money(EMPTY_ACCOUNT.total_cash),
        summary: EMPTY_SUMMARY,
        allItems: [],
        items: [],
        filters: [
            { key: 'all', label: '全部' },
            { key: 'opportunity', label: '可执行' },
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
    _timer: 0,
    onLoad() {
        this.fetch();
        this._timer = setInterval(() => this.fetch(), 60000);
    },
    onUnload() {
        const timer = this._timer;
        if (timer)
            clearInterval(timer);
    },
    onPullDownRefresh() {
        this.fetch(() => wx.stopPullDownRefresh());
    },
    onRefresh() {
        this.fetch();
    },
    onFilterTap(e) {
        const key = String((e.currentTarget.dataset || {}).key || 'all');
        const allItems = this.data.allItems;
        const items = key === 'all'
            ? allItems
            : allItems.filter((item) => item.signal === key);
        this.setData({ activeFilter: key, items });
    },
    onItemTap(e) {
        const code = String((e.currentTarget.dataset || {}).code || '');
        const allItems = this.data.allItems.map((item) => ({
            ...item,
            expanded: item.code === code ? !item.expanded : item.expanded,
        }));
        const activeFilter = this.data.activeFilter;
        const items = activeFilter === 'all'
            ? allItems
            : allItems.filter((item) => item.signal === activeFilter);
        this.setData({ allItems, items });
    },
    fetch(done) {
        this.setData({ loading: true, error: '' });
        (0, api_1.request)(api_1.API_PATH.ARBITRAGE, { timeout: 30000 })
            .then((res) => {
            const account = res.account || EMPTY_ACCOUNT;
            const allItems = (res.items || [])
                .map(toDisplay)
                .sort((a, b) => b.net_edge_pct - a.net_edge_pct);
            const activeFilter = this.data.activeFilter;
            const items = activeFilter === 'all'
                ? allItems
                : allItems.filter((item) => item.signal === activeFilter);
            this.setData({
                account,
                accountTotalText: money(account.total_cash),
                summary: res.summary || EMPTY_SUMMARY,
                allItems,
                items,
                displayUpdatedAt: res.updated_at || '--',
                message: res.message || '',
                loading: false,
                error: res.status === 'unavailable'
                    ? (res.message || '公开数据暂不可用')
                    : '',
            });
        })
            .catch((err) => {
            console.error('套利扫描失败', err);
            this.setData({
                loading: false,
                error: '无法连接套利数据服务，未展示模拟机会',
            });
        })
            .finally(() => done && done());
    },
});
