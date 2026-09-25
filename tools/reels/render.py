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
  "cards": [                       # B-roll, full screen, speech and subtitles continue on top
    {"start": 4, "end": 7, "kind": "stat", "value": "90%", "label": "проектов ломаются после запуска"},
    {"start": 9, "end": 12, "kind": "text", "tag": "Главное", "text": "Код это шаг №5", "accent": "шаг №5"},
    {"start": 13, "end": 17, "kind": "list", "title": "3 шага", "items": ["...", "..."]},
    {"start": 18, "end": 22, "kind": "chat", "title": "Telegram-бот", "messages": [{"me": false, "text": "..."}]},
    {"start": 23, "end": 26, "kind": "clip", "file": "broll.mp4", "from": 0}
  ],
  "cta": {"text": "Напиши «AI»\\nв комментариях", "accent": "«AI»", "start": -3.5}
}
All times are seconds in the source video; a negative cta.start counts from the end.
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


def card_html(c):
    k = c["kind"]
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
        items = "".join(
            f'<div class="item" style="animation:up .45s {0.25 + i * 0.35:.2f}s both"><span class="n">{i + 1}</span><span>{esc(t)}</span></div>'
            for i, t in enumerate(c["items"]))
        body = f'<h1 style="font-size:78px;margin-bottom:40px;animation:up .45s both">{accented(c["title"], c.get("accent"))}</h1>{items}'
    elif k == "chat":
        msgs = "".join(
            f'<div class="msg {"out" if m.get("me") else "in"}" style="animation:up .4s {0.3 + i * 0.7:.2f}s both">{esc(m["text"])}</div>'
            for i, m in enumerate(c["messages"]))
        body = f'<div class="chathead">{esc(c.get("title", ""))}</div><div style="display:flex;flex-direction:column">{msgs}</div>'
    else:
        raise ValueError(f"unknown card kind {k}")
    return f"""<div class="card"><div class="grid"></div><div class="glow"></div>
<div class="handle">{HANDLE}</div><div class="content">{body}</div></div>"""


def banner_html(text, accent, top=260):
    """Hook / CTA plate on a transparent background, sits above the speaker."""
    return f"""<div style="position:absolute;left:70px;right:70px;top:{top}px;display:flex;justify-content:center;
animation:slidein .4s cubic-bezier(.2,.9,.3,1.2) both">
<div style="background:rgba(13,15,20,.92);border:4px solid {LIME};border-radius:36px;padding:40px 48px;text-align:center;
font-family:Unbounded;font-weight:800;font-size:72px;line-height:1.12;letter-spacing:-1px;box-shadow:0 20px 60px rgba(0,0,0,.5)">
{accented(text, accent, words_anim=True, delay0=0.15, step=0.06)}</div></div>"""


def render_frames(page, body, seconds, outdir, transparent):
    page.set_content(f"<html><head><meta charset='utf-8'><style>{BASE_CSS}</style></head>"
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

    overlays = []  # (kind, start, end, input_args)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME)
        page = browser.new_page(viewport={"width": W, "height": H})
        for i, c in enumerate(plan.get("cards", [])):
            s, e = c["start"], c["end"]
            if c["kind"] == "clip":
                overlays.append(("clip", s, e, ["-ss", str(c.get("from", 0)), "-t", f"{e - s:.3f}", "-i", p(c["file"])]))
                continue
            d = f"{tmp}/card{i}"
            render_frames(page, card_html(c), e - s, d, transparent=False)
            overlays.append(("card", s, e, ["-framerate", str(FPS), "-i", f"{d}/%05d.png"]))
        for key, top in (("hook", 260), ("cta", 300)):
            b = plan.get(key)
            if not b:
                continue
            s = b.get("start", 0)
            s = total + s if s < 0 else s
            e = b.get("end", total)
            d = f"{tmp}/{key}"
            render_frames(page, banner_html(b["text"], b.get("accent"), top), e - s, d, transparent=True)
            overlays.append(("banner", s, e, ["-framerate", str(FPS), "-i", f"{d}/%05d.png"]))
        browser.close()

    args = ["ffmpeg", "-y", "-v", "error", "-stats", "-i", src]
    fc = [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,format=yuv420p[v0]"]
    last = "v0"
    zooms = plan.get("zooms", [])
    if zooms:
        fc.append(f"[{last}]split={len(zooms) + 1}[zb]" + "".join(f"[zs{i}]" for i in range(len(zooms))))
        last = "zb"
        for i, z in enumerate(zooms):
            sc = z.get("scale", 1.15)
            zw, zh = int(W * sc) // 2 * 2, int(H * sc) // 2 * 2
            fc.append(f"[zs{i}]scale={zw}:{zh},crop={W}:{H}:(iw-{W})/2:(ih-{H})/2*0.8[zz{i}]")
            fc.append(f"[{last}][zz{i}]overlay=enable='between(t,{z['start']},{z['end']})'[zo{i}]")
            last = f"zo{i}"

    idx = 1
    banners = []
    for kind, s, e, inp in overlays:
        if kind == "banner":
            banners.append((s, e, inp)); continue
        args += inp
        prep = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1," if kind == "clip" else ""
        d = e - s
        fc.append(f"[{idx}:v]{prep}format=rgba,trim=duration={d:.3f},fade=in:st=0:d=0.18:alpha=1,"
                  f"fade=out:st={max(d - 0.18, 0):.3f}:d=0.18:alpha=1,setpts=PTS-STARTPTS+{s}/TB[o{idx}]")
        fc.append(f"[{last}][o{idx}]overlay=eof_action=pass:enable='between(t,{s},{e})'[v{idx}]")
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
             "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high",
             "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    run(args)
    shutil.rmtree(tmp, ignore_errors=True)
    print("rendered", out)


if __name__ == "__main__":
    main(sys.argv[1])
