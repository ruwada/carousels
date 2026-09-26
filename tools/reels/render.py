#!/usr/bin/env python3
"""Render a polished reel from a talking-head video and an edit plan.

    python3 render.py edit.json

edit.json:
{
  "src": "in.mp4",                 # trimmed talking-head video from the user
  "words": "words.json",           # from transcribe.py, spelling corrected by hand
  "out": "out.mp4",
  "hook":  {"text": "AI уже продаёт\\nвместо менеджеров", "accent": "продаёт", "start": 0, "end": 3},
  "zooms": [{"start": 5.0, "end": 7.5, "scale": 1.18}],
  "theme": "glass",                # design of the graphic cards, pick per reel: dark | paper | glass | terminal
  "transition": "smooth",          # default for cards and clips: smooth (fade) | sharp (slide / hard cut + punch-in)
  "cards": [                       # B-roll, full screen, speech and subtitles continue on top
    {"start": 4, "end": 7, "kind": "stat", "value": "90%", "label": "проектов ломаются после запуска"},
    {"start": 9, "end": 12, "kind": "text", "tag": "Главное", "text": "Код это шаг №5", "accent": "шаг №5"},
    {"start": 13, "end": 17, "kind": "list", "title": "3 шага", "items": ["...", "..."], "theme": "paper",
     "item_at": [0.4, 1.4, 2.3]},     # optional: when each item appears, seconds into the card
    {"start": 18, "end": 22, "kind": "chat", "title": "Telegram-бот", "frame": "phone",
     "messages": [{"me": true, "text": "..."}, {"me": false, "text": "...", "time": "19:02"}]},
    {"start": 23, "end": 26, "kind": "clip", "file": "broll.mp4", "from": 0, "transition": "sharp", "grade": true}
  ],
  "cta": {"text": "Напиши «AI»\\nв комментариях", "accent": "«AI»", "start": -3.5}
  # hook/cta take an optional "top" (px) to keep the plate off the speaker's face
}
All times are seconds in the source video; a negative cta.start counts from the end.
Themes: dark = grid on near-black; paper = light sheet with marker highlights; glass = frosted panel
over the blurred speaker (the speaker stays in frame); terminal = code window for dev topics.
A chat with "frame": "phone" is drawn as a Telegram screen in a phone; "me" messages go right.
Clips get a mild grade to sit with the speaker's footage ("grade": false to keep them as shot).
"""
import html, json, os, re, shutil, subprocess, sys, tempfile

W, H, FPS = 1080, 1920, 30
LIME, BG = "#C6F432", "#0D0F14"
CHROME = os.environ.get("CHROME", "/opt/pw-browsers/chromium")
HANDLE = "@islam.devai"


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


# ---------------------------------------------------------------- subtitles

def ass_time(t):
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def ass_escape(s):
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def chunk_words(words, max_words=3, max_chars=20, gap=0.35):
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words
                    or len(" ".join(x["w"] for x in cur + [w])) > max_chars
                    or w["s"] - cur[-1]["e"] > gap):
            chunks.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.!?,:;…—]$", w["w"]):
            chunks.append(cur); cur = []
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(words, path):
    lime = "&H0032F4C6&"
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Manrope ExtraBold,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,4,2,90,90,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for chunk in chunk_words(words):
        shown = [re.sub(r"[.,:;…]+$", "", w["w"]) for w in chunk]
        c_end = chunk[-1]["e"]
        for i, w in enumerate(chunk):
            start = w["s"]
            end = chunk[i + 1]["s"] if i + 1 < len(chunk) else c_end
            parts = []
            for j, text in enumerate(shown):
                text = ass_escape(text)
                parts.append(f"{{\\c{lime}}}{text}{{\\c&H00FFFFFF&}}" if j == i else text)
            pop = "{\\fscx88\\fscy88\\t(0,110,\\fscx100\\fscy100)}" if i == 0 else ""
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Sub,,0,0,0,,{pop}{' '.join(parts)}")
    open(path, "w").write(head + "\n".join(lines) + "\n")


# ---------------------------------------------------------------- HTML motion graphics

BASE_CSS = f"""
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden}}
body{{font-family:Manrope,sans-serif;color:#F2F3F5}}
.card{{position:absolute;inset:0;background:{BG};overflow:hidden}}
.glow{{position:absolute;right:-300px;top:-200px;width:900px;height:900px;border-radius:50%;
  background:radial-gradient(circle,rgba(198,244,50,.18),transparent 70%);animation:drift 6s linear both}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.035) 2px,transparent 2px),
  linear-gradient(90deg,rgba(255,255,255,.035) 2px,transparent 2px);background-size:90px 90px}}
.handle{{position:absolute;top:150px;left:90px;font-size:32px;font-weight:700;color:{LIME};animation:fade .4s both}}
.content{{position:absolute;left:90px;right:90px;top:300px;height:820px;display:flex;flex-direction:column;justify-content:center}}
.acc{{color:{LIME}}}
.tag{{align-self:flex-start;border:3px solid {LIME};color:{LIME};border-radius:50px;padding:14px 34px;font-size:32px;
  font-weight:800;letter-spacing:1px;text-transform:uppercase;margin-bottom:56px;animation:up .45s .05s both}}
h1{{font-family:Unbounded;font-weight:800;font-size:92px;line-height:1.08;letter-spacing:-1px}}
.big{{font-family:Unbounded;font-weight:800;font-size:250px;line-height:1;color:{LIME};letter-spacing:-8px;animation:pop .5s .05s both}}
.label{{font-size:56px;font-weight:700;line-height:1.25;margin-top:48px;animation:up .5s .3s both}}
.item{{display:flex;gap:34px;align-items:flex-start;padding:30px 0;border-bottom:3px solid #232733;font-size:48px;
  font-weight:700;line-height:1.25}}
.item:last-child{{border:none}}
.item .n{{font-family:Unbounded;color:{LIME};min-width:80px}}
.msg{{max-width:82%;padding:30px 40px;border-radius:40px;font-size:50px;font-weight:600;line-height:1.3;margin:14px 0}}
.msg.in{{align-self:flex-start;background:#1E222C;border-bottom-left-radius:10px}}
.msg.out{{align-self:flex-end;background:{LIME};color:#0D0F14;border-bottom-right-radius:10px}}
.chathead{{font-size:36px;font-weight:800;color:#8A90A0;margin-bottom:30px;animation:fade .3s both}}
.w{{display:inline-block;animation:up .45s both}}
@keyframes up{{from{{opacity:0;transform:translateY(60px)}}to{{opacity:1;transform:none}}}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes pop{{0%{{opacity:0;transform:scale(.6)}}70%{{opacity:1;transform:scale(1.06)}}100%{{transform:scale(1)}}}}
@keyframes drift{{from{{transform:translate(0,0)}}to{{transform:translate(-160px,120px)}}}}
@keyframes slidein{{from{{opacity:0;transform:translateY(-40px) scale(.9)}}to{{opacity:1;transform:none}}}}
@keyframes panel{{from{{opacity:0;transform:scale(.92)}}to{{opacity:1;transform:none}}}}
"""

# Card themes. The design changes from reel to reel so the cards never look like one template.
THEME_CSS = f"""
.card.paper{{background:#F2EEE4;color:#16181D}}
.paper .grid{{background-image:repeating-linear-gradient(transparent 0 88px,rgba(22,24,29,.08) 88px 91px);background-size:auto}}
.paper .grid::after{{content:'';position:absolute;top:0;bottom:0;left:64px;width:3px;background:rgba(214,80,60,.35)}}
.paper .glow{{display:none}}
.paper .handle{{color:#16181D;opacity:.55}}
.paper .acc{{color:#16181D;background:linear-gradient(transparent 55%,{LIME} 55% 90%,transparent 90%)}}
.paper .tag{{border-color:#16181D;color:#16181D}}
.paper .big{{color:#16181D;text-shadow:12px 12px 0 {LIME}}}
.paper .item{{border-color:#D9D2C3}}
.paper .item .n{{color:#16181D}}
.paper .msg.in{{background:#FFFFFF;box-shadow:0 10px 30px rgba(0,0,0,.08)}}
.paper .chathead{{color:#6B6F7A}}

.card.glass{{background:transparent}}
.glass .grid,.glass .glow,.glass .handle{{display:none}}
.glass .content{{left:64px;right:64px;top:0;bottom:640px;height:fit-content;margin:auto 0;padding:72px 64px;border-radius:56px;
  background:rgba(13,15,20,.6);border:2px solid rgba(255,255,255,.16);box-shadow:0 30px 90px rgba(0,0,0,.45);
  animation:panel .45s cubic-bezier(.2,.9,.3,1.1) both}}
.glass .item{{border-color:rgba(255,255,255,.12)}}
.glass .msg.in{{background:rgba(255,255,255,.12)}}

.card.terminal{{background:#070B08;font-family:'JetBrains Mono',monospace}}
.terminal .grid{{background-image:repeating-linear-gradient(rgba(120,255,140,.035) 0 2px,transparent 2px 6px);background-size:auto}}
.terminal .glow{{background:radial-gradient(circle,rgba(80,255,120,.12),transparent 70%)}}
.terminal .content{{top:280px;height:auto;padding:120px 56px 60px;border:2px solid #1D3322;border-radius:28px;background:rgba(9,16,11,.92)}}
.terminal .content::before{{content:'';position:absolute;top:44px;left:48px;width:22px;height:22px;border-radius:50%;
  background:#FF5F57;box-shadow:38px 0 #FEBC2E,76px 0 #28C840}}
.terminal h1,.terminal .big,.terminal .item,.terminal .item .n{{font-family:'JetBrains Mono',monospace}}
.terminal h1{{font-size:76px;letter-spacing:-2px}}
.terminal .big{{font-size:220px;letter-spacing:-6px}}
.terminal .item{{font-size:44px;border-color:#16261A}}
.terminal .item .n::before{{content:'> '}}
.terminal .tag{{border-radius:10px}}

.phone{{position:absolute;left:190px;right:190px;top:170px;height:1060px;border-radius:90px;background:#0E1621;overflow:hidden;
  border:14px solid #15171C;box-shadow:0 40px 120px rgba(0,0,0,.6),0 0 0 3px rgba(255,255,255,.1);
  animation:panel .45s cubic-bezier(.2,.9,.3,1.1) both}}
.phone .island{{position:absolute;top:20px;left:50%;width:150px;height:42px;margin-left:-75px;border-radius:24px;background:#000;z-index:2}}
.tgbar{{position:absolute;top:0;left:0;right:0;height:186px;padding:88px 34px 0;background:#17212B;display:flex;gap:20px;align-items:center}}
.tgbar .ava{{width:78px;height:78px;border-radius:50%;background:{LIME};color:#0D0F14;font-family:Unbounded;font-weight:800;
  font-size:26px;display:flex;align-items:center;justify-content:center;flex:none}}
.tgbar b{{display:block;font-size:36px;font-weight:800;color:#fff}}
.tgbar span{{font-size:27px;color:#6C7883;font-weight:700}}
.thread{{position:absolute;top:206px;left:26px;right:26px;bottom:40px;display:flex;flex-direction:column;justify-content:flex-end}}
.phone .msg{{font-size:39px;padding:22px 30px;border-radius:28px;max-width:88%;margin:9px 0;line-height:1.3}}
.phone .msg.in{{background:#182533;color:#fff;border-bottom-left-radius:8px}}
.phone .msg.out{{background:#2B5278;color:#fff;border-bottom-right-radius:8px}}
.phone .msg small{{display:block;text-align:right;font-size:22px;color:rgba(255,255,255,.5);margin-top:4px}}
"""

SEEK_JS = """
window.seek = t => {
  document.getAnimations().forEach(a => { a.pause(); a.currentTime = t * 1000; });
  document.querySelectorAll('[data-count]').forEach(el => {
    const k = Math.min(1, Math.max(0, (t - 0.05) / 0.9)), e = 1 - Math.pow(1 - k, 3);
    const v = parseFloat(el.dataset.count);
    el.textContent = el.dataset.pre + (Number.isInteger(v) ? Math.round(v * e) : (v * e).toFixed(1)) + el.dataset.suf;
  });
};
"""


def esc(s):
    return html.escape(s)


def accented(text, accent=None, words_anim=False, delay0=0.1, step=0.07):
    """Escape text, wrap `accent` in lime, keep newlines, optionally animate word by word."""
    out, i = [], 0
    for li, line in enumerate(text.split("\n")):
        tokens = []
        for word in line.split(" "):
            cls = "acc" if accent and word.strip("«»\"'.,!?") and word in accent.split(" ") else ""
            if words_anim:
                tokens.append(f'<span class="w {cls}" style="animation-delay:{delay0 + i * step:.2f}s">{esc(word)}</span>')
            else:
                tokens.append(f'<span class="{cls}">{esc(word)}</span>' if cls else esc(word))
            i += 1
        out.append(" ".join(tokens))
    return "<br>".join(out)


def phone_html(c):
    """Telegram chat inside a phone: the header is the bot, "me" messages are the other side."""
    msgs = ""
    for i, m in enumerate(c["messages"]):
        time = f'<small>{esc(m["time"])}</small>' if m.get("time") else ""
        side = "out" if m.get("me") else "in"
        msgs += f'<div class="msg {side}" style="animation:up .4s {0.35 + i * 0.75:.2f}s both">{esc(m["text"])}{time}</div>'
    return (f'<div class="phone"><div class="island"></div><div class="tgbar"><div class="ava">AI</div>'
            f'<div><b>{esc(c.get("title", "AI-агент"))}</b><span>{esc(c.get("status", "бот"))}</span></div></div>'
            f'<div class="thread">{msgs}</div></div>')


def card_html(c, theme="dark"):
    k = c["kind"]
    if k == "chat" and c.get("frame") == "phone":
        return f"""<div class="card {theme}"><div class="grid"></div><div class="glow"></div>
<div class="handle">{HANDLE}</div>{phone_html(c)}</div>"""
    if k == "stat":
        m = re.match(r"^(\D*)([\d.,]+)(.*)$", c["value"])
        if m:
            num = m.group(2).replace(",", ".")
            big = f'<div class="big" data-count="{num}" data-pre="{esc(m.group(1))}" data-suf="{esc(m.group(3))}">{esc(c["value"])}</div>'
        else:
            big = f'<div class="big">{esc(c["value"])}</div>'
        tag = f'<div class="tag">{esc(c["tag"])}</div>' if c.get("tag") else ""
        body = f'{tag}{big}<div class="label">{accented(c["label"], c.get("accent"))}</div>'
    elif k == "text":
        tag = f'<div class="tag">{esc(c["tag"])}</div>' if c.get("tag") else ""
        body = f'{tag}<h1>{accented(c["text"], c.get("accent"), words_anim=True)}</h1>'
    elif k == "list":
        at = c.get("item_at") or [0.25 + i * 0.35 for i in range(len(c["items"]))]  # seconds into the card, to match speech
        items = "".join(
            f'<div class="item" style="animation:up .45s {at[i]:.2f}s both"><span class="n">{i + 1}</span><span>{esc(t)}</span></div>'
            for i, t in enumerate(c["items"]))
        body = f'<h1 style="font-size:78px;margin-bottom:40px;animation:up .45s both">{accented(c["title"], c.get("accent"))}</h1>{items}'
    elif k == "chat":
        msgs = "".join(
            f'<div class="msg {"out" if m.get("me") else "in"}" style="animation:up .4s {0.3 + i * 0.7:.2f}s both">{esc(m["text"])}</div>'
            for i, m in enumerate(c["messages"]))
        body = f'<div class="chathead">{esc(c.get("title", ""))}</div><div style="display:flex;flex-direction:column">{msgs}</div>'
    else:
        raise ValueError(f"unknown card kind {k}")
    return f"""<div class="card {theme}"><div class="grid"></div><div class="glow"></div>
<div class="handle">{HANDLE}</div><div class="content">{body}</div></div>"""


def banner_html(text, accent, top=260):
    """Hook / CTA plate on a transparent background, sits above the speaker."""
    return f"""<div style="position:absolute;left:70px;right:70px;top:{top}px;display:flex;justify-content:center;
animation:slidein .4s cubic-bezier(.2,.9,.3,1.2) both">
<div style="background:rgba(13,15,20,.92);border:4px solid {LIME};border-radius:36px;padding:40px 48px;text-align:center;
font-family:Unbounded;font-weight:800;font-size:72px;line-height:1.12;letter-spacing:-1px;box-shadow:0 20px 60px rgba(0,0,0,.5)">
{accented(text, accent, words_anim=True, delay0=0.15, step=0.06)}</div></div>"""


def render_frames(page, body, seconds, outdir, transparent):
    page.set_content(f"<html><head><meta charset='utf-8'><style>{BASE_CSS}{THEME_CSS}</style></head>"
                     f"<body style='background:{'transparent' if transparent else BG}'>{body}"
                     f"<script>{SEEK_JS}</script></body></html>")
    page.evaluate("document.fonts.ready")
    os.makedirs(outdir, exist_ok=True)
    n = max(1, round(seconds * FPS))
    for f in range(n):
        page.evaluate(f"seek({f / FPS})")
        page.screenshot(path=f"{outdir}/{f:05d}.png", omit_background=transparent)
    return n


# ---------------------------------------------------------------- main

def main(plan_path):
    plan = json.load(open(plan_path))
    root = os.path.dirname(os.path.abspath(plan_path))
    p = lambda x: x if os.path.isabs(x) else os.path.join(root, x)
    src, out = p(plan["src"]), p(plan.get("out", "out.mp4"))
    total = duration(src)
    words = json.load(open(p(plan["words"])))
    tmp = tempfile.mkdtemp(prefix="reel-")

    build_ass(words, f"{tmp}/subs.ass")

    # cards and clips; transition "smooth" = soft fade, "sharp" = slide (cards) or hard cut + punch-in (clips)
    overlays, banners = [], []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME)
        page = browser.new_page(viewport={"width": W, "height": H})
        for i, c in enumerate(plan.get("cards", [])):
            o = dict(s=c["start"], e=c["end"], kind=c["kind"], sharp=c.get("transition", plan.get("transition")) == "sharp")
            if c["kind"] == "clip":
                o.update(kind="clip", grade=c.get("grade", True),
                         inp=["-ss", str(c.get("from", 0)), "-t", f"{o['e'] - o['s']:.3f}", "-i", p(c["file"])])
            else:
                theme = c.get("theme", plan.get("theme", "dark"))
                d = f"{tmp}/card{i}"
                render_frames(page, card_html(c, theme), o["e"] - o["s"], d, transparent=theme == "glass")
                o.update(kind="card", glass=theme == "glass", inp=["-framerate", str(FPS), "-i", f"{d}/%05d.png"])
            overlays.append(o)
        for key, top in (("hook", 260), ("cta", 300)):
            b = plan.get(key)
            if not b:
                continue
            s = b.get("start", 0)
            s = total + s if s < 0 else s
            e = b.get("end", total)
            d = f"{tmp}/{key}"
            render_frames(page, banner_html(b["text"], b.get("accent"), b.get("top", top)), e - s, d, transparent=True)
            banners.append((s, e, ["-framerate", str(FPS), "-i", f"{d}/%05d.png"]))
        browser.close()

    args = ["ffmpeg", "-y", "-v", "error", "-stats", "-i", src]
    zooms = plan.get("zooms", [])
    fc = [f"[0:v]split={len(zooms) + 1}[src]" + "".join(f"[zsrc{i}]" for i in range(len(zooms))),
          f"[src]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS},setsar=1,format=yuv420p[v0]"]
    last = "v0"
    # punch-in zooms crop the full-resolution source, so a 4K original stays sharp when zoomed
    for i, z in enumerate(zooms):
        sc = z.get("scale", 1.15)
        cw, ch = f"min(iw,ih*{W}/{H})/{sc}", f"min(ih,iw*{H}/{W})/{sc}"
        fc.append(f"[zsrc{i}]crop=w='{cw}':h='{ch}':x='(iw-ow)/2':y='(ih-oh)/2*0.8',"
                  f"scale={W}:{H}:flags=lanczos,fps={FPS},setsar=1,format=yuv420p[zz{i}]")
        fc.append(f"[{last}][zz{i}]overlay=enable='between(t,{z['start']},{z['end']})'[zo{i}]")
        last = f"zo{i}"

    idx = 1
    for o in overlays:
        s, e, sharp = o["s"], o["e"], o["sharp"]
        d = e - s
        args += o["inp"]
        on = f"enable='between(t,{s},{e})'"
        if o.get("glass"):
            # frost the speaker behind a glass card: blurred, dimmed copy of the frame that fades with the card
            f = 0.15 if sharp else 0.4
            fc.append(f"[{last}]split[gs{idx}][gb{idx}]")
            fc.append(f"[gb{idx}]scale=270:480,boxblur=6:2,scale={W}:{H},eq=brightness=-0.08:saturation=0.8,format=rgba,"
                      f"fade=in:st={s}:d={f}:alpha=1,fade=out:st={e - f:.3f}:d={f}:alpha=1[gf{idx}]")
            fc.append(f"[gs{idx}][gf{idx}]overlay={on}[gv{idx}]")
            last = f"gv{idx}"
        chain = f"[{idx}:v]"
        if o["kind"] == "clip":
            chain += f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,"
            if o["grade"]:
                chain += "eq=contrast=1.05:brightness=-0.02:saturation=0.88,vignette=angle=PI/5,"
            if sharp:  # hard cut in, then a quick settle from a 12% push-in
                chain += (f"scale=w='trunc({W}*(1+0.12*pow(max(0,1-t/0.3),2))/2)*2':h=-2:eval=frame,"
                          f"crop={W}:{H}:(iw-{W})/2:(ih-{H})/2,")
        chain += f"format=rgba,trim=duration={d:.3f},"
        ov = "overlay=eof_action=pass"
        if not sharp:
            fd = 0.4
            chain += f"fade=in:st=0:d={fd}:alpha=1,fade=out:st={max(d - fd, 0):.3f}:d={fd}:alpha=1,"
        elif o["kind"] == "card":
            a, b = 0.22, 0.16  # slide-in and slide-out durations
            x = (f"if(lt(t,{s + a:.3f}),main_w*pow(1-(t-{s})/{a},3),"
                 f"if(gt(t,{e - b:.3f}),-main_w*pow((t-{e - b:.3f})/{b},2),0))")
            ov = f"overlay=x='{x}':y=0:eval=frame:eof_action=pass"
        fc.append(f"{chain}setpts=PTS-STARTPTS+{s}/TB[o{idx}]")
        fc.append(f"[{last}][o{idx}]{ov}:{on}[v{idx}]")
        last = f"v{idx}"; idx += 1

    subs = f"{tmp}/subs.ass".replace(":", "\\:")
    fc.append(f"[{last}]ass='{subs}':fontsdir=/usr/local/share/fonts/brand[vs]")
    last = "vs"
    for s, e, inp in banners:
        args += inp
        d = e - s
        fc.append(f"[{idx}:v]format=rgba,fade=out:st={max(d - 0.25, 0):.3f}:d=0.25:alpha=1,setpts=PTS-STARTPTS+{s}/TB[o{idx}]")
        fc.append(f"[{last}][o{idx}]overlay=eof_action=pass:enable='between(t,{s},{e})'[v{idx}]")
        last = f"v{idx}"; idx += 1
    fc.append("[0:a]highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,"
              "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")

    args += ["-filter_complex", ";".join(fc), "-map", f"[{last}]", "-map", "[a]",
             "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high",
             "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    run(args)
    shutil.rmtree(tmp, ignore_errors=True)
    print("rendered", out)


if __name__ == "__main__":
    main(sys.argv[1])
