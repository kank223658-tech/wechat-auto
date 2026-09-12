# -*- coding: utf-8 -*-
"""付款面板几何诊断：导出面板/密码格/键盘各行的 boundingRect（600x1300 空间），
便于与参考视频实测行带 y 值逐条对齐。"""
import os
from playwright.sync_api import sync_playwright

ENH = r"G:\weixin-auto\enhance"
def rd(p): return open(p, encoding="utf-8").read()

JS = """
() => {
  const out = [];
  const q = (sel) => document.querySelector(sel);
  const r = (el) => { if(!el) return null; const b = el.getBoundingClientRect();
      return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)]; };
  const pairs = [
    ['#wxPaySheet', q('#wxPaySheet')],
    ['.pay-sheet', q('#wxPaySheet .pay-sheet') || q('.pay-sheet')],
    ['.pay-sheet-header', q('.pay-sheet-header')],
    ['.ps-title', q('.ps-title')],
    ['.ps-amount', q('.ps-amount')],
    ['.pay-boxes', q('.pay-boxes')],
    ['#pwKeyboard', q('#pwKeyboard')],
  ];
  for (const [n, el] of pairs) out.push([n, r(el)]);
  const keys = document.querySelectorAll('#pwKeyboard .tkr-key');
  out.push(['keyCount', keys.length]);
  let i = 0;
  const seen = new Set();
  keys.forEach(k => {
    const b = k.getBoundingClientRect();
    const row = Math.round(b.y);
    if (!seen.has(row)) { seen.add(row); out.push(['row#' + (i++) + ' y' + row, r(k)]); }
  });
  // 面板内所有直接子节点的 y
  const sheet = q('#wxPaySheet .pay-sheet') || q('.pay-sheet');
  if (sheet) { [...sheet.children].forEach((c, idx) => out.push(['child' + idx + ':' + c.className, r(c)])); }
  return out;
}
"""

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 600, "height": 1300})
    pg.goto("http://localhost:8080/#/", wait_until="domcontentloaded")
    pg.wait_for_timeout(1200)
    pg.add_style_tag(content=".welcome { display: none !important; }")
    for f in ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
              "wechat_modern.css", "human_actions.css", "transfer_ui.css", "send_image_ui.css",
              "peer_pages.css", "block_ui.css", "video_player.css", "homepage_exact.css"]:
        pg.add_style_tag(content=rd(ENH + "\\" + f))
    for f in ["config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
              "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "send_image_ui.js",
              "video_player.js", "peer_pages.js", "block_ui.js"]:
        pg.evaluate(rd(ENH + "\\" + f))
    pg.evaluate(rd(ENH + "\\keyboard.js"))
    pg.wait_for_timeout(400)
    pg.evaluate("window.__wxTransfer.openAmount('小星')")
    pg.wait_for_timeout(600)
    for k in ["1", ".", "0", "0"]:
        pg.evaluate("(d)=>{const k=document.querySelector('#taKeyboard .tkr-key[data-key=\"'+d+'\"]'); if(k) k.click();}", k)
        pg.wait_for_timeout(100)
    pg.evaluate("()=>{const k=document.querySelector('#taKeyboard .tkr-ok'); if(k) k.click();}")
    pg.wait_for_timeout(3200)
    for row in pg.evaluate(JS):
        print("  ", row)
    b.close()
