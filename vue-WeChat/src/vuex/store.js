import Vue from 'vue'
import Vuex from 'vuex'
import OfficialAccounts from "./official-account" //存放所有关注的公众号
import contact from './contacts' //存放所有联系人的数据
import mutations from "./mutations"
import actions from "./actions"
import getters from "./getters"
Vue.use(Vuex)
    // 统一管理接口域名 
let apiPublicDomain = '//vrapi.snail.com/'
const state = {
    currentLang: "zh", //当前使用的语言 zh：简体中文 en:英文 后期需要
    newMsgCount: 0, //新消息数量
    allContacts: contact.contacts, //所有联系人
    OfficialAccounts: OfficialAccounts, //所有关注的公众号
    currentPageName: "微信", //用于在wx-header组件中显示当前页标题
    //backPageName: "", //用于在返回按钮出 显示前一页名字 已遗弃
    headerStatus: true, //显示（true）/隐藏（false）wx-header组件
    tipsStatus: false, //控制首页右上角菜单的显示(true)/隐藏(false)
    // 所有接口地址 后期需要
    apiUrl: {
        demo: apiPublicDomain + ""
    },
    msgList: {
        stickMsg: [], //置顶消息列表 后期需要
        baseMsg: [ //普通消息列表
            {
                "mid": 1,
                "type": "friend",
                "group_name": "",
                "read": false,
                "newMsgCount": 9,
                "quiet": false,
                "msg": [{"text": "已支付¥11.65", "date": 1787653320000, "name": "微信支付", "headerUrl": "/images/ref/pay.png"}],
                "user": [{"wxid": "wxid_wxpay", "headerUrl": "/images/ref/pay.png", "nickname": "微信支付", "remark": "微信支付"}]
            },
            {
                "mid": 2,
                "type": "group",
                "group_name": "梓康群",
                "read": false,
                "newMsgCount": 1,
                "quiet": true,
                "msg": [{"text": "下午看得怎么样", "date": 1787652960000, "name": "夜华", "headerUrl": "/images/header/yehua.jpg"}],
                "user": [{"wxid": "wxid_zhaohd", "headerUrl": "/images/header/header01.png", "nickname": "阿荡", "remark": "阿荡"}, {"wxid": "wxid_yehua", "headerUrl": "/images/header/yehua.jpg", "nickname": "夜华", "remark": "夜华"}]
            },
            {
                "mid": 3,
                "type": "friend",
                "group_name": "",
                "read": false,
                "newMsgCount": 1,
                "quiet": false,
                "msg": [{"text": "我也吃饭去了", "date": 1787652960000, "name": "陆香儿", "headerUrl": "/images/ref/luxianger.png"}],
                "user": [{"wxid": "wxid_luxianger", "headerUrl": "/images/ref/luxianger.png", "nickname": "陆香儿", "remark": "陆香儿"}]
            },
            {
                "mid": 4,
                "type": "friend",
                "group_name": "",
                "read": true,
                "newMsgCount": 1,
                "quiet": false,
                "msg": [{"text": "广东联网售票：已上线！全省客运线路实现“一…”", "date": 1787650140000, "name": "服务号", "headerUrl": "/images/ref/fuwu.png"}],
                "user": [{"wxid": "wxid_fuwu", "headerUrl": "/images/ref/fuwu.png", "nickname": "服务号", "remark": "服务号"}]
            },
            {
                "mid": 5,
                "type": "friend",
                "group_name": "",
                "read": true,
                "newMsgCount": 1,
                "quiet": false,
                "msg": [{"text": "快讯：自动驾驶首次被写入法律", "date": 1787626620000, "name": "公众号", "headerUrl": "/images/ref/gongzhong.png"}],
                "user": [{"wxid": "wxid_gzh", "headerUrl": "/images/ref/gongzhong.png", "nickname": "公众号", "remark": "公众号"}]
            },
            {
                "mid": 6,
                "type": "friend",
                "group_name": "",
                "read": true,
                "newMsgCount": 1,
                "quiet": false,
                "msg": [{"text": "登录操作通知", "date": 1787590140000, "name": "微信团队", "headerUrl": "/images/ref/weixin_team.png"}],
                "user": [{"wxid": "wxid_team", "headerUrl": "/images/ref/weixin_team.png", "nickname": "微信团队", "remark": "微信团队"}]
            },
            {
                "mid": 7,
                "type": "friend",
                "group_name": "",
                "read": true,
                "newMsgCount": 1,
                "quiet": false,
                "msg": [{"text": "拍得", "date": 1787673120000, "name": "沉默光环", "headerUrl": "/images/ref/chenmo.png"}],
                "user": [{"wxid": "wxid_chenmo", "headerUrl": "/images/ref/chenmo.png", "nickname": "沉默光环", "remark": "沉默光环"}]
            },
            {
                "mid": 8,
                "type": "friend",
                "group_name": "",
                "read": true,
                "newMsgCount": 1,
                "quiet": false,
                "msg": [{"text": "给 Cursor 的精准开发提示词（复制即用）#任…", "date": 1787668080000, "name": "D", "headerUrl": "/images/ref/D.png"}],
                "user": [{"wxid": "wxid_D", "headerUrl": "/images/ref/D.png", "nickname": "D", "remark": "D"}]
            },
            {
                "mid": 9,
                "type": "friend",
                "group_name": "",
                "read": true,
                "newMsgCount": 1,
                "quiet": false,
                "msg": [{"text": "在吗", "date": 1787659800000, "name": "妍", "headerUrl": "/images/ref/yan.png"}],
                "user": [{"wxid": "wxid_yan", "headerUrl": "/images/ref/yan.png", "nickname": "妍", "remark": "妍"}]
            }
        ]
    }
}
export default new Vuex.Store({
    state,
    mutations,
    actions,
    getters
})