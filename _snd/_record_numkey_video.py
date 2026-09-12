# -*- coding: utf-8 -*-
"""录制演示视频 v2：数字/字母键盘发送键组合态 确认↔发送。
流畅度：CDP Page.startScreencast 逐帧抓取（按真实时间戳组装），弃用 record_video。
逻辑：pressRun 只打字母出组合，每段打完显式上屏（候选首位/确认/空格选定）。
输出 1080x2340 mp4。
"""
import sys, time, json, glob, os, subprocess, base64
sys.path.insert(0, '.')
import main
from playwright.sync_api import sync_playwright

def read_e(n):
    return main._read_enhance(n)

CSS1 = ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
        "wechat_modern.css", "human_actions.css", "transfer_ui.css", "transfer_detail.css",
        "send_image_ui.css", "peer_pages.css", "block_ui.css", "video_player.css",
        "homepage_exact.css"]
JS1 = ["config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
       "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "transfer_detail.js",
       "send_image_ui.js", "video_player.js", "peer_pages.js", "block_ui.js"]
CSS2 = ["chat_exact.css", "panel_switch.css", "wx_icons.css", "moments_exact.css", "discover_exact.css"]
JS2 = ["panel_switch.js", "human_actions.js", "homepage.js"]

def tap_key(pg, sel):
    r = json.loads(pg.evaluate(f"""JSON.stringify((()=>{{
        const els=[...document.querySelectorAll('{sel}')];
        const el=els.find(e=>e.getBoundingClientRect().width>10)||els[0];
        if(!el)return null;const b=el.getBoundingClientRect();
        return [b.x+b.width/2,b.y+b.height/2]}})())"""))
    pg.mouse.click(r[0], r[1])

os.makedirs('_snd/frames', exist_ok=True)
for f in glob.glob('_snd/frames/*'):
    os.remove(f)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 600, 'height': 1300})
    pg = ctx.new_page()
    pg.goto('http://localhost:8080', wait_until='networkidle')
    pg.wait_for_timeout(800)
    for c in CSS1:
        pg.add_style_tag(content=read_e(c))
    for j in JS1:
        pg.evaluate(read_e(j))
    pg.add_script_tag(content=read_e("pinyin_data.js"))
    pg.evaluate(read_e("keyboard.js"))
    pg.evaluate(main.ENHANCE_JS)
    for j in JS2:
        pg.evaluate(read_e(j))
    for c in CSS2:
        pg.add_style_tag(content=read_e(c))
    pg.wait_for_timeout(400)

    # ---- CDP screencast：逐帧抓取 ----
    cdp = ctx.new_cdp_session(pg)
    frames = []          # (timestamp, filepath)
    counter = [0]
    def on_frame(params):
        ts = params['metadata']['timestamp']
        counter[0] += 1
        fp = f'_snd/frames/f{counter[0]:05d}.png'
        with open(fp, 'wb') as fh:
            fh.write(base64.b64decode(params['data']))
        frames.append((ts, fp))
        try:
            cdp.send('Page.screencastFrameAck', {'sessionId': params['sessionId']})
        except Exception:
            pass
    cdp.on('Page.screencastFrame', on_frame)
    cdp.send('Page.startScreencast', {'format': 'png', 'everyNthFrame': 1})

    def wait_s(t):
        pg.wait_for_timeout(int(t * 1000))

    # 进会话 → 输入栏出键盘
    pg.mouse.click(300, 430)
    wait_s(1.0)
    pg.mouse.click(250, 1210)
    wait_s(0.9)
    ok = pg.evaluate("!!(window.__wxKeyboard && window.__wxKeyboard.visible)")
    if not ok:
        pg.mouse.click(250, 1184); wait_s(0.9)
        ok = pg.evaluate("!!(window.__wxKeyboard && window.__wxKeyboard.visible)")
    if not ok:
        pg.evaluate("window.__wxKeyboard.show()")
        wait_s(0.8)
        pg.mouse.click(250, 1184); wait_s(0.5)
    r = json.loads(pg.evaluate("JSON.stringify((()=>{const el=document.querySelector('.chat-txt');"
                               "const b=el.getBoundingClientRect();return [b.x,b.y,b.width,b.height]})())"))
    pg.mouse.click(r[0] + r[2] / 2, r[1] + r[3] / 2)
    wait_s(0.3)
    pg.evaluate("document.querySelector('.chat-txt').focus()")
    wait_s(0.8)

    # 1) 字母页打 "ni" → 组合态（选定/确认）→ 上屏「你」→ 发送态
    pg.evaluate("window.__wxKeyboard.pressRun('ni', 170, 170, '你', 'ni')")
    wait_s(1.0)
    pg.evaluate("window.__wxKeyboard.commitByPhrase('你')")
    wait_s(1.2)

    # 2) 打 "hao" → 组合态 → 按空格「选定」上屏「好」→ 发送态
    pg.evaluate("window.__wxKeyboard.pressRun('hao', 170, 170, '好', 'hao')")
    wait_s(1.0)
    tap_key(pg, '#wxkb .kb-key.kb-space')
    wait_s(1.2)

    # 3) 打 "wo" 保持组合态 → 切 123 数字页（确认态保持）→ 按「确认」原样上屏 → 发送态
    pg.evaluate("window.__wxKeyboard.pressRun('wo', 170, 170, '我', 'wo')")
    wait_s(1.0)
    tap_key(pg, '#wxkb .kb-key[data-key="123"]')
    wait_s(1.2)
    tap_key(pg, '#wxkb .kb-key.kb-send')
    wait_s(1.2)

    # 4) 数字页打 666：全程发送态
    pg.evaluate("document.querySelector('.chat-txt').focus()")
    wait_s(0.2)
    for k in ['6', '6', '6']:
        tap_key(pg, f'#wxkb .kb-key[data-key="{k}"]')
        wait_s(0.45)
    wait_s(0.8)

    # 5) 回拼音页打 "ya" → 组合态 → 上屏「呀」→ 发送态收尾
    tap_key(pg, '#wxkb .kb-key[data-key="abc"]')
    wait_s(1.0)
    pg.evaluate("document.querySelector('.chat-txt').focus()")
    wait_s(0.2)
    pg.evaluate("window.__wxKeyboard.pressRun('ya', 170, 170, '呀', 'ya')")
    wait_s(1.0)
    pg.evaluate("window.__wxKeyboard.commitByPhrase('呀')")
    wait_s(1.5)

    cdp.send('Page.stopScreencast')
    wait_s(0.4)
    print('captured frames:', len(frames))
    ctx.close()
    b.close()

# ---- 按真实时间戳组装 concat 列表（帧间 duration = 相邻时间戳差） ----
if len(frames) < 2:
    print('ERROR: too few frames'); sys.exit(1)
t0 = frames[0][0]
lines = []
for i, (ts, fp) in enumerate(frames):
    rel = ts - t0
    if i + 1 < len(frames):
        dur = max(0.02, frames[i+1][0] - ts)
    else:
        dur = 0.5
    lines.append(f"file '{os.path.basename(fp)}'")
    lines.append(f"duration {dur:.4f}")
lines.append(f"file '{os.path.basename(frames[-1][1])}'")
open('_snd/frames/list.txt', 'w').write('\n'.join(lines))
print('timeline span: %.2fs, frames: %d' % (frames[-1][0] - t0, len(frames)))

FF = r"C:\Users\mik\AppData\Local\Programs\Python\Python314\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
out = '_snd/numkey_send_demo.mp4'
r = subprocess.run([FF, '-y', '-f', 'concat', '-safe', '0', '-i', '_snd/frames/list.txt',
                    '-vf', 'scale=1080:2340:flags=lanczos',
                    '-c:v', 'libx264', '-preset', 'fast', '-r', '30',
                    '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out],
                   capture_output=True, text=True)
print('ffmpeg rc=', r.returncode)
if r.returncode != 0:
    print(r.stderr[-1500:])
else:
    print('mp4:', out, os.path.getsize(out), 'bytes')
