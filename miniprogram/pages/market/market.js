"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const api_1 = require("../../utils/api");
function numberOf(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}
function priceText(value) {
    const number = numberOf(value);
    if (number == null)
        return '$--';
    const digits = number >= 1000 ? 0 : number >= 10 ? 2 : 3;
    return '$' + number.toLocaleString('en-US', { maximumFractionDigits: digits });
}
function toAsset(raw) {
    const change = numberOf(raw.change_pct_24h) || 0;
    const rise = change >= 0;
    return {
        symbol: String(raw.symbol || '--').replace('USDT', ''),
        name: String(raw.name || ''),
        priceText: priceText(raw.price),
        changeText: (rise ? '+' : '') + change.toFixed(2) + '%',
        changeCls: rise ? 'crypto-change rise' : 'crypto-change fall',
        rangeText: `${priceText(raw.low_24h)} — ${priceText(raw.high_24h)}`,
        sourceText: raw.source === 'live' ? '实时行情' : '缓存参考',
    };
}
function toComponents(items) {
    return items.map((item) => ({
        key: String(item.key || item.name),
        name: String(item.name || '--'),
        display: String(item.display || '--'),
        note: String(item.note || ''),
        barStyle: `width: ${Math.max(0, Math.min(100, Number(item.value || 0)))}%;`,
    }));
}
function toSectors(items) {
    return items.map((item) => ({
        ...item,
        indexText: item.index == null ? '--' : Number(item.index).toFixed(1),
        buyText: item.buy == null ? '--' : Number(item.buy).toFixed(1),
        sellText: item.sell == null ? '--' : Number(item.sell).toFixed(1),
    }));
}
Page({
    data: {
        loading: true,
        error: '',
        updatedAt: '--',
        hasAShare: false,
        aScore: '--',
        aLabel: '数据同步中',
        aSummary: '',
        aMethod: '',
        aSample: 0,
        aScoreStyle: 'width: 0%;',
        components: [],
        hasRetail: false,
        retailIndex: '--',
        retailLabel: '--',
        retailBuy: '--',
        retailSell: '--',
        retailSample: 0,
        retailMethod: '',
        sectors: [],
        cryptoFear: '--',
        cryptoLabel: '--',
        cryptoRisk: '--',
        cryptoSource: '数据同步中',
        assets: [],
        showCryptoEmpty: false,
    },
    _refreshTimer: 0,
    onLoad() { this.fetch(); },
    onShow() {
        const oldTimer = this._refreshTimer;
        if (oldTimer)
            clearInterval(oldTimer);
        this._refreshTimer = setInterval(() => this.fetch(undefined, true), 60000);
    },
    onHide() { this.stopRefresh(); },
    onUnload() { this.stopRefresh(); },
    onPullDownRefresh() { this.fetch(() => wx.stopPullDownRefresh()); },
    stopRefresh() {
        const timer = this._refreshTimer;
        if (timer)
            clearInterval(timer);
        this._refreshTimer = 0;
    },
    fetch(done, silent = false) {
        if (!silent)
            this.setData({ loading: true, error: '', showCryptoEmpty: false });
        (0, api_1.request)(api_1.API_PATH.MARKET, { timeout: 60000 })
            .then((res) => {
            const aShare = res.a_share_sentiment || {};
            const retail = res.retail_sentiment || {};
            const fear = res.fear_greed || {};
            const assets = Array.isArray(res.crypto_assets) ? res.crypto_assets.map(toAsset) : [];
            const score = numberOf(aShare.score);
            this.setData({
                updatedAt: res.updated_at || '--',
                hasAShare: Boolean(aShare.available),
                aScore: score == null ? '--' : score.toFixed(1),
                aLabel: aShare.label || '数据不足',
                aSummary: aShare.summary || '客观数据不足，暂不生成情绪结论。',
                aMethod: aShare.method || '',
                aSample: Number(aShare.sample_size || 0),
                aScoreStyle: `width: ${score == null ? 0 : Math.max(0, Math.min(100, score))}%;`,
                components: toComponents(aShare.components || []),
                hasRetail: Boolean(retail.available),
                retailIndex: retail.index == null ? '--' : Number(retail.index).toFixed(1),
                retailLabel: retail.label || '无数据',
                retailBuy: retail.buy == null ? '--' : Number(retail.buy).toFixed(1),
                retailSell: retail.sell == null ? '--' : Number(retail.sell).toFixed(1),
                retailSample: Number(retail.sample_size || 0),
                retailMethod: retail.method || '',
                sectors: toSectors(retail.sectors || []),
                cryptoFear: fear.value == null ? '--' : String(fear.value),
                cryptoLabel: fear.classification || '--',
                cryptoRisk: res.risk_level || '--',
                cryptoSource: fear.source === 'live' ? '实时数据' : '缓存参考',
                assets,
                showCryptoEmpty: assets.length === 0,
                loading: false,
            });
        })
            .catch((error) => {
            console.error('[市场情绪失败]', error);
            if (!silent) {
                this.setData({ loading: false, error: '无法连接市场情绪服务，请下拉重试', showCryptoEmpty: true });
            }
        })
            .finally(() => done && done());
    },
});
