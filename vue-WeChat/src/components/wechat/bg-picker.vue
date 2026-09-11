<template>
    <div class="bg-picker-mask" v-if="show" v-on:click.self="$emit('close')">
        <div class="bg-picker">
            <header class="bg-picker-header">
                <span class="back iconfont icon-return-arrow" v-on:click="$emit('close')"></span>
                <span class="title">设置当前聊天背景</span>
            </header>

            <!-- 背景列表 -->
            <div class="bg-list" v-if="images.length">
                <div class="bg-cell" v-for="img in images" :key="img"
                     :class="{ active: img === selected }"
                     v-on:click="pick(img)">
                    <img :src="img" :alt="img">
                    <span class="check" v-if="img === selected">✓</span>
                </div>
            </div>
            <div class="bg-empty" v-else>还没有背景图片，点右上角上传一张。</div>

            <!-- 操作区 -->
            <footer class="bg-footer">
                <button class="reset" v-on:click="pick('')">默认深色</button>
                <label class="upload-btn">
                    <input type="file" accept="image/*" v-on:change="onFile">
                    上传背景
                </label>
            </footer>

            <div class="bg-tip" v-if="loading">{{ loadingText }}</div>
        </div>
    </div>
</template>
<script>
    /* ============================================================
       聊天背景挑选/上传面板
       ------------------------------------------------------------
       - 从编辑器服务(editor_server)的 /api/chat-bgs 列出 public/images/bg 下的背景；
       - 上传通过该服务的 /api/upload-bg（base64）存入同一目录；
       - 选择后把背景写入 --wx-chat-bg（深色蒙层），聊天页 .dialogue-section 立即生效；
         兼容 main.py 注入的 window.__wxConfig（此时一并持久化，供录屏使用）。
       编辑器服务地址默认 http://localhost:8000，可用 window.__WX_EDITOR_API 覆盖。
       ============================================================ */
    export default {
        name: "BgPicker",
        props: {
            show: { type: Boolean, default: false }
        },
        data() {
            return {
                images: [],
                selected: "",
                loading: false,
                loadingText: "",
                editorApi: (window.__WX_EDITOR_API || "http://localhost:8000").replace(/\/$/, "")
            }
        },
        watch: {
            show(v) { if (v) this.load(); }
        },
        mounted() {
            if (this.show) this.load();
            // 读取启动时(可能已由 main.py 设置的)背景，用于高亮当前选中项
            this.selected = this.currentBg();
        },
        methods: {
            /* 当前生效的背景（URL） */
            currentBg() {
                try {
                    if (window.__wxConfig && window.__wxConfig.getChatBg) return window.__wxConfig.getChatBg() || "";
                } catch (e) { /* 忽略 */ }
                return "";
            },
            /* 把背景写入 --wx-chat-bg；空串 = 默认深色 */
            applyChatBg(bg) {
                bg = (bg || "").trim();
                const value = bg
                    ? "linear-gradient(rgba(16,16,16,.82), rgba(16,16,16,.82)), url('" + bg + "') center / cover no-repeat #101010"
                    : "#101010";
                const root = document.documentElement;
                if (value === "#101010") root.style.removeProperty("--wx-chat-bg");
                else root.style.setProperty("--wx-chat-bg", value);
                try {
                    if (window.__wxConfig && window.__wxConfig.setChatBg) window.__wxConfig.setChatBg(bg);
                } catch (e) { /* 忽略 */ }
                this.selected = bg;
            },
            /* 从编辑器服务拉取背景列表 */
            async load() {
                this.images = [];
                this.loading = true;
                this.loadingText = "正在加载背景…";
                try {
                    const r = await fetch(this.editorApi + "/api/chat-bgs", { headers: { "Accept": "application/json" } });
                    if (!r.ok) throw new Error("HTTP " + r.status);
                    const d = await r.json();
                    this.images = (d.images || []).slice();
                    this.loading = false;
                } catch (e) {
                    this.images = [];
                    this.loading = false;
                    this.loadingText = "无法连接编辑器(请先运行 editor_server.py)，当前无背景可列。";
                }
            },
            /* 选择某张背景（空串 = 恢复默认深色） */
            pick(bg) {
                this.applyChatBg(bg);
            },
            /* 上传：读文件→base64→POST 到编辑器 /api/upload-bg */
            async onFile(ev) {
                const file = ev.target.files && ev.target.files[0];
                ev.target.value = "";
                if (!file) return;
                if (!/^image\//.test(file.type || "")) { this.loadingText = "仅支持图片文件"; return; }
                const reader = new FileReader();
                reader.onload = async () => {
                    this.loading = true;
                    this.loadingText = "正在上传…";
                    try {
                        const r = await fetch(this.editorApi + "/api/upload-bg", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ data: reader.result, name: file.name })
                        });
                        const d = await r.json();
                        if (!r.ok || !d.ok) throw new Error(d.msg || ("HTTP " + r.status));
                        this.images = (d.images || []).slice();
                        this.applyChatBg(d.path);   // 上传后直接选中并预览
                        this.loading = false;
                    } catch (e) {
                        this.loading = false;
                        this.loadingText = "上传失败：" + e.message;
                    }
                };
                reader.readAsDataURL(file);
            }
        }
    }
</script>
<style scoped>
    .bg-picker-mask {
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, .55);
        z-index: 99999;
        display: flex;
        align-items: flex-end;
        justify-content: center;
    }
    .bg-picker {
        width: 100%;
        background: #fdfdfd;
        border-radius: 14px 14px 0 0;
        padding-bottom: 20px;
        color: #464646;
        font-size: 14px;
    }
    .bg-picker-header {
        display: flex;
        align-items: center;
        height: 56px;
        padding: 0 14px;
        border-bottom: 1px solid #ededed;
    }
    .bg-picker-header .back { font-size: 22px; color: #576b95; margin-right: 12px; }
    .bg-picker-header .title { font-size: 16px; font-weight: 500; }
    .bg-list {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        padding: 16px 14px;
        max-height: 46vh;
        overflow: auto;
    }
    .bg-cell {
        position: relative;
        width: 104px;
        height: 104px;
        border-radius: 8px;
        overflow: hidden;
        border: 2px solid transparent;
        cursor: pointer;
        background: #111;
    }
    .bg-cell img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .bg-cell.active { border-color: #23ba65; }
    .bg-cell .check {
        position: absolute;
        right: 6px;
        bottom: 6px;
        width: 20px;
        height: 20px;
        line-height: 20px;
        text-align: center;
        border-radius: 50%;
        background: #23ba65;
        color: #fff;
        font-size: 13px;
    }
    .bg-empty { padding: 28px 14px; color: #9a9a9a; text-align: center; }
    .bg-footer {
        display: flex;
        gap: 14px;
        padding: 0 14px;
        margin-top: 6px;
    }
    .bg-footer button,
    .bg-footer .upload-btn {
        flex: 1;
        height: 44px;
        line-height: 44px;
        text-align: center;
        border-radius: 8px;
        font-size: 15px;
        cursor: pointer;
        border: 1px solid #dcdcdc;
        background: #fff;
        color: #464646;
        box-sizing: border-box;
    }
    .bg-footer .upload-btn { background: #e9f5ff; color: #576b95; border-color: #bcd8f5; }
    .bg-footer .upload-btn input { display: none; }
    .bg-tip { padding: 10px 14px; color: #9a9a9a; text-align: center; }
</style>