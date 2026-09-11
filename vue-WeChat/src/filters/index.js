const filters = {
    /**
     * 功能：将时间戳按照给定的 时间/日期 格式进行处理
     * @param {Number} date 时间戳
     * @param {String} fmtExp 时间格式 'hh:mm'
     * @returns {String} 规范后的 时间/日期 字符串
     *
     * 首页会话列表用 'hh:mm'，按微信真实逻辑显示相对时间：
     *   今天        →  HH:MM
     *   昨天        →  "昨天 HH:MM"
     *   2~6 天前    →  "星期X"
     *   更早        →  "M月d日"
     * 其它 fmtExp（如 'yyyy-MM-dd'）仍走原通用格式化。
     */
    fmtDate: function (date, fmtExp) {
        const fmt = String(fmtExp || 'hh:mm');
        // 非列表时间格式：走原通用解析
        if (fmt !== 'hh:mm') {
            return filters._generic(date, fmt);
        }
        const d = new Date(date);
        if (!isFinite(d.getTime())) return '';
        const now = new Date();
        const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
        const startOfMsg = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
        const dayDiff = Math.round((startOfToday - startOfMsg) / 86400000);
        const pad = (n) => String(n).padStart(2, '0');
        const hm = pad(d.getHours()) + ':' + pad(d.getMinutes());
        const weekNames = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
        if (dayDiff <= 0) return hm;                    // 今天（含未来，直接显示时刻）
        if (dayDiff === 1) return '昨天 ' + hm;          // 昨天
        if (dayDiff < 7) return weekNames[d.getDay()];   // 一周内显示星期
        return (d.getMonth() + 1) + '月' + d.getDate() + '日';
    },

    /* 通用格式化（原逻辑） */
    _generic: function (date, fmtExp) {
        date = new Date(date);
        var o = {
            "M+": date.getMonth() + 1, //月份
            "d+": date.getDate(), //日
            "h+": date.getHours(), //小时
            "m+": date.getMinutes(), //分
            "s+": date.getSeconds(), //秒
            "q+": Math.floor((date.getMonth() + 3) / 3), //季度
            "S": date.getMilliseconds() //毫秒
        };
        if (/(y+)/.test(fmtExp))
            fmtExp = fmtExp.replace(RegExp.$1, (date.getFullYear() + "").substr(4 - RegExp.$1.length));
        for (var k in o)
            if (new RegExp("(" + k + ")").test(fmtExp))
                fmtExp = fmtExp.replace(RegExp.$1, (RegExp.$1.length == 1) ? (o[k]) : (("00" + o[k]).substr(("" + o[k]).length)));
        return fmtExp;
    }
}
export default (Vue) => {
    Object.keys(filters).forEach(key => {
        Vue.filter(key, filters[key])
    })
}
