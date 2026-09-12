<template>
<!--个人信息组件（可编辑，保存后写入 scene.json 的 me，脚本每次运行自动读取）-->
    <div class="profile">
        <header id="wx-header">
            <div class="center">
                <router-link to="/self" tag="div" class="iconfont icon-return-arrow">
                    <span>我</span>
                </router-link>
                <span>个人信息</span>
            </div>
        </header>
        <div class="weui-cells">
            <div class="weui-cell weui-cell_access" id="avatarCell" @click="pickerShow = true">
                <div class="weui-cell__bd">
                    <p>头像</p>
                </div>
                <div class="weui-cell__ft">
                    <img :src="form.avatar" data-me-avatar style="width: 50px;height: 50px;border-radius: 4px;">
                    <span class="edit-hint">点击更换</span>
                </div>
            </div>
            <div class="weui-cell">
                <div class="weui-cell__bd">
                    <p>名字</p>
                </div>
                <div class="weui-cell__ft" data-me-name>
                    <input class="cell-input" v-model.trim="form.name" placeholder="填写名字" maxlength="30">
                </div>
            </div>
            <div class="weui-cell">
                <div class="weui-cell__bd">
                    <p>微信号</p>
                </div>
                <div class="weui-cell__ft">
                    <input class="cell-input" v-model.trim="form.wxid" placeholder="填写微信号" maxlength="30">
                </div>
            </div>
            <router-link to="/self/profile/my-qrcode" class="weui-cell weui-cell_access">
                <div class="weui-cell__bd">
                    <p>我的二维码</p>
                </div>
                <div class="weui-cell__ft">
                    <img src="/images/contact_add-friend-my-qr.png" style="vertical-align: middle;;width:24px" class="_align-middle">
                </div>
            </router-link>
            <div class="weui-cell">
                <div class="weui-cell__bd">
                    <p>我的地址</p>
                </div>
                <div class="weui-cell__ft">
                    <input class="cell-input" v-model.trim="form.address" placeholder="填写地址" maxlength="60">
                </div>
            </div>
        </div>

        <div class="weui-cells">
            <div class="weui-cell">
                <div class="weui-cell__bd">
                    <p>性别</p>
                </div>
                <div class="weui-cell__ft">
                    <select class="cell-input" v-model="form.gender">
                        <option value="男">男</option>
                        <option value="女">女</option>
                    </select>
                </div>
            </div>
            <div class="weui-cell">
                <div class="weui-cell__bd">
                    <p>地区</p>
                </div>
                <div class="weui-cell__ft">
                    <input class="cell-input" v-model.trim="form.region" placeholder="如：广东 深圳" maxlength="40">
                </div>
            </div>
            <div class="weui-cell">
                <div class="weui-cell__bd">
                    <p>个性签名</p>
                </div>
                <div class="weui-cell__ft">
                    <input class="cell-input" v-model.trim="form.signature" placeholder="填写个性签名" maxlength="60">
                </div>
            </div>
        </div>

        <div class="weui-cells">
            <div class="weui-cell">
                <div class="weui-cell__bd">
                    <p>LinkedIn帐号</p>
                </div>
                <div class="weui-cell__ft">
                    <input class="cell-input" v-model.trim="form.linkedin" placeholder="未设置" maxlength="60">
                </div>
            </div>
        </div>

        <div class="save-bar">
            <button class="save-btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
        <div class="save-toast" v-if="toast">{{ toast }}</div>

        <!--头像选择：图片库头像分类 + 上传-->
        <div class="picker-mask" v-if="pickerShow" @click.self="pickerShow = false">
            <div class="picker-panel">
                <div class="picker-title">
                    <span>选择头像</span>
                    <span class="picker-close" @click="pickerShow = false">✕</span>
                </div>
                <div class="picker-upload">
                    <button class="upload-btn" :disabled="uploading" @click="pickUpload">
                        {{ uploading ? '上传中…' : '＋ 从手机相册选图上传' }}
                    </button>
                </div>
                <div class="picker-grid" v-if="avatarList.length">
                    <div class="picker-item" :class="{ active: form.avatar === img.path }"
                         v-for="img in avatarList" :key="img.path" @click="chooseAvatar(img.path)">
                        <img :src="img.path">
                    </div>
                </div>
                <div class="picker-empty" v-else>图片库暂无头像，先上传一张吧</div>
            </div>
        </div>

    </div>
</template>
<script>
    const EDITOR_API = (window.__WX_EDITOR_API || "http://localhost:8000").replace(/\/$/, "");

    export default {
        computed: {
            me() {
                const cfg = (window.__wxConfig && window.__wxConfig.get()) || {}
                return cfg.me || { name: '微信用户', avatar: '/images/avatar/2_20260831_184618_874.jpg' }
            }
        },
        data() {
            return {
                pageName: "个人信息",
                form: { name: "", wxid: "", avatar: "", gender: "男", region: "", signature: "", address: "", linkedin: "" },
                saving: false,
                toast: "",
                pickerShow: false,
                uploading: false,
                avatarList: []
            }
        },
        mounted() {
            if (window.__wxConfig) window.__wxConfig.apply()
            this.fillForm()
        },
        methods: {
            fillForm() {
                const me = this.me || {}
                this.form = {
                    name: me.name || "",
                    wxid: me.wxid || "",
                    avatar: me.avatar || "/images/avatar/2_20260831_184618_874.jpg",
                    gender: me.gender || "男",
                    region: me.region || "",
                    signature: me.signature || "",
                    address: me.address || "",
                    linkedin: me.linkedin || ""
                }
            },
            async save() {
                if (this.saving) return
                if (!this.form.name) { this.showToast("名字不能为空"); return }
                this.saving = true
                try {
                    const r = await fetch(EDITOR_API + "/api/me", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ me: this.form })
                    })
                    const d = await r.json().catch(() => ({}))
                    if (!r.ok || d.ok === false) throw new Error(d.msg || ("HTTP " + r.status))
                    // 同步到运行时配置，界面立即生效
                    if (window.__wxConfig && window.__wxConfig.setMe) {
                        window.__wxConfig.setMe(Object.assign({}, this.form))
                        window.__wxConfig.apply()
                    }
                    this.showToast("已保存，脚本运行时会自动使用")
                } catch (e) {
                    this.showToast("保存失败：" + e.message)
                } finally {
                    this.saving = false
                }
            },
            async openPicker() {
                this.pickerShow = true
                try {
                    const r = await fetch(EDITOR_API + "/api/gallery", { headers: { "Accept": "application/json" } })
                    const d = await r.json()
                    // 只取图片库「头像」分类（avatar 目录）下的图
                    const files = (d.files || []).filter(f => f.folder === "avatar")
                    this.avatarList = files.map(f => ({ path: f.path, name: f.label || f.name }))
                } catch (e) {
                    this.avatarList = []
                }
            },
            chooseAvatar(path) {
                this.form.avatar = path
                this.pickerShow = false
            },
            pickUpload() {
                const input = document.createElement("input")
                input.type = "file"
                input.accept = "image/*"
                input.onchange = async () => {
                    const file = input.files && input.files[0]
                    if (!file) return
                    this.uploading = true
                    try {
                        const dataUrl = await new Promise((resolve, reject) => {
                            const fr = new FileReader()
                            fr.onload = () => resolve(fr.result)
                            fr.onerror = () => reject(new Error("读取文件失败"))
                            fr.readAsDataURL(file)
                        })
                        const r = await fetch(EDITOR_API + "/api/upload-image", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ data: dataUrl, name: file.name, category: "avatar" })
                        })
                        const d = await r.json().catch(() => ({}))
                        if (!r.ok || d.ok === false) throw new Error(d.msg || ("HTTP " + r.status))
                        this.form.avatar = d.path
                        this.pickerShow = false
                        this.showToast("头像已上传，点「保存」生效")
                    } catch (e) {
                        this.showToast("上传失败：" + e.message)
                    } finally {
                        this.uploading = false
                    }
                }
                input.click()
            },
            showToast(msg) {
                this.toast = msg
                clearTimeout(this._toastTimer)
                this._toastTimer = setTimeout(() => { this.toast = "" }, 2600)
            }
        },
        watch: {
            pickerShow(v) { if (v) this.openPicker() }
        }
    }
</script>
<style scoped>
    .cell-input {
        border: none;
        outline: none;
        background: transparent;
        text-align: right;
        font-size: 15px;
        color: #333;
        max-width: 220px;
    }
    .edit-hint {
        margin-left: 6px;
        font-size: 12px;
        color: #b2b2b2;
    }
    .save-bar {
        position: fixed;
        left: 0;
        right: 0;
        bottom: 0;
        padding: 10px 16px calc(10px + constant(safe-area-inset-bottom)) 16px;
        padding-bottom: calc(10px + env(safe-area-inset-bottom));
        background: #f7f7f7;
        border-top: 1px solid #e5e5e5;
        z-index: 30;
    }
    .save-btn {
        width: 100%;
        height: 42px;
        border: none;
        border-radius: 6px;
        background: #07c160;
        color: #fff;
        font-size: 16px;
    }
    .save-btn:disabled { opacity: .6; }
    .save-toast {
        position: fixed;
        left: 50%;
        bottom: 80px;
        transform: translateX(-50%);
        background: rgba(0, 0, 0, .75);
        color: #fff;
        font-size: 13px;
        padding: 8px 14px;
        border-radius: 6px;
        z-index: 40;
        max-width: 80%;
        text-align: center;
    }
    .picker-mask {
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, .45);
        z-index: 50;
        display: flex;
        align-items: flex-end;
    }
    .picker-panel {
        width: 100%;
        background: #fff;
        border-radius: 12px 12px 0 0;
        padding: 14px;
        max-height: 65vh;
        display: flex;
        flex-direction: column;
    }
    .picker-title {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 16px;
        color: #333;
        margin-bottom: 10px;
    }
    .picker-close { color: #b2b2b2; font-size: 16px; padding: 2px 6px; }
    .picker-upload { margin-bottom: 10px; }
    .upload-btn {
        width: 100%;
        height: 38px;
        border: 1px dashed #bbb;
        border-radius: 6px;
        background: #fafafa;
        color: #576b95;
        font-size: 14px;
    }
    .picker-grid {
        overflow-y: auto;
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        padding-bottom: 10px;
    }
    .picker-item {
        aspect-ratio: 1;
        border-radius: 6px;
        overflow: hidden;
        border: 2px solid transparent;
    }
    .picker-item.active { border-color: #07c160; }
    .picker-item img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .picker-empty { color: #b2b2b2; font-size: 13px; text-align: center; padding: 24px 0; }
</style>
