# -*- coding: utf-8 -*-
"""探针：[发送图片] 新流程 —— 弹「+」面板 → 点「照片」→ 预览页 → 自动发送。
一次性验证实例（8080 dev server，自建浏览器，不碰 8001 渲染器），只读页面状态。
判定：
  A1  __wxPanels.set('attach') 后加号面板 open + body.wxp-open
  A2  「照片」瓦片 .tap 期间图标块变 #3d3d3d，摘除后回 #272727
  A3  selfImage 后：预览页 sip-open、面板已收起；~1.7s 后预览关闭 + 图片气泡 +1
  B   键盘开着 → 直切 attach → 再发一张，气泡 +1（键盘→面板直切路径）
"""
import json
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/"
ENH = r"G:/weixin-auto/enhance/"

CSS_BASE = ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
            "wechat_modern.css", "human_actions.css", "transfer_ui.css", "transfer_detail.css",
            "send_image_ui.css", "peer_pages.css", "block_ui.css", "video_player.css",
            "homepage_exact.css"]
JS_ORDER = ["config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
            "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "transfer_detail.js",
            "send_image_ui.js", "video_player.js", "peer_pages.js", "block_ui.js", "homepage.js"]
CSS_POST = ["chat_exact.css", "panel_switch.css", "wx_icons.css", "moments_exact.css",
            "discover_exact.css"]

def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()

FLOW_JS = r"""
() => new Promise(async (resolve) => {
  const P = window.__wxPanels, X = window.__wxChatExt;
  if (!P || !X) { resolve({error: 'no __wxPanels/__wxChatExt'}); return; }
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const countImg = () => document.querySelectorAll('.dialogue-section .text.msg-image').length;
  const out = {};
  out.img0 = countImg();

  // A1: 打开「+」功能面板
  out.setAttach = P.set('attach');
  await sleep(900);
  out.A1_panelOpen = document.getElementById('wxTransferPanel').classList.contains('open');
  out.A1_bodyWxp = document.body.classList.contains('wxp-open');

  // A2: 点「照片」瓦片按压反馈
  const tile = document.querySelector('#wxTransferPanel .tp-item[data-id="photo"]');
  if (!tile) { resolve({error: 'no photo tile'}); return; }
  tile.classList.add('tap');
  out.A2_iconBgTap = getComputedStyle(tile.querySelector('.tp-icon')).backgroundColor;
  await sleep(250);
  tile.classList.remove('tap');
  out.A2_iconBgRest = getComputedStyle(tile.querySelector('.tp-icon')).backgroundColor;

  // A3: selfImage → 收面板 + 预览页打开 → 自动发送
  out.A3_ret = X.selfImage('/images/chat/sticker1.png');
  await sleep(120);
  const sip = document.getElementById('sendImagePreview');
  out.A3_sipOpen = sip.classList.contains('sip-open');
  out.A3_panelClosed = !document.body.classList.contains('wxp-open');
  await sleep(1700);
  out.A3_sipClosedAfter = !sip.classList.contains('sip-open');
  out.img1 = countImg();

  // B: 键盘开着 → 直切 attach → 再发一张
  P.set('kb');
  await sleep(500);
  out.B_kbOpen = document.body.classList.contains('wxkb-open');
  out.B_setAttach = P.set('attach');
  await sleep(900);
  out.B_panelOpen = document.getElementById('wxTransferPanel').classList.contains('open');
  out.B_kbClosed = !document.body.classList.contains('wxkb-open');
  out.B_ret = X.selfImage('/images/chat/sticker1.png');
  await sleep(1800);
  out.B_sipClosedAfter = !sip.classList.contains('sip-open');
  out.img2 = countImg();
  resolve(out);
})
"""

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 620, "height": 1340})
    pg.goto(URL, wait_until="domcontentloaded")
    pg.evaluate("document.querySelector('.welcome') && (document.querySelector('.welcome').style.display='none')")
    for n in CSS_BASE:
        pg.add_style_tag(content=read(ENH + n))
    pg.evaluate("window.__wxDefaultScene = %s" % read(r"G:/weixin-auto/scene.json"))
    for n in JS_ORDER:
        pg.add_script_tag(content=read(ENH + n))
    for n in CSS_POST:
        pg.add_style_tag(content=read(ENH + n))
    pg.wait_for_function("!!window.__wxChatExt && !!window.__wxTransfer", timeout=30000)
    pg.add_script_tag(content=read(ENH + "panel_switch.js"))
    pg.wait_for_function("!!window.__wxPanels", timeout=10000)
    pg.evaluate("window.__wxConfig.applyScene(window.__wxDefaultScene)")
    pg.evaluate("location.hash = '#/wechat/dialogue'")
    pg.wait_for_selector(".dialogue-section", timeout=15000)
    pg.wait_for_timeout(1500)
    pg.evaluate("""
      () => {
        const cells = document.querySelectorAll('#wechat .wechat-list .weui-cell');
        if (cells.length) { cells[0].click(); return 'clicked'; }
        return 'no-cell';
      }
    """)
    pg.wait_for_selector(".dialogue-section", timeout=15000)
    pg.wait_for_timeout(600)
    out = pg.evaluate(FLOW_JS)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    b.close()
