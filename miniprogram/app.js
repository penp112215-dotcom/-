"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
// app.ts
const config_1 = require("./utils/config");
App({
    globalData: {},
    onLaunch() {
        if ((0, config_1.shouldUseCloudBase)()) {
            if (!config_1.CLOUDBASE_ENV_ID) {
                console.error('[CloudBase] 尚未配置环境 ID');
            }
            else if (wx.cloud) {
                wx.cloud.init({
                    env: config_1.CLOUDBASE_ENV_ID,
                    traceUser: true,
                });
            }
            else {
                console.error('[CloudBase] 当前微信基础库不支持 wx.cloud');
            }
        }
        // 展示本地存储能力
        const logs = wx.getStorageSync('logs') || [];
        logs.unshift(Date.now());
        wx.setStorageSync('logs', logs);
        // 登录
        wx.login({
            success: res => {
                console.log(res.code);
                // 发送 res.code 到后台换取 openId, sessionKey, unionId
            },
        });
    },
});
