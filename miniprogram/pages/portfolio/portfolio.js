"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
// portfolio.ts
// 核心资产监控：美股持仓 + 加密合约
const api_1 = require("../../utils/api");
/** 拒绝串线：portfolio 绝不能收到 arbitrage / news 的响应 */
function assertPortfolioResponse(res) {
    const cat = res.category || '';
    if (cat.includes('套利') || cat.includes('资讯')) {
        throw new Error('URL串线: portfolio 页面收到了 ' + cat + ' 的数据，应为 /api/portfolio');
    }
}
function toNumber(val) {
    if (val == null || val === '' || val === '-')
        return null;
    const n = Number(val);
    return Number.isFinite(n) ? n : null;
}
function normalizeUsStock(raw) {
    return {
        symbol: String(raw.symbol || ''),
        cn_name: String(raw.cn_name || raw.cnName || ''),
        name: String(raw.name || ''),
        price: toNumber(raw.price),
        preclose: toNumber(raw.preclose),
        change_pct: toNumber(raw.change_pct || raw.changePct),
        source: String(raw.source || 'unknown'),
    };
}
function normalizeCryptoPerp(raw) {
    return {
        symbol: String(raw.symbol || 'SOLUSDT-PERP'),
        price: toNumber(raw.price),
        change_pct_24h: toNumber(raw.change_pct_24h || raw.changePct24h),
        high_24h: toNumber(raw.high_24h || raw.high24h),
        low_24h: toNumber(raw.low_24h || raw.low24h),
        quote_volume_24h: toNumber(raw.quote_volume_24h || raw.quoteVolume24h),
        source: String(raw.source || 'unknown'),
    };
}
/** 兼容 FastAPI 直出 JSON，以及可能的 data 包裹层 */
function extractPortfolioPayload(res) {
    const root = res && typeof res === 'object' && res.data && typeof res.data === 'object'
        ? res.data
        : (res || {});
    const stocksRaw = root.us_stocks || root.usStocks;
    const usStocks = Array.isArray(stocksRaw)
        ? stocksRaw.map((item) => normalizeUsStock(item))
        : [];
    const perpRaw = root.crypto_perp || root.cryptoPerp;
    const cryptoPerp = perpRaw && typeof perpRaw === 'object'
        ? normalizeCryptoPerp(perpRaw)
        : normalizeCryptoPerp({});
    const updatedAt = String(root.updated_at || root.updatedAt || '--:--:--');
    return { usStocks, cryptoPerp, updatedAt };
}
function isLiveSource(source) {
    return source === 'live';
}
function formatPrice(price, prefix) {
    if (price == null)
        return prefix + '--';
    return prefix + price;
}
function toUsStockDisplay(item) {
    const rise = (item.change_pct || 0) >= 0;
    const live = isLiveSource(item.source);
    const pct = item.change_pct || 0;
    return {
        ...item,
        cardCls: rise ? 'card stock-card card-rise' : 'card stock-card card-fall',
        badgeCls: live ? 'source-badge source-badge-live' : 'source-badge source-badge-demo',
        badgeText: live ? 'LIVE' : 'DEMO',
        changeCls: rise ? 'change-block rise' : 'change-block fall',
        changeText: (rise ? '+' : '') + pct + '%',
        priceText: formatPrice(item.price, '$'),
    };
}
function toCryptoDisplay(item) {
    const rise = (item.change_pct_24h || 0) >= 0;
    const live = isLiveSource(item.source);
    const pct = item.change_pct_24h || 0;
    return {
        symbol: item.symbol || 'SOLUSDT-PERP',
        cardCls: rise ? 'card crypto-card card-rise' : 'card crypto-card card-fall',
        badgeCls: live ? 'source-badge source-badge-live' : 'source-badge source-badge-demo',
        badgeText: live ? 'LIVE' : 'DEMO',
        changeCls: rise ? 'change-block change-block-lg rise' : 'change-block change-block-lg fall',
        changeText: (rise ? '+' : '') + pct + '%',
        priceText: formatPrice(item.price, '$'),
        highText: formatPrice(item.high_24h, '$'),
        lowText: formatPrice(item.low_24h, '$'),
        volumeText: item.quote_volume_24h != null ? String(item.quote_volume_24h) : '--',
    };
}
function mapUsStocks(items) {
    if (!Array.isArray(items))
        return [];
    return items.map(toUsStockDisplay);
}
// 仅在网络完全失败时使用的前端占位
const placeholderUsStocks = [
    {
        symbol: 'AAPL',
        cn_name: '苹果',
        name: 'Apple Inc.',
        price: 198.23,
        preclose: 195.89,
        change_pct: 1.19,
        source: 'ph',
    },
    {
        symbol: 'TSLA',
        cn_name: '特斯拉',
        name: 'Tesla Inc.',
        price: 248.5,
        preclose: 258.45,
        change_pct: -3.86,
        source: 'ph',
    },
];
const placeholderCryptoPerp = {
    symbol: 'BTCUSDT',
    price: 43250.5,
    change_pct_24h: 2.34,
    high_24h: 44580.0,
    low_24h: 42100.25,
    quote_volume_24h: 285.6,
    source: 'ph',
};
Page({
    data: {
        usStocks: [],
        cryptoPerp: {},
        displayUpdatedAt: '--:--:--',
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
    applyPortfolioData(usStocks, cryptoPerp, updatedAt) {
        this.setData({
            usStocks: mapUsStocks(usStocks),
            cryptoPerp: toCryptoDisplay(cryptoPerp),
            displayUpdatedAt: updatedAt,
            loading: false,
            error: '',
            usingPlaceholder: false,
            isEmpty: usStocks.length === 0,
        });
    },
    applyPlaceholder() {
        this.setData({
            usStocks: mapUsStocks(placeholderUsStocks),
            cryptoPerp: toCryptoDisplay(placeholderCryptoPerp),
            displayUpdatedAt: new Date().toLocaleTimeString('zh-CN'),
            loading: false,
            error: '',
            usingPlaceholder: true,
            isEmpty: false,
        });
    },
    fetch(cb) {
        // 必须请求 /api/portfolio，禁止调用 arbitrage 接口
        (0, api_1.request)(api_1.API_PATH.PORTFOLIO, { timeout: 180000 })
            .then((res) => {
            console.log('portfolio 解析前:', res);
            try {
                assertPortfolioResponse(res);
                const { usStocks, cryptoPerp, updatedAt } = extractPortfolioPayload(res);
                console.log('portfolio 映射结果:', { usStocks, cryptoPerp, updatedAt });
                this.applyPortfolioData(usStocks, cryptoPerp, updatedAt);
            }
            catch (err) {
                console.error('portfolio 数据映射异常:', err, res);
                this.applyPlaceholder();
            }
        })
            .catch((err) => {
            console.error('portfolio 请求失败:', err);
            this.applyPlaceholder();
        })
            .finally(() => cb && cb());
    },
});
