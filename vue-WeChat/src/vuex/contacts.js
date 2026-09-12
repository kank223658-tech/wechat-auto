/**
 * 联系人数据：已清空旧版硬编码人物（白浅/夜华/刘备/关羽/诸葛亮/孙尚香/孙权/黄月英/甄姬/阿荡）。
 *
 * 现在的数据链路：场景编辑器 scene.json → main.py 注入 window.__wxDefaultScene
 * → enhance/config.js 的 setContacts() 重建 vuex allContacts（每人自动生成
 * 女性 8 位微信号 + 大城市地区）。本文件只保留 vuex 初始结构与 getUserInfo 兜底。
 */
const contacts = []

const contact = {
    contacts
}
contact.getUserInfo = function(wxid) {
    if (!wxid) {
        return;
    } else {
        for (var index in contacts) {
            if (contacts[index].wxid === wxid) {
                return contacts[index]
            }
        }
    }
}

export default contact
