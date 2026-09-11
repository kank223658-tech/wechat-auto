import Vue from 'vue'
import Router from 'vue-router'

import wechat from '../components/wechat/wechat.vue'
import dialogue from '../components/wechat/dialogue.vue'
import addFriend from '../components/contact/add-friend.vue'
import dialogueInfo from '../components/wechat/dialogue-info.vue'
import dialogueDetail from '../components/wechat/dialogue-detail.vue'
import contact from '../components/contact/contact.vue'
import details from '../components/contact/details.vue'
import mobileContacts from '../components/contact/mobile-contacts.vue'
import officialAccounts from '../components/contact/official-accounts.vue'
import groupList from '../components/contact/group-list.vue'
import newFriends from '../components/contact/new-friends.vue'
import tags from '../components/contact/tags.vue'
import explore from '../components/explore/explore.vue'
import moments from '../components/explore/moments.vue'
import self from '../components/self/self.vue'
import album from '../components/common/album.vue'
import selfSettings from '../components/self/settings.vue'
import security from '../components/self/settings/security.vue'
import notice from '../components/self/settings/notice.vue'
import privacy from '../components/self/settings/privacy.vue'
import selfCommon from '../components/self/settings/common.vue'
import profile from '../components/common/profile.vue'
import myQrcode from '../components/self/my-qrcode.vue'
import settings from '../components/settings/settings.vue'
import settingsCommon from '../components/settings/common/common.vue'
import language from '../components/settings/common/language.vue'

Vue.use(Router)
    //app整体由店面页和店内页组成 暂时并没有用到嵌套路由
const routes = [{
        path: '/',
        name: "微信",
        component: wechat
    }, {
        path: '/wechat/dialogue',
        name: "",
        components: {
            "default": wechat,
            "subPage": dialogue
        }
    },
    {
        path: '/wehchat/add-friend',
        name: "",
        components: {
            "default": wechat,
            "subPage": addFriend
        }
    },
    {
        path: '/wechat/dialogue/dialogue-info',
        name: "",
        components: {
            "subPage": dialogueInfo
        }
    },
    {
        path: '/wechat/dialogue/dialogue-detail',
        name: "",
        components: {
            "subPage": dialogueDetail
        }
    },
    {
        path: '/contact',
        name: "通讯录",
        component: contact
    },
    {
        path: '/contact/add-friend',
        name: "",
        components: {
            "default": contact,
            "subPage": addFriend
        }
    },
    {
        path: '/contact/details',
        name: "",
        components: {
            "default": contact,
            "subPage": details
        }
    },
    {
        path: '/contact/new-friends/mobile-contacts',
        name: "通讯录朋友",
        components: {
            "subPage": mobileContacts
        }
    },
    {
        path: '/contact/official-accounts',
        name: "",
        components: {
            "default": contact,
            "subPage": officialAccounts
        }
    },
    {
        path: '/contact/group-list',
        name: "",
        components: {
            "default": contact,
            "subPage": groupList
        }
    },
    {
        path: '/contact/new-friends',
        name: "",
        components: {
            "default": contact,
            "subPage": newFriends
        }
    }, {
        path: '/contact/tags',
        name: "新的朋友",
        components: {
            "default": contact,
            "subPage": tags
        }
    }, {
        path: '/explore',
        name: "发现",
        component: explore
    }, {
        path: '/explore/moments',
        name: "朋友圈",
        components: {
            "default": explore,
            "subPage": moments
        }
    }, {
        path: '/self',
        name: "我",
        component: self
    }, {
        path: '/self/album',
        components: { "default": self, "subPage": album }
    },
    {
        path: '/self/settings',
        components: { "default": self, "subPage": selfSettings }
    }, {
        path: '/self/settings/security',
        components: { "subPage": security }
    },
    {
        path: '/self/settings/notice',
        components: { "subPage": notice }
    },
    {
        path: '/self/settings/privacy',
        components: { "subPage": privacy }
    }, {
        path: '/self/settings/common',
        components: { "subPage": selfCommon }
    }, {
        path: '/self/profile',
        components: { "default": self, "subPage": profile }
    }, {
        path: '/self/profile/my-qrcode',
        components: { "subPage": myQrcode }
    }, {
        path: '/self/settings',
        components: { "subPage": settings }
    },
    {
        path: '/self/settings/common',
        components: {
            "subPage": settingsCommon
        }
    },
    {
        path: '/self/settings/common/language',
        components: {
            "subPage": language
        }
    }

]
export default new Router({
    base: "/vue-wechat/",
    routes,
    // scrollBehavior(to, from, savedPosition) {
    //     if (savedPosition) {
    //         return savedPosition
    //     } else {
    //         return { x: 0, y: 0 }
    //     }
    // }

})