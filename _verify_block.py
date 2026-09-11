# -*- coding: utf-8 -*-
"""拉黑功能验证脚本：打开前端，注入增强层，逐步执行拉黑动画并截图。
产物落在 _block_verify/ 目录，对照参考视频帧核对。"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main as _wx  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_block_verify")
os.makedirs(OUT, exist_ok=True)


def shot(page, name):
    page.screenshot(path=os.path.join(OUT, name))
    print("shot:", name)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": _wx.VIEWPORT_W, "height": _wx.VIEWPORT_H},
            device_scale_factor=2,
            user_agent=_wx.MOBILE_UA,
            is_mobile=True,
            has_touch=True,
            locale="zh-CN",
        )
        page = ctx.new_page()
        page.goto(_wx.BASE_URL, wait_until="domcontentloaded")
        _wx.inject_overlays(page)
        page.wait_for_timeout(2200)

        # 1. 对方资料页（右上角 … 是设置页入口）
        page.evaluate("() => window.__wxPeer.openProfile()")
        page.wait_for_timeout(600)
        shot(page, "01_profile.png")

        # 2. 打开联系人设置页
        page.evaluate("() => window.__wxBlock.openSettings()")
        page.wait_for_timeout(600)
        shot(page, "02_settings.png")

        # 3. 拨「加入黑名单」开关（变绿）
        ok = page.evaluate("() => window.__wxBlock.tapToggle()")
        print("tapToggle:", ok)
        page.wait_for_timeout(400)
        shot(page, "03_toggle_on.png")

        # 4. 底部弹起确认弹窗
        page.evaluate("() => window.__wxBlock.showSheet('block')")
        page.wait_for_timeout(400)
        shot(page, "04_sheet.png")

        # 5. 点「确定」→ 弹窗收起
        page.evaluate("() => window.__wxBlock.confirmSheet()")
        page.wait_for_timeout(450)
        shot(page, "05_sheet_closed.png")

        # 6. 「正在加载」Toast
        page.evaluate("() => window.__wxBlock.showToast(1.2)")
        page.wait_for_timeout(350)
        shot(page, "06_loading.png")

        # 7. Toast 消失后的完成态
        page.wait_for_timeout(1400)
        shot(page, "07_done.png")

        # 8. 返回上一页（设置页 → 资料页）
        back = page.evaluate("() => window.__wxPeer.back()")
        page.wait_for_timeout(500)
        shot(page, "08_back_profile.png")
        print("back ->", back, "blocked:", page.evaluate("() => window.__wxBlock.isBlocked()"))

        # 9. 取消路径：重新进设置页（此时已拉黑，先 reset 再演示）
        page.evaluate("() => window.__wxBlock.reset()")
        page.wait_for_timeout(500)
        page.evaluate("() => window.__wxBlock.openSettings()")
        page.wait_for_timeout(500)
        page.evaluate("() => window.__wxBlock.tapToggle()")
        page.wait_for_timeout(300)
        page.evaluate("() => window.__wxBlock.showSheet('block')")
        page.wait_for_timeout(400)
        shot(page, "09_cancel_sheet.png")
        page.evaluate("() => window.__wxBlock.cancelSheet()")
        page.wait_for_timeout(400)
        shot(page, "10_after_cancel.png")
        print("after cancel blocked:", page.evaluate("() => window.__wxBlock.isBlocked()"))

        # 10. 移出黑名单文案核对
        page.evaluate("() => window.__wxBlock.reset()")
        page.wait_for_timeout(400)
        page.evaluate("() => { window.__wxBlock.openSettings(); "
                      "window.__wxBlock.tapToggleOff && null; }")
        # 手动把状态置为已拉黑再演示移出（直接走 block 全自动流的前半段）
        page.evaluate("() => { const b = window.__wxBlock; b.openSettings(); "
                      "b.tapToggle(); b.showSheet('block'); b.confirmSheet(); }")
        page.wait_for_timeout(300)
        page.evaluate("() => window.__wxBlock.tapToggleOff()")
        page.wait_for_timeout(300)
        page.evaluate("() => window.__wxBlock.showSheet('unblock')")
        page.wait_for_timeout(400)
        shot(page, "11_unblock_sheet.png")

        browser.close()
        print("DONE ->", OUT)


if __name__ == "__main__":
    main()
