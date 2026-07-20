"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
// arbitrage.ts
// A股 ETF 套利监控
const api_1 = require("../../utils/api");
function toDisplayItem(item) {
    // 改成三元运算符，完美兼容所有版本
    const rise = (item.change_pct !== null && item.change_pct !== undefined ? item.change_pct : 0) >= 0;
    const premiumRise = (item.premium_rate || 0) >= 0;
    const live = item.source === 'live';
    const pct = item.change_pct || 0;
    const premium = item.premium_rate || 0;
    return {
        ...item,
        cardCls: rise ? 'card card-rise' : 'card card-fall',
        badgeCls: live ? 'source-badge source-badge-live' : 'source-badge source-badge-demo',
        badgeText: live ? 'LIVE' : 'DEMO',
        changeCls: rise ? 'change-block rise' : 'change-block fall',
        changeText: (rise ? '+' : '') + pct + '%',
        premiumCls: premiumRise ? 'meta-value rise' : 'meta-value fall',
        premiumText: (premiumRise ? '+' : '') + premium + '%',
        priceText: String(item.price),
        iopvText: item.iopv + ' @ ' + item.iopv_time,
    };
}
function mapItems(items) {
    return items.map(toDisplayItem);
}
// 占位数据：A股ETF套利
const placeholderArbItems = [
    {
        code: '510300',
        name: '沪深300ETF',
        price: 4.238,
        preclose: 4.215,
        open: 4.220,
        high: 4.245,
        low: 4.210,
        change_pct: 0.55,
        iopv: 4.231,
        iopv_time: '14:30',
        premium_rate: 0.17,
        source: 'ph'
    },
    {
        code: '510500',
        name: '中证500ETF',
        price: 6.892,
        preclose: 6.854,
        open: 6.860,
        high: 6.905,
        low: 6.845,
        change_pct: 0.55,
        iopv: 6.881,
        iopv_time: '14:30',
        premium_rate: 0.16,
        source: 'ph'
    },
    {
        code: '159915',
        name: '创业板ETF',
        price: 2.156,
        preclose: 2.142,
        open: 2.145,
        high: 2.165,
        low: 2.138,
        change_pct: 0.65,
        iopv: 2.151,
        iopv_time: '14:30',
        premium_rate: 0.23,
        source: 'ph'
    }
];
Page({
    data: {
        items: [],
        displayUpdatedAt: '--',
        loading: true,
        error: '',
        usingPlaceholder: false,
        isEmpty: false,
    },
    _timer: 0,
    onLoad() {
        this.fetch();
        this._timer = setInterval(() => this.fetch(), 15000);
    },
    onUnload() {
        const t = this._timer;
        if (t)
            clearInterval(t);
    },
    onPullDownRefresh() {
        this.fetch(() => wx.stopPullDownRefresh());
    },
    fetch(cb) {
        // 必须请求 /api/arbitrage
        (0, api_1.request)(api_1.API_PATH.ARBITRAGE, { timeout: 90000 })
            .then((res) => {
            const raw = res.items || [];
            this.setData({
                items: mapItems(raw),
                displayUpdatedAt: res.updated_at || '--',
                loading: false,
                error: '',
                usingPlaceholder: false,
                isEmpty: raw.length === 0,
            });
        })
            .catch(() => {
            this.setData({
                items: mapItems(placeholderArbItems),
                displayUpdatedAt: new Date().toLocaleTimeString('zh-CN'),
                loading: false, // 强制关闭无限转圈！
                usingPlaceholder: true,
                error: ''
            });
        })
            .finally(() => cb && cb());
    },
});
