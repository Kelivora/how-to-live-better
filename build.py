# -*- coding: utf-8 -*-
"""把《高性价比人生指南》指定的节，渲染成一个自包含的单文件 HTML 阅读页。

页面是手机优先的「卡片翻阅」形式：首页按节选，进去后一条建议一张卡，
左右滑动换卡，轻点翻面看成本、收益、备注与来源。

用法：
    python build.py                      # 默认第 1、2、16 节
    python build.py 1 2 16 3             # 指定任意节号（按给定顺序渲染）
    python build.py all                  # 全部节（用于线上站点）
    python build.py all -o index.html    # 指定输出文件名
    python build.py all --repo /path/to/HowToLiveBetter

源目录也可用环境变量 HLTB_REPO 覆盖（供 GitHub Actions 使用，优先级低于 --repo）。
产物默认与脚本同目录，单个 .html，无任何外部依赖，双击即可打开、可离线读。

数字与标签的口径完全照抄仓库 tools/sync-stats.ps1 与 index.html 的 COST_W / e.ratio：
仓库改了那两行，这里也要同步改，否则性价比档会和官方检索页对不上。
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def parse_args():
    ap = argparse.ArgumentParser(description="生成《高性价比人生指南》单文件阅读页")
    ap.add_argument("sections", nargs="*", help="节号；或 all 表示全部节")
    ap.add_argument("-o", "--out", default=None, help="输出文件名（默认按节号自动命名）")
    ap.add_argument("--repo", default=None, help="上游仓库目录（默认 D:\\Agent\\HowToLiveBetter）")
    return ap.parse_args()


ARGS = parse_args()
REPO = Path(ARGS.repo or os.environ.get("HLTB_REPO") or r"D:\Agent\HowToLiveBetter")

UPSTREAM = "https://github.com/eternity4719/HowToLiveBetter"


def avail_sections():
    """扫描 book/ 目录，得到实际存在的节号。"""
    return sorted(int(p.name[:2]) for p in REPO.glob("book/[0-9][0-9]-*.md"))


ALL = avail_sections()
if not ALL:
    raise SystemExit("在 %s 下找不到 book/NN-*.md，请用 --repo 指定正确的仓库目录" % REPO)

if ARGS.sections:
    if any(a.lower() == "all" for a in ARGS.sections):
        SECTIONS = ALL
    else:
        SECTIONS = [int(a) for a in ARGS.sections]
else:
    SECTIONS = [n for n in (1, 2, 16) if n in ALL]

SCOPE = ("全书 %d 节" % len(ALL)) if SECTIONS == ALL else ("第 %s 节" % "、".join(str(n) for n in SECTIONS))

# 成本权重与档位规则，抄自 index.html 的 COST_W 与 e.ratio 两行
COST_W = {
    "钱": {"0": 0, "少": 1, "多": 2},
    "时间": {"少": 0, "中": 1, "多": 2},
    "毅力": {"否": 0, "些": 1, "是": 2},
}
RATIO_ORDER = {"极高": 0, "高": 1, "一般": 2}


def find_file(n):
    hits = sorted(REPO.glob("book/%02d-*.md" % n))
    if not hits:
        raise SystemExit("找不到第 %d 节" % n)
    return hits[0]


def parse(path):
    lines = path.read_text(encoding="utf-8").split("\n")
    title, intro, entries, cur = "", [], [], None
    for ln in lines:
        m = re.match(r"^#\s+(.*)$", ln)
        if m and not title:
            title = m.group(1).strip()
            continue
        m = re.match(r"^###\s+(\d+)\.\s*(.*)$", ln)
        if m:
            cur = {"no": int(m.group(1)), "title": m.group(2).strip(),
                   "tags_raw": None, "fields": {}, "last": None}
            entries.append(cur)
            continue
        if cur is None:
            if ln.strip() and not ln.startswith("["):
                intro.append(ln.strip())
            continue
        mt = re.match(r"^<!--\s*成本标签:\s*(.*?)\s*-->", ln)
        if mt:
            cur["tags_raw"] = mt.group(1)
            continue
        mf = re.match(r"^-\s*(成本|说人话|收益|证据等级|来源|备注)：(.*)$", ln)
        if mf:
            cur["last"] = mf.group(1)
            cur["fields"][mf.group(1)] = mf.group(2).strip()
            continue
        if not ln.strip():
            cur["last"] = None
            continue
        if cur["last"]:
            cur["fields"][cur["last"]] += ln.strip()
    return title, intro, entries


def parse_tags(raw):
    if not raw:
        return {}
    return dict(re.findall(r"(钱|时间|毅力|收益|口径)=(\S+)", raw))


def ratio_of(t):
    try:
        cs = sum(COST_W[k][t[k]] for k in ("钱", "时间", "毅力"))
    except KeyError:
        return None
    lv = t.get("收益")
    if lv == "大":
        return "极高" if cs == 0 else ("高" if cs <= 2 else "一般")
    if lv == "中" and cs == 0:
        return "高"
    return "一般"


def inline(s):
    """把一小段 markdown 行内语法转成 HTML。先整体转义，再用占位符放链接。"""
    stash = []

    def mk(url, text=None):
        shown = text or url
        if len(shown) > 62:
            shown = shown[:59] + "…"
        stash.append('<a href="%s" target="_blank" rel="noopener">%s</a>' % (url, shown))
        return "\u0001%d\u0001" % (len(stash) - 1)

    s = html.escape(s, quote=False)
    s = re.sub(r"&lt;(https?://[^\s]+?)&gt;", lambda m: mk(m.group(1)), s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", lambda m: mk(m.group(2), m.group(1)), s)
    s = re.sub(r"(?<![\w\"=])(https?://[^\s，。；）)]+)", lambda m: mk(m.group(1)), s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = s.replace("\\*", "*").replace("\\_", "_")
    s = re.sub("\u0001(\\d+)\u0001", lambda m: stash[int(m.group(1))], s)
    return s


def link_count(s):
    return len(re.findall(r"https?://", s or ""))


def source_rev():
    """取上游当前提交的短 hash 与日期。

    故意用上游 git 状态而不是构建时间：同样的源状态下重跑结果完全一致，
    产物可做字节级比对，方便确认「没改坏东西」。
    """
    try:
        p = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--date=short",
                            "--format=%h|%cd"],
                           capture_output=True, text=True, encoding="utf-8", timeout=15)
        if p.returncode == 0 and "|" in (p.stdout or ""):
            h, d = p.stdout.strip().split("|", 1)
            return h.strip(), d.strip()
    except Exception:
        pass
    return "", ""


CSS = r"""
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#f4f1ec;--card:#fffdf9;--card-2:#f7f4ee;--line:#e6e0d6;
  --t1:#1f1d1a;--t2:#57524a;--t3:#8c867c;
  --brand:#2c6e58;--brand-ink:#fff;--brand-soft:rgba(44,110,88,.1);--brand-line:rgba(44,110,88,.32);
  --gA:#1d7a4c;--gA-s:rgba(29,122,76,.11);
  --gB:#975a0a;--gB-s:rgba(214,140,20,.15);
  --gC:#686c73;--gC-s:rgba(120,126,138,.15);
  --w0:#1d7a4c;--w1:#a15c07;--w2:#b42318;
  --mark:rgba(250,204,21,.45);
  --ink-s:46%;--ink-l:35%;--tint-s:58%;--tint-l:93%;
  --shadow:0 1px 2px rgba(40,30,15,.05),0 8px 24px -10px rgba(40,30,15,.18);
  --shadow-lg:0 1px 3px rgba(40,30,15,.06),0 22px 44px -18px rgba(40,30,15,.3);
  --serif:"Songti SC","STSong","Noto Serif SC","Noto Serif CJK SC","Source Han Serif SC",ui-serif,Georgia,serif;
  --font:ui-sans-serif,system-ui,-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  --ease:cubic-bezier(.2,.8,.2,1);
  --spring:cubic-bezier(.3,1.35,.45,1);
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){%DARK%}}
:root[data-theme=dark]{%DARK%}
html{-webkit-text-size-adjust:100%;-webkit-tap-highlight-color:transparent}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--t1);font:15px/1.7 var(--font);-webkit-font-smoothing:antialiased}
button{font:inherit;color:inherit;-webkit-user-select:none;user-select:none}
button:not(:disabled){cursor:pointer}
:focus{outline:0}
:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
a{color:var(--brand);text-decoration:none}
a:hover{text-decoration:underline;text-underline-offset:2px}
mark{background:var(--mark);color:inherit;border-radius:3px;padding:0 1px}
strong{font-weight:650;color:var(--t1)}
svg{flex:none}
.ico{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.hidden{display:none!important}
.icon-btn{width:42px;height:42px;flex:none;display:grid;place-items:center;padding:0;border-radius:14px;
  border:1px solid var(--line);background:var(--card);color:var(--t2);transition:transform .18s var(--ease),opacity .2s,color .2s}
.icon-btn:active:not(:disabled){transform:scale(.9)}
.icon-btn:disabled{opacity:.3}

/* ---------- 目录页 ---------- */
.home{max-width:1000px;margin:0 auto;padding:calc(env(safe-area-inset-top) + 20px) 16px calc(env(safe-area-inset-bottom) + 36px)}
.hero{display:flex;align-items:flex-start;gap:12px;padding:4px 2px 14px;animation:rise .7s var(--ease) both}
.hero .txt{flex:1;min-width:0}
.kicker{font-size:11px;font-weight:700;letter-spacing:.22em;color:var(--brand)}
.hero h1{font:700 30px/1.25 var(--serif);margin:6px 0 8px;letter-spacing:.02em}
.hero p{margin:0;font-size:13px;line-height:1.7;color:var(--t3)}
.hero p b{color:var(--t2);font-weight:600;font-variant-numeric:tabular-nums}
.tools{position:sticky;top:0;z-index:10;margin:0 -16px;padding:calc(env(safe-area-inset-top) + 8px) 16px 10px;
  background:var(--bg);background:color-mix(in srgb,var(--bg) 86%,transparent);
  -webkit-backdrop-filter:saturate(1.6) blur(14px);backdrop-filter:saturate(1.6) blur(14px);animation:rise .7s .06s var(--ease) both}
.search{position:relative;display:block;margin:0}
.search input{width:100%;height:46px;padding:0 44px;border-radius:16px;border:1px solid var(--line);background:var(--card);
  color:var(--t1);font:inherit;font-size:16px;-webkit-appearance:none;appearance:none;transition:border-color .2s,box-shadow .2s}
.search input::placeholder{color:var(--t3)}
.search input::-webkit-search-cancel-button{display:none}
.search input:focus{border-color:var(--brand-line);box-shadow:0 0 0 4px var(--brand-soft);outline:0}
.search>.ico{position:absolute;left:15px;top:13px;color:var(--t3);pointer-events:none}
.search .clr{position:absolute;right:5px;top:5px;width:36px;height:36px;border:0;border-radius:12px;background:none;color:var(--t3);display:grid;place-items:center;padding:0}
.chips-row{display:flex;gap:8px;margin-top:10px;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}
.chips-row::-webkit-scrollbar{display:none}
.pill{flex:none;display:inline-flex;align-items:center;gap:6px;height:36px;padding:0 15px;border-radius:999px;border:1px solid var(--line);
  background:var(--card);color:var(--t2);font-size:13.5px;font-weight:550;transition:background .22s var(--ease),color .22s,border-color .22s,transform .18s var(--ease)}
.pill:active{transform:scale(.95)}
.pill[aria-pressed=true]{background:var(--t1);border-color:var(--t1);color:var(--bg)}
.pill .ico{width:16px;height:16px}
.pill.ghost{color:var(--brand);border-color:var(--brand-line);background:var(--brand-soft)}
.resume{display:flex;align-items:center;gap:14px;width:100%;margin:12px 0 2px;padding:14px 16px;border:0;border-radius:20px;
  background:var(--brand);color:var(--brand-ink);text-align:left;box-shadow:var(--shadow);animation:rise .7s .1s var(--ease) both;transition:transform .2s var(--ease)}
.resume:active{transform:scale(.98)}
.resume .play{width:40px;height:40px;border-radius:50%;background:rgba(255,255,255,.18);display:grid;place-items:center;flex:none}
.resume .play svg{width:16px;height:16px;fill:currentColor}
.resume .rt{flex:1;min-width:0;line-height:1.45}
.resume .rt small{display:block;font-size:12px;opacity:.78}
.resume .rt b{display:block;font-weight:650;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.resume .rt span{display:block;font-size:12.5px;opacity:.85;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hits{display:flex;align-items:center;gap:12px;margin:12px 0 2px;padding:12px 12px 12px 16px;border-radius:18px;background:var(--card);
  border:1px solid var(--line);font-size:14px;color:var(--t2);animation:rise .4s var(--ease) both}
.hits>div{flex:1;min-width:0}
.hits b{color:var(--t1);font-size:18px;font-variant-numeric:tabular-nums;margin-right:2px}
.hits .pill{background:var(--brand);border-color:var(--brand);color:var(--brand-ink)}
.label{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:20px 2px 10px 4px;font-size:13px;color:var(--t3)}
.label b{color:var(--t1);font-size:15px;font-weight:650;margin-right:8px}
.label .pill{height:34px;padding:0 13px;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(138px,1fr));gap:10px}
.tile{position:relative;display:flex;flex-direction:column;align-items:stretch;gap:6px;min-height:138px;padding:14px 14px 12px;
  border-radius:20px;border:1px solid var(--line);text-align:left;overflow:hidden;color:var(--t1);
  background:linear-gradient(150deg,hsl(var(--h) var(--tint-s) var(--tint-l)) 0%,var(--card) 64%);
  animation:rise .6s var(--ease) both;animation-delay:min(calc(var(--i) * 26ms + 120ms),760ms);
  transition:transform .25s var(--ease),box-shadow .25s,opacity .3s}
.tile:active{transform:scale(.96)}
@media (hover:hover){.tile:hover{transform:translateY(-3px);box-shadow:var(--shadow)}}
.tile.none{opacity:.32;pointer-events:none}
.t-no{font:700 28px/1 var(--serif);color:hsl(var(--h) var(--ink-s) var(--ink-l));letter-spacing:-.02em}
.t-name{font-size:15px;font-weight:650;line-height:1.42}
.t-meta{margin-top:auto;display:flex;gap:8px;font-size:12px;color:var(--t3);font-variant-numeric:tabular-nums}
.t-bar{height:3px;border-radius:3px;background:var(--line);overflow:hidden}
.t-bar i{display:block;height:100%;width:var(--p,0%);border-radius:inherit;background:hsl(var(--h) var(--ink-s) var(--ink-l));transition:width .7s var(--ease)}
.tile.done::after{content:"";position:absolute;top:12px;right:12px;width:22px;height:22px;border-radius:50%;
  background:hsl(var(--h) var(--ink-s) var(--ink-l)) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 12.5l4.5 4.5L19 7.5'/%3E%3C/svg%3E") center/14px no-repeat}
footer{margin:34px 4px 0;padding-top:16px;border-top:1px solid var(--line);color:var(--t3);font-size:12px;line-height:1.9}
footer a{color:var(--t2)}
@keyframes rise{from{opacity:0;translate:0 16px}}

/* ---------- 卡片阅读层 ---------- */
body.reading{overflow:hidden}
.deck{position:fixed;inset:0;z-index:50;display:flex;flex-direction:column;height:100vh;height:100dvh;overflow:hidden;
  padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom);background:var(--bg);--accent:var(--brand);
  visibility:hidden;opacity:0;transform:translateY(28px) scale(.98);
  transition:opacity .28s var(--ease),transform .45s var(--ease),visibility 0s linear .45s}
body.reading .deck{visibility:visible;opacity:1;transform:none;transition:opacity .28s var(--ease),transform .45s var(--ease),visibility 0s}
.d-top,.d-prog,.d-ctl{width:100%;max-width:560px;margin:0 auto}
.d-top{display:flex;align-items:center;gap:8px;padding:10px 14px 4px}
.d-title{flex:1;min-width:0;height:42px;display:flex;align-items:center;justify-content:center;gap:4px;padding:0 6px;
  border:0;border-radius:14px;background:none;font-size:15.5px;font-weight:650}
.d-title span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.d-title .ico{width:16px;height:16px;color:var(--t3)}
.d-title:active{background:var(--card)}
.d-prog{display:flex;align-items:center;gap:12px;padding:2px 22px 8px;font-size:12px;color:var(--t3);font-variant-numeric:tabular-nums}
.d-prog .track{flex:1;height:4px;border-radius:4px;background:var(--line);overflow:hidden}
.d-prog .track i{display:block;height:100%;width:0;border-radius:inherit;background:var(--accent);transition:width .5s var(--ease)}
.d-prog span{min-width:44px;text-align:right}
.stage{position:relative;flex:1;min-height:0;width:100%;max-width:520px;margin:0 auto}
.d-ctl{display:flex;align-items:center;justify-content:center;gap:20px;padding:4px 16px 14px}
.d-ctl .icon-btn{width:52px;height:52px;border-radius:50%}
.d-ctl .icon-btn .ico{width:22px;height:22px}
.act{height:52px;min-width:136px;display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:0 22px;border:0;border-radius:999px;
  background:var(--t1);color:var(--bg);font-size:15px;font-weight:650;box-shadow:var(--shadow);transition:transform .18s var(--ease)}
.act:active{transform:scale(.94)}
.act .ico{transition:transform .6s var(--ease)}
.act.on .ico{transform:rotate(180deg)}

.card{position:absolute;top:4px;left:16px;right:16px;bottom:34px;transform-origin:50% 100%;perspective:1800px;
  touch-action:pan-y pinch-zoom;transition:transform .5s var(--ease),opacity .4s var(--ease),visibility 0s}
.card[data-pos="0"]{z-index:5}
.card[data-pos="1"]{z-index:4;transform:translateY(14px) scale(.95)}
.card[data-pos="2"]{z-index:3;transform:translateY(27px) scale(.9);opacity:.55}
.card[data-pos="3"]{z-index:2;transform:translateY(36px) scale(.86);opacity:0}
.card[data-pos="-1"]{z-index:6;transform:translateX(-135%) rotate(-10deg);opacity:0;visibility:hidden;
  transition:transform .5s var(--ease),opacity .45s ease-in,visibility 0s linear .5s}
.stage.dragging .card{transition:none}
.stage.dragging{-webkit-user-select:none;user-select:none;cursor:grabbing}
.card.deal{animation:deal .6s var(--ease) both;animation-delay:var(--d,0ms)}
.card.bump-l{animation:bumpL .42s var(--ease)}
.card.bump-r{animation:bumpR .42s var(--ease)}
@keyframes deal{from{opacity:0;translate:0 70px}}
@keyframes bumpL{30%{translate:-20px 0}}
@keyframes bumpR{30%{translate:20px 0}}
.flipper{position:absolute;inset:0;transform-style:preserve-3d;transition:transform .75s var(--spring)}
.card.flipped .flipper{transform:rotateY(180deg)}
.face{position:absolute;inset:0;display:flex;flex-direction:column;padding:20px 20px 18px;border-radius:26px;
  background:var(--card);border:1px solid var(--line);box-shadow:var(--shadow-lg);overflow-x:hidden;overflow-y:auto;
  overscroll-behavior:contain;-webkit-overflow-scrolling:touch;scrollbar-width:none;
  -webkit-backface-visibility:hidden;backface-visibility:hidden;transition:visibility 0s linear .2s}
.face::-webkit-scrollbar{display:none}
.face>*{flex-shrink:0;transition:opacity .35s var(--ease)}
/* 叠在后面的牌只露一道边，内容先藏起来，免得边缘透出一截文字；拖动时下一张提前显出来 */
.card[data-pos="1"]:not(.peek) .face>*,.card[data-pos="2"] .face>*,.card[data-pos="3"] .face>*{opacity:0}
.back{transform:rotateY(180deg);visibility:hidden}
.card.flipped .front{visibility:hidden}
.card.flipped .back{visibility:inherit}

.c-top{display:flex;align-items:center;gap:8px;margin-bottom:12px;font-size:12px;color:var(--t3);min-width:0}
.c-no{flex:none;padding:5px 9px;border-radius:9px;font:700 12px/1 var(--mono);
  background:hsl(var(--h) var(--tint-s) var(--tint-l));color:hsl(var(--h) var(--ink-s) var(--ink-l))}
.c-sec{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.c-title{margin:0 0 12px;font-size:21px;font-weight:700;line-height:1.45;letter-spacing:-.01em;text-wrap:pretty}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.badge,.tag{display:inline-flex;align-items:center;font:600 12px/1 var(--font);padding:6px 10px;border-radius:999px}
.gA{background:var(--gA-s);color:var(--gA)}.gB{background:var(--gB-s);color:var(--gB)}.gC{background:var(--gC-s);color:var(--gC)}
.r0{background:var(--brand);color:var(--brand-ink)}.r1{background:var(--brand-soft);color:var(--brand)}.r2{background:var(--gC-s);color:var(--gC)}
.tag{font-weight:500;background:var(--card-2);color:var(--t3);box-shadow:inset 0 0 0 1px var(--line)}
.cost{display:grid;grid-template-columns:repeat(auto-fit,minmax(0,1fr));margin-bottom:14px;border:1px solid var(--line);border-radius:16px;overflow:hidden}
.cost span{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:7px 2px 8px;font-size:15px;font-weight:700;line-height:1.3}
.cost span+span{border-left:1px solid var(--line)}
.cost i{font-style:normal;font-size:11px;font-weight:500;color:var(--t3);margin-bottom:1px;white-space:nowrap}
.w0{color:var(--w0)}.w1{color:var(--w1)}.w2{color:var(--w2)}
.cost .gain{background:var(--brand-soft);color:var(--brand)}
.plain{margin:0;padding:14px 16px 15px;border-radius:18px;background:hsl(var(--h) var(--tint-s) var(--tint-l))}
.plain .lbl{display:flex;align-items:center;gap:6px;margin-bottom:4px;font-size:12px;font-weight:700;letter-spacing:.12em;color:hsl(var(--h) var(--ink-s) var(--ink-l))}
.plain .lbl::before{content:"";width:14px;height:2px;border-radius:2px;background:currentColor}
.plain p{margin:0;font-size:16.5px;line-height:1.85;overflow-wrap:anywhere}
.c-hint{margin-top:auto;padding-top:16px;display:flex;align-items:center;justify-content:center;gap:6px;font-size:12px;color:var(--t3)}
.c-hint .ico{width:15px;height:15px}
.card[data-pos="0"] .c-hint.swipe .ico{animation:nudge 1.6s var(--ease) infinite}
@keyframes nudge{0%,100%{translate:0}50%{translate:-6px 0}}

.b-head{display:flex;align-items:center;gap:10px;margin:-2px 0 4px;padding-bottom:12px;border-bottom:1px solid var(--line);cursor:pointer}
.b-t{flex:1;min-width:0;font-size:14px;font-weight:650;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.b-flip{flex:none;display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:600;color:var(--t3)}
.b-flip .ico{width:14px;height:14px}
.fields{margin:0}
.f{padding:12px 0;border-bottom:1px dashed var(--line)}
.f:last-child{border-bottom:0}
.f dt{display:flex;align-items:center;gap:8px;margin-bottom:3px;font-size:12px;font-weight:700;letter-spacing:.12em;color:hsl(var(--h) var(--ink-s) var(--ink-l))}
.f.note dt{color:var(--gB)}
.f dt .badge{letter-spacing:0;padding:4px 8px;font-size:11px}
.f dd{margin:0;font-size:14.5px;line-height:1.8;color:var(--t2);overflow-wrap:anywhere}
.src{margin-top:8px;padding:0 14px;border-radius:16px;background:var(--card-2);border:1px solid var(--line)}
.src summary{display:flex;align-items:center;justify-content:space-between;padding:12px 0;list-style:none;font-size:13px;font-weight:600;color:var(--t2);cursor:pointer}
.src summary::-webkit-details-marker{display:none}
.src summary .ico{width:16px;height:16px;color:var(--t3);transition:transform .3s var(--ease)}
.src[open] summary .ico{transform:rotate(180deg)}
.src .sbody{padding-bottom:12px;font-size:12.5px;line-height:1.8;color:var(--t3);overflow-wrap:anywhere}
.src[open] .sbody{animation:fade .35s var(--ease)}
@keyframes fade{from{opacity:0;translate:0 -4px}}

.cover .face{background:linear-gradient(165deg,hsl(var(--h) var(--tint-s) var(--tint-l)) 0%,var(--card) 58%)}
.cv-k{font-size:12px;font-weight:600;letter-spacing:.08em;color:hsl(var(--h) var(--ink-s) var(--ink-l))}
.cv-no{margin-top:10px;font:700 64px/1 var(--serif);color:hsl(var(--h) var(--ink-s) var(--ink-l));letter-spacing:-.03em}
.cv-t{margin:10px 0 14px;font:700 27px/1.3 var(--serif)}
.cv-f{margin:-4px 0 14px;font-size:12.5px;color:var(--t3)}
.cv-stats{display:flex;gap:8px;margin-bottom:16px}
.cv-stats span{flex:1;padding:10px 4px;border-radius:16px;background:var(--card);border:1px solid var(--line);text-align:center;font-size:11.5px;color:var(--t3);line-height:1.4}
.cv-stats b{display:block;font:700 22px/1.2 var(--font);color:var(--t1);font-variant-numeric:tabular-nums}
.cv-in p{margin:0 0 10px;font-size:14px;line-height:1.85;color:var(--t2)}
.cv-in p:last-child{margin-bottom:0}
.jl{display:inline;padding:0 1px;border:0;background:none;color:hsl(var(--h) var(--ink-s) var(--ink-l));font:inherit;font-weight:600;
  text-decoration:underline;text-decoration-style:dotted;text-underline-offset:3px;cursor:pointer;-webkit-user-select:text;user-select:text}

.end .face{align-items:center;justify-content:center;text-align:center;padding:28px 22px}
.ok{width:76px;height:76px;border-radius:50%;display:grid;place-items:center;background:hsl(var(--h) var(--ink-s) var(--ink-l));color:var(--card)}
.ok .ico{width:36px;height:36px;stroke-width:2.6}
.card[data-pos="0"].end .ok{animation:pop .7s .15s var(--spring) both}
@keyframes pop{from{opacity:0;scale:.4}}
.end-t{margin:18px 0 6px;font:700 24px/1.35 var(--serif)}
.end-s{margin:0 0 22px;font-size:14px;color:var(--t2);line-height:1.8}
.end-acts{display:flex;flex-direction:column;gap:10px;width:100%;max-width:300px}
.end-acts button{display:flex;align-items:center;justify-content:center;gap:8px;min-height:48px;padding:10px 16px;border-radius:16px;
  border:1px solid var(--line);background:var(--card-2);font-size:14.5px;font-weight:600;line-height:1.4;transition:transform .18s var(--ease)}
.end-acts button:active{transform:scale(.96)}
.end-acts .pri{background:var(--t1);border-color:var(--t1);color:var(--bg)}
.end-acts .ico{width:17px;height:17px}

/* ---------- 本组目录（底部抽屉） ---------- */
.sheet{position:fixed;inset:0;z-index:80;visibility:hidden;transition:visibility 0s linear .4s}
.sheet.open{visibility:visible;transition:none}
.sheet-bg{position:absolute;inset:0;background:rgba(10,10,10,.42);opacity:0;transition:opacity .3s var(--ease)}
.sheet.open .sheet-bg{opacity:1}
.sheet-panel{position:absolute;left:0;right:0;bottom:0;max-width:560px;max-height:78vh;max-height:78dvh;margin:0 auto;display:flex;flex-direction:column;
  border-radius:24px 24px 0 0;background:var(--card);box-shadow:0 -10px 40px rgba(0,0,0,.2);padding-bottom:env(safe-area-inset-bottom);
  transform:translateY(100%);transition:transform .42s var(--ease)}
.sheet.open .sheet-panel{transform:none}
.sheet-h{display:flex;align-items:center;gap:10px;padding:8px 12px 8px 20px;border-bottom:1px solid var(--line)}
.sheet-h::before{content:"";position:absolute;top:7px;left:50%;width:38px;height:4px;margin-left:-19px;border-radius:4px;background:var(--line)}
.sheet-h h3{flex:1;min-width:0;margin:12px 0 4px;font-size:15px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sheet-h small{font-weight:400;color:var(--t3);margin-left:6px}
.sheet-list{overflow-y:auto;overscroll-behavior:contain;padding:6px 8px 14px}
.row{display:flex;align-items:baseline;gap:10px;width:100%;padding:10px 12px;border:0;border-radius:12px;background:none;text-align:left;font-size:14px;line-height:1.5;color:var(--t2)}
.row:active{background:var(--card-2)}
.row.on{background:var(--brand-soft);color:var(--brand);font-weight:600}
.row i{flex:none;min-width:24px;font-style:normal;text-align:right;color:var(--t3);font-size:12px;font-variant-numeric:tabular-nums}
.row .g{flex:none;margin-left:auto;font-size:11px;color:var(--t3)}
.dot{flex:none;width:7px;height:7px;border-radius:50%;translate:0 -2px}
.d0{background:var(--brand)}.d1{background:var(--gA)}.d2{background:var(--t3);opacity:.4}

.toast{position:fixed;left:50%;bottom:calc(env(safe-area-inset-bottom) + 96px);z-index:90;max-width:86vw;padding:10px 16px;border-radius:999px;
  background:var(--t1);color:var(--bg);font-size:13px;pointer-events:none;opacity:0;translate:-50% 10px;transition:opacity .25s,translate .35s var(--ease)}
.toast.show{opacity:1;translate:-50% 0}
.nojs{margin:12px 0;padding:12px 16px;border-radius:14px;background:var(--gB-s);color:var(--gB);font-size:13px}

@media (max-height:700px){
  .c-title{font-size:19px;margin-bottom:10px}
  .plain p{font-size:15.5px;line-height:1.8}
  .chips{margin-bottom:10px}.cost{margin-bottom:10px}
  .face{padding:16px 16px 14px}
  .d-ctl{padding-bottom:10px}.d-ctl .icon-btn,.act{height:48px}.d-ctl .icon-btn{width:48px}
  .cv-no{font-size:52px}
}
@media (max-width:360px){
  .hero h1{font-size:26px}
  .card{left:12px;right:12px}
  .d-ctl{gap:12px}.act{min-width:120px;padding:0 16px}
}
@media (min-width:700px){
  .home{padding-left:28px;padding-right:28px}
  .tools{margin:0 -28px;padding-left:28px;padding-right:28px}
  .hero h1{font-size:36px}
  .grid{grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms!important;animation-delay:0s!important;animation-iteration-count:1!important}
  .card{transition:opacity .2s!important}
  .flipper{transition:none!important}
  .face{transition:none!important}
}
@media print{
  .tools,.resume,.hits,.deck,.sheet,.toast{display:none!important}
  .tile{break-inside:avoid;animation:none}
}
"""

DARK = ("--bg:#131315;--card:#1d1d21;--card-2:#25252a;--line:#303036;"
        "--t1:#ecebe7;--t2:#b6b2aa;--t3:#7f7b74;"
        "--brand:#5cc69a;--brand-ink:#0b1f17;--brand-soft:rgba(92,198,154,.13);--brand-line:rgba(92,198,154,.38);"
        "--gA:#5fd394;--gA-s:rgba(95,211,148,.13);--gB:#f0b35a;--gB-s:rgba(240,179,90,.14);"
        "--gC:#a3a7ae;--gC-s:rgba(163,167,174,.14);"
        "--w0:#5fd394;--w1:#f0b35a;--w2:#f4847a;--mark:rgba(250,204,21,.32);"
        "--ink-s:62%;--ink-l:72%;--tint-s:26%;--tint-l:17%;"
        "--shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -10px rgba(0,0,0,.7);"
        "--shadow-lg:0 1px 3px rgba(0,0,0,.4),0 22px 44px -18px rgba(0,0,0,.8);color-scheme:dark")

CSS = CSS.replace("%DARK%", DARK)

# 行内 SVG 图标（stroke 风格，24 网格）。JS 里也会用到同一套。
ICON = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "theme": '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5a8.5 8.5 0 0 0 0 17z" fill="currentColor"/>',
    "left": '<path d="M15 5l-7 7 7 7"/>',
    "right": '<path d="M9 5l7 7-7 7"/>',
    "down": '<path d="M6 9l6 6 6-6"/>',
    "flip": '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 3v5h5"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 21v-5h-5"/>',
    "shuffle": '<path d="M16 3h5v5"/><path d="M4 20L21 3"/><path d="M21 16v5h-5"/><path d="M15 15l6 6"/><path d="M4 4l5 5"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "grid": '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
}


def svg(name):
    return '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">%s</svg>' % ICON[name]


JS = r"""
(function(){
'use strict';
const $=(s,r)=>(r||document).querySelector(s);
const $$=(s,r)=>[...(r||document).querySelectorAll(s)];
const D=JSON.parse($('#data').textContent);
const SECS=D.secs, ITEMS=D.items, SEC=new Map();
SECS.forEach(s=>{s.idx=[];SEC.set(s.n,s);});
ITEMS.forEach((it,i)=>SEC.get(it.s).idx.push(i));
const root=document.documentElement, body=document.body;
const home=$('#home'), deckEl=$('#deck'), stage=$('#stage'), sheet=$('#sheet'), sheetList=$('#sheet-list');
const q=$('#q'), clr=$('#clr'), tiles=$$('.tile');
const I=n=>'<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">'+D.icon[n]+'</svg>';
const pad=n=>String(n).padStart(2,'0');
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ENT={'&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"','&#x27;':"'"};
const strip=h=>(h||'').replace(/<[^>]+>/g,'').replace(/&(?:amp|lt|gt|quot|#x27);/g,m=>ENT[m]);
const GL={A:'gA',B:'gB',C:'gC'}, RN=['极高','高','一般'];
const FL={A:'只看 A 级',hi:'高性价比'};

/* ---- 本地记忆：阅读进度、明暗主题（读写失败也不影响使用） ---- */
function load(k,d){try{const v=localStorage.getItem(k);return v?JSON.parse(v):d;}catch(e){return d;}}
function keep(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}
let POS=load('hltb-pos',{});
if(!POS||typeof POS!=='object') POS={};

const mq=window.matchMedia?matchMedia('(prefers-color-scheme: dark)'):null;
function theme(){return root.getAttribute('data-theme')||(mq&&mq.matches?'dark':'light');}
function paintMeta(){
  const c=getComputedStyle(root).getPropertyValue('--bg').trim();
  $$('meta[name=theme-color]').forEach(m=>m.setAttribute('content',c));
}
function toggleTheme(){
  const t=theme()==='dark'?'light':'dark';
  root.setAttribute('data-theme',t);
  try{localStorage.setItem('hltb-theme',t);}catch(e){}
  paintMeta();
}
$$('[data-theme-btn]').forEach(b=>b.addEventListener('click',toggleTheme));
paintMeta();

/* ---- 搜索与筛选 ---- */
let filt='all', term='', TXT=null;
function text(i){
  if(!TXT) TXT=ITEMS.map(it=>[it.t,it.p,it.m,it.src].concat(it.f.map(f=>f[1])).map(strip).join(' ').toLowerCase());
  return TXT[i];
}
function pass(i){
  const it=ITEMS[i];
  if(filt==='A'&&it.g!=='A') return false;
  if(filt==='hi'&&it.r>1) return false;
  return !term||text(i).includes(term);
}
function active(){return filt!=='all'||!!term;}
function desc(){
  const a=[]; if(term) a.push('「'+esc(term)+'」'); if(filt!=='all') a.push(FL[filt]);
  return a.join(' · ');
}
function refreshHome(){
  const on=active(); let tot=0, secs=0;
  tiles.forEach(t=>{
    const s=SEC.get(+t.dataset.n), k=on?s.idx.filter(pass).length:s.idx.length;
    tot+=k; if(k) secs++;
    $('.t-cnt',t).textContent=on?(k+' / '+s.idx.length+' 条'):(s.idx.length+' 条');
    t.classList.toggle('none',k===0); t.disabled=(k===0);
  });
  const h=$('#hits');
  h.classList.toggle('hidden',!on);
  if(on){
    $('#hits-t').innerHTML=tot?(desc()+'<br><b>'+tot+'</b> 条，分布在 '+secs+' 节'):(desc()+'<br>没有符合的建议');
    $('#hits-go').classList.toggle('hidden',!tot);
  }
  $('#grid-c').textContent=on?('筛出 '+tot+' 条'):(ITEMS.length+' 条');
}
let tm=0;
function onQ(){
  clr.classList.toggle('hidden',!q.value);
  clearTimeout(tm);
  tm=setTimeout(()=>{term=q.value.trim().toLowerCase();refreshHome();},120);
}
q.addEventListener('input',onQ);
clr.addEventListener('click',()=>{q.value='';onQ();q.focus();});
$('#sform').addEventListener('submit',e=>{e.preventDefault();q.blur();});
$$('[data-f]').forEach(b=>b.addEventListener('click',()=>{
  filt=b.dataset.f;
  $$('[data-f]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
  refreshHome();
}));

/* ---- 阅读进度：每节记住看到第几条，0 = 封面，-1 = 读完 ---- */
function progOf(n){
  const s=SEC.get(n), v=POS[n];
  if(v===-1) return 1;
  if(!v) return 0;
  const j=s.idx.findIndex(i=>ITEMS[i].no===v);
  return j<0?0:(j+1)/s.idx.length;
}
function refreshProg(){
  tiles.forEach(t=>{
    const n=+t.dataset.n;
    t.style.setProperty('--p',(progOf(n)*100).toFixed(1)+'%');
    t.classList.toggle('done',POS[n]===-1);
  });
  const r=$('#resume'), last=load('hltb-last',null), s=SEC.get(last);
  if(s&&POS[last]>0){
    const j=s.idx.findIndex(i=>ITEMS[i].no===POS[last]);
    if(j>=0){
      r.dataset.n=last;
      $('#r-sec').textContent=pad(s.n)+' · '+s.t;
      $('#r-at').textContent='第 '+(j+1)+' / '+s.idx.length+' 条：'+strip(ITEMS[s.idx[j]].t);
      r.classList.remove('hidden');
      return;
    }
  }
  r.classList.add('hidden');
}

/* ---- 牌组 ---- */
let deck=null, opener=null;
const live=new Map();
function mkDeck(kind,idxs,o){
  const list=[]; if(kind==='sec') list.push({k:'cover'});
  idxs.forEach(i=>list.push({k:'item',i}));
  list.push({k:'end'});
  let ord=0; list.forEach(e=>{if(e.k==='item') e.o=++ord;});
  return Object.assign({kind,list,count:ord,i:0},o);
}
function openSec(n,start,mode){
  const s=SEC.get(n);
  const d=mkDeck('sec',s.idx.filter(pass),{n,h:s.h,title:pad(n)+' '+s.t});
  if(start==null){const v=POS[n]; start=(v>0)?v:0;}
  let at=0;
  if(start>0){
    at=d.list.findIndex(e=>e.k==='item'&&ITEMS[e.i].no===start);
    if(at<0) at=d.list.findIndex(e=>e.k==='item'&&ITEMS[e.i].no>start);
    if(at<0) at=0;
  }
  show(d,at,mode);
}
function openList(kind,idxs,title){show(mkDeck(kind,idxs,{h:null,title}),0,'push');}
function hashOf(){
  if(!deck) return '';
  if(deck.kind!=='sec') return '#'+deck.kind;
  const e=deck.list[deck.i];
  return e.k==='item'?('#s'+deck.n+'-'+ITEMS[e.i].no):('#sec'+deck.n);
}
function show(d,at,mode){
  const was=!!deck;
  deck=d; deck.i=at;
  stage.textContent=''; live.clear();
  deckEl.style.setProperty('--accent',d.h==null?'var(--brand)':'hsl('+d.h+' var(--ink-s) var(--ink-l))');
  $('#d-name').textContent=d.title;
  if(!was){
    body.classList.add('reading');
    home.inert=true; deckEl.inert=false; deckEl.removeAttribute('aria-hidden');
  }
  layout(was?'jump':'open');
  chrome(); save();
  if(mode==='push') history.pushState({deck:1},'',hashOf());
  else if(mode==='replace') history.replaceState({deck:1},'',hashOf());
}
function closeDeck(){
  if(!deck) return;
  deck=null; closeSheet();
  body.classList.remove('reading');
  home.inert=false; deckEl.inert=true; deckEl.setAttribute('aria-hidden','true');
  refreshProg();
  setTimeout(()=>{if(!deck){stage.textContent='';live.clear();}},460);
  if(opener&&document.contains(opener)) try{opener.focus({preventScroll:true});}catch(e){}
}
function back(){
  if(history.state&&history.state.deck) history.back();
  else{closeDeck();history.replaceState(null,'',location.pathname+location.search);}
}
function save(){
  if(!deck||deck.kind!=='sec') return;
  const e=deck.list[deck.i];
  POS[deck.n]=e.k==='item'?ITEMS[e.i].no:(e.k==='end'?-1:0);
  keep('hltb-pos',POS); keep('hltb-last',deck.n);
}

/* 只在 DOM 里保留当前牌前后几张：-1 是飞出去的上一张，1~2 是叠在后面的，3 是透明的预备位 */
function layout(deal){
  const i=deck.i, L=deck.list;
  for(const [k,el] of live) if(k<i-1||k>i+3){el.remove();live.delete(k);}
  for(let k=Math.max(0,i-1);k<=Math.min(L.length-1,i+3);k++){
    const pos=k-i; let el=live.get(k);
    if(!el){
      el=build(L[k]); live.set(k,el);
      el.dataset.pos=(!deal&&pos>0)?Math.min(pos+1,3):pos;
      stage.appendChild(el);
      if(deal&&pos>=0&&pos<3){
        el.style.setProperty('--d',(pos*80+(deal==='open'?120:0))+'ms');
        el.classList.add('deal');
        el.addEventListener('animationend',function f(ev){if(ev.target===el){el.classList.remove('deal');el.removeEventListener('animationend',f);}});
      }else void el.offsetWidth;
    }
    el.dataset.pos=pos;
    el.inert=(pos!==0);
    if(pos===0) el.removeAttribute('aria-hidden'); else el.setAttribute('aria-hidden','true');
  }
}
function chrome(){
  const e=deck.list[deck.i], el=live.get(deck.i), fl=!!(el&&el.classList.contains('flipped'));
  $('#d-pos').textContent=e.k==='item'?(e.o+' / '+deck.count):(e.k==='cover'?'导读':'完');
  $('#d-bar').style.width=(e.k==='item'?e.o/deck.count*100:(e.k==='end'?100:0))+'%';
  $('#prev').disabled=deck.i===0;
  $('#next').disabled=deck.i===deck.list.length-1;
  const a=$('#act');
  a.classList.toggle('on',fl);
  if(e.k==='cover') a.innerHTML='开始翻看'+I('arrow');
  else if(e.k==='end') a.innerHTML=I('grid')+'回到目录';
  else a.innerHTML=I('flip')+(fl?'看正面':'看详情');
}
function go(d){
  if(!deck) return;
  const j=deck.i+d;
  if(j<0||j>=deck.list.length){bump(d);return;}
  deck.i=j; layout(false); chrome(); save();
  if(deck.kind==='sec') history.replaceState(history.state,'',hashOf());
}
function jump(k){
  if(!deck||k===deck.i) return;
  if(Math.abs(k-deck.i)===1) return go(k-deck.i);
  deck.i=k; stage.textContent=''; live.clear();
  layout('jump'); chrome(); save();
  if(deck.kind==='sec') history.replaceState(history.state,'',hashOf());
}
function bump(d){
  const el=live.get(deck.i); if(!el) return;
  el.classList.remove('bump-l','bump-r'); void el.offsetWidth;
  el.classList.add(d>0?'bump-l':'bump-r');
  el.addEventListener('animationend',()=>el.classList.remove('bump-l','bump-r'),{once:true});
}
function flip(){
  const el=live.get(deck.i);
  if(!el||!el.classList.contains('item')) return;
  if(el.classList.toggle('flipped')) $('.back',el).scrollTop=0;
  else $('.front',el).scrollTop=0;
  chrome();
}
function act(){
  const e=deck.list[deck.i];
  if(e.k==='cover') go(1); else if(e.k==='end') back(); else flip();
}

/* ---- 生成卡片 DOM ---- */
function shell(cls,h){
  const el=document.createElement('article');
  el.className='card '+cls;
  el.style.setProperty('--h',h==null?155:h);
  return el;
}
function buildItem(i){
  const it=ITEMS[i], s=SEC.get(it.s), el=shell('item',s.h);
  const no='<span class="c-no">No.'+it.no+'</span>';
  let chips='<span class="badge '+(GL[it.g]||'gC')+'">'+esc(it.g)+' 级证据</span>';
  if(it.r<3) chips+='<span class="badge r'+it.r+'">性价比 '+RN[it.r]+'</span>';
  if(it.k) chips+='<span class="tag">口径 · '+esc(it.k)+'</span>';
  let cost='';
  if(it.c.length||it.y){
    cost='<div class="cost">'+it.c.map(c=>'<span class="w'+c[2]+'"><i>'+esc(c[0])+'</i>'+esc(c[1])+'</span>').join('')
      +(it.y?'<span class="gain"><i>收益</i>'+esc(it.y)+'</span>':'')+'</div>';
  }
  const rows=it.f.map(f=>'<div class="f"><dt>'+f[0]+'</dt><dd>'+f[1]+'</dd></div>').join('')
    +(it.m?'<div class="f note"><dt>备注</dt><dd>'+it.m+'</dd></div>':'');
  const src=it.src?('<details class="src"><summary><span>来源'+(it.sn?'（'+it.sn+' 条文献）':'')+'</span>'+I('down')+'</summary><div class="sbody">'+it.src+'</div></details>'):'';
  el.innerHTML='<div class="flipper"><div class="face front">'
    +'<div class="c-top">'+no+'<span class="c-sec">'+pad(s.n)+' · '+esc(s.t)+'</span></div>'
    +'<h2 class="c-title">'+it.t+'</h2><div class="chips">'+chips+'</div>'+cost
    +(it.p?'<div class="plain"><div class="lbl">说人话</div><p>'+it.p+'</p></div>':'')
    +'<div class="c-hint">'+I('flip')+'轻点卡片，翻面看成本、收益与出处</div></div>'
    +'<div class="face back"><div class="b-head" title="翻回正面">'+no+'<span class="b-t">'+strip(it.t)+'</span><span class="b-flip">'+I('flip')+'正面</span></div>'
    +'<dl class="fields"><div class="f"><dt>证据等级 <span class="badge '+(GL[it.g]||'gC')+'">'+esc(it.g)+' 级</span></dt></div>'+rows+'</dl>'+src+'</div></div>';
  if(term) markAll(el,term);
  return el;
}
function buildCover(){
  const s=SEC.get(deck.n), el=shell('cover',s.h);
  const its=deck.list.filter(e=>e.k==='item').map(e=>ITEMS[e.i]);
  const a=its.filter(x=>x.g==='A').length, hi=its.filter(x=>x.r<=1).length;
  el.innerHTML='<div class="flipper"><div class="face front">'
    +'<div class="cv-k">第 '+s.n+' 节 · 共 '+SECS.length+' 节</div>'
    +'<div class="cv-no">'+pad(s.n)+'</div><h2 class="cv-t">'+esc(s.t)+'</h2>'
    +(active()?'<p class="cv-f">已筛选 '+desc()+'：'+deck.count+' / '+s.idx.length+' 条</p>':'')
    +'<div class="cv-stats"><span><b>'+deck.count+'</b>条建议</span><span><b>'+a+'</b>A 级证据</span><span><b>'+hi+'</b>高性价比</span></div>'
    +(s.in.length?'<div class="cv-in">'+s.in.join('')+'</div>':'')
    +'<div class="c-hint swipe">'+I('left')+'向左滑动，开始翻卡</div></div></div>';
  return el;
}
function buildEnd(){
  const el=shell('end',deck.h);
  let nx='';
  if(deck.kind==='sec'){
    const k=SECS.findIndex(s=>s.n===deck.n);
    for(let j=k+1;j<SECS.length;j++){
      const s=SECS[j];
      if(s.idx.some(pass)){nx='<button class="pri" data-act="next" data-n="'+s.n+'">下一节 · '+pad(s.n)+' '+esc(s.t)+I('arrow')+'</button>';break;}
    }
  }
  el.innerHTML='<div class="flipper"><div class="face front"><div class="ok">'+I('check')+'</div>'
    +'<h2 class="end-t">'+(deck.kind==='sec'?'第 '+deck.n+' 节翻完了':'这一组翻完了')+'</h2>'
    +'<p class="end-s">'+deck.count+' 条建议都过了一遍。<br>挑一条最容易做到的，今天就开始。</p>'
    +'<div class="end-acts">'+nx+'<button data-act="restart">'+I('flip')+'从头再翻</button></div></div></div>';
  return el;
}
function build(e){return e.k==='item'?buildItem(e.i):(e.k==='cover'?buildCover():buildEnd());}

function markAll(rootEl,t){
  const w=document.createTreeWalker(rootEl,NodeFilter.SHOW_TEXT,{acceptNode(n){
    if(!n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
    const p=n.parentElement;
    if(!p||p.closest('mark,a,.c-no,.lbl')) return NodeFilter.FILTER_REJECT;
    return NodeFilter.FILTER_ACCEPT;
  }});
  const nodes=[]; while(w.nextNode()) nodes.push(w.currentNode);
  nodes.forEach(n=>{
    const raw=n.nodeValue.toLowerCase();
    let i=raw.indexOf(t); if(i<0) return;
    const frag=document.createDocumentFragment(); let last=0;
    while(i>=0){
      frag.appendChild(document.createTextNode(n.nodeValue.slice(last,i)));
      const m=document.createElement('mark'); m.textContent=n.nodeValue.slice(i,i+t.length);
      frag.appendChild(m); last=i+t.length; i=raw.indexOf(t,last);
    }
    frag.appendChild(document.createTextNode(n.nodeValue.slice(last)));
    n.replaceWith(frag);
  });
}

/* ---- 手势：横向拖动翻牌，纵向留给卡片内滚动 ---- */
let g=null, noClick=0;
const rub=(x,w)=>x/(1+Math.abs(x)/(w*.45))*.55;
function T(el,tf,op){if(!el) return; el.style.transform=tf; el.style.opacity=op==null?'':op;}
function drag(dx){
  const i=deck.i, w=g.w, cur=g.cur, L=deck.list;
  const n1=live.get(i+1), n2=live.get(i+2), pv=live.get(i-1);
  if(dx<=0){
    if(pv){T(pv,'');pv.style.visibility='';}
    if(i<L.length-1){
      const p=Math.min(1,-dx/w);
      if(n1) n1.classList.add('peek');
      T(cur,'translateX('+dx+'px) rotate('+(dx/w*10)+'deg)');
      T(n1,'translateY('+(14*(1-p))+'px) scale('+(.95+.05*p)+')');
      T(n2,'translateY('+(27-13*p)+'px) scale('+(.9+.05*p)+')',.55+.45*p);
    }else T(cur,'translateX('+rub(dx,w)+'px)');
  }else{
    T(n1,''); T(n2,''); if(n1) n1.classList.remove('peek');
    if(pv){
      const p=Math.min(1,dx/w);
      pv.style.visibility='visible';
      T(pv,'translateX('+(-1.35*w*(1-p))+'px) rotate('+(-10*(1-p))+'deg)',Math.min(1,p*2));
      T(cur,'translateY('+(14*p)+'px) scale('+(1-.05*p)+')');
    }else T(cur,'translateX('+rub(dx,w)+'px)');
  }
}
stage.addEventListener('pointerdown',e=>{
  if(!deck||g||(e.pointerType==='mouse'&&e.button!==0)) return;
  const cur=live.get(deck.i);
  if(!cur||!cur.contains(e.target)||e.target.closest('input,select,textarea')) return;
  g={id:e.pointerId,x0:e.clientX,y0:e.clientY,dx:0,on:false,cur,w:cur.offsetWidth||stage.clientWidth,s:[[e.timeStamp,e.clientX]]};
});
stage.addEventListener('pointermove',e=>{
  if(!g||e.pointerId!==g.id) return;
  const dx=e.clientX-g.x0, dy=e.clientY-g.y0;
  if(!g.on){
    if(Math.abs(dy)>10&&Math.abs(dy)>Math.abs(dx)){g=null;return;}
    if(Math.abs(dx)<10||Math.abs(dx)<Math.abs(dy)*1.2) return;
    g.on=true; g.x0+=dx>0?10:-10;
    stage.classList.add('dragging');
    try{stage.setPointerCapture(e.pointerId);}catch(_){}
    if(e.pointerType==='mouse'){const s=window.getSelection&&getSelection(); if(s) s.removeAllRanges();}
  }
  e.preventDefault();
  g.dx=e.clientX-g.x0;
  g.s.push([e.timeStamp,e.clientX]); if(g.s.length>6) g.s.shift();
  drag(g.dx);
});
function endDrag(e){
  if(!g||e.pointerId!==g.id) return;
  const G=g; g=null;
  if(!G.on) return;
  stage.classList.remove('dragging');
  noClick=Date.now()+320;
  const last=G.s[G.s.length-1]; let first=G.s[0];
  for(const s of G.s) if(last[0]-s[0]<=110){first=s;break;}
  const v=last[0]>first[0]?(last[1]-first[1])/(last[0]-first[0]):0;
  const i=deck.i; let d=0;
  if(e.type!=='pointercancel'){
    if(G.dx<0&&i<deck.list.length-1&&(G.dx<-G.w*.25||(v<-.45&&G.dx<-24))) d=1;
    if(G.dx>0&&i>0&&(G.dx>G.w*.25||(v>.45&&G.dx>24))) d=-1;
  }
  for(const el of live.values()){el.style.transform='';el.style.opacity='';el.style.visibility='';el.classList.remove('peek');}
  if(d) go(d);
}
stage.addEventListener('pointerup',endDrag);
stage.addEventListener('pointercancel',endDrag);
stage.addEventListener('touchmove',e=>{if(g&&g.on&&e.cancelable) e.preventDefault();},{passive:false});
stage.addEventListener('click',e=>{if(Date.now()<noClick){e.preventDefault();e.stopPropagation();}},true);
stage.addEventListener('click',e=>{
  if(!deck) return;
  const card=e.target.closest('.card');
  if(!card||card!==live.get(deck.i)) return;
  const b=e.target.closest('[data-act]');
  if(b){
    const v=b.dataset.act;
    if(v==='home') back(); else if(v==='restart') jump(0);
    else if(v==='next') openSec(+b.dataset.n,0,'replace');
    return;
  }
  const jl=e.target.closest('.jl');
  if(jl){
    const no=+jl.dataset.no, k=deck.list.findIndex(x=>x.k==='item'&&ITEMS[x.i].no===no);
    if(k>=0) jump(k); else toast('第 '+no+' 条不在当前筛选结果里');
    return;
  }
  if(e.target.closest('a,button,summary,.sbody,input')) return;
  if(window.getSelection&&String(getSelection())) return;
  if(!card.classList.contains('item')) return;
  if(!card.classList.contains('flipped')||e.target.closest('.b-head')) flip();
});

/* ---- 底部抽屉：本组卡片目录，点一下直接跳过去 ---- */
function openSheet(){
  if(!deck) return;
  $('#sheet-t').innerHTML=esc(deck.title)+'<small>'+deck.count+' 条</small>';
  sheetList.innerHTML=deck.list.map((e,k)=>{
    const on=k===deck.i?' on':'';
    if(e.k==='cover') return '<button class="row'+on+'" data-k="'+k+'"><i>·</i><span>导读</span></button>';
    if(e.k!=='item') return '';
    const it=ITEMS[e.i];
    const n=deck.kind==='sec'?it.no:(pad(it.s)+'·'+it.no);
    return '<button class="row'+on+'" data-k="'+k+'"><span class="dot d'+Math.min(it.r,2)+'"></span><i>'+n+'</i><span>'+esc(strip(it.t))+'</span><span class="g">'+esc(it.g)+'</span></button>';
  }).join('');
  sheet.classList.add('open'); sheet.inert=false; sheet.removeAttribute('aria-hidden');
  const on=$('.row.on',sheetList);
  sheetList.scrollTop=on?Math.max(0,on.offsetTop-sheetList.clientHeight/2+on.offsetHeight/2):0;
}
function closeSheet(){sheet.classList.remove('open'); sheet.inert=true; sheet.setAttribute('aria-hidden','true');}
sheetList.addEventListener('click',e=>{
  const b=e.target.closest('.row'); if(!b) return;
  closeSheet(); setTimeout(()=>jump(+b.dataset.k),120);
});
$('#sheet-bg').addEventListener('click',closeSheet);
$('#sheet-x').addEventListener('click',closeSheet);
$('#d-title').addEventListener('click',openSheet);

let tt=0;
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');clearTimeout(tt);tt=setTimeout(()=>t.classList.remove('show'),1900);}

/* ---- 按钮、键盘、浏览器返回键 ---- */
$('#prev').addEventListener('click',()=>go(-1));
$('#next').addEventListener('click',()=>go(1));
$('#act').addEventListener('click',act);
$('#back').addEventListener('click',back);
tiles.forEach(t=>t.addEventListener('click',()=>{opener=t;openSec(+t.dataset.n,null,'push');}));
$('#resume').addEventListener('click',e=>{opener=e.currentTarget;openSec(+e.currentTarget.dataset.n,null,'push');});
$('#hits-go').addEventListener('click',e=>{
  opener=e.currentTarget;
  openList('list',ITEMS.map((_,i)=>i).filter(pass),term?('搜索「'+q.value.trim()+'」'):FL[filt]);
});
$('#shuffle').addEventListener('click',e=>{
  opener=e.currentTarget;
  const a=ITEMS.map((_,i)=>i).filter(pass);
  for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]];}
  if(!a.length){toast('当前筛选下没有可翻的卡片');return;}
  openList('random',a.slice(0,30),'随机翻翻');
});
document.addEventListener('keydown',e=>{
  const tg=e.target;
  if(tg&&tg.closest&&tg.closest('input,textarea,select')){
    if(e.key==='Escape'&&tg===q){q.value='';onQ();q.blur();}
    return;
  }
  if(sheet.classList.contains('open')){if(e.key==='Escape') closeSheet(); return;}
  if(deck){
    if(e.key==='ArrowRight'){e.preventDefault();go(1);}
    else if(e.key==='ArrowLeft'){e.preventDefault();go(-1);}
    else if(e.key==='Escape') back();
    else if((e.key===' '||e.key==='Enter')&&!(tg&&tg.closest&&tg.closest('button,a,summary'))){e.preventDefault();act();}
  }else if(e.key==='/'){e.preventDefault();q.focus();}
});
function route(){
  const h=location.hash; let m;
  if((m=h.match(/^#s(\d+)-(\d+)$/))&&SEC.has(+m[1])) return {n:+m[1],no:+m[2]};
  if((m=h.match(/^#sec(\d+)$/))&&SEC.has(+m[1])) return {n:+m[1],no:0};
  return null;
}
addEventListener('popstate',()=>{
  const r=route();
  if(r){if(!deck||deck.kind!=='sec'||deck.n!==r.n) openSec(r.n,r.no,'none');}
  else if(deck) closeDeck();
});

refreshHome(); refreshProg();
deckEl.inert=true; sheet.inert=true;
/* 旧版页面的 #s1-3 / #sec1 链接照样能直接打开对应卡片；返回键回到目录而不是离开页面 */
const r0=route();
if(r0){history.replaceState(null,'',location.pathname+location.search);openSec(r0.n,r0.no,'push');}
else if(location.hash) history.replaceState(null,'',location.pathname+location.search);
})();
"""


def intro_html(lines):
    """导读段落。「**主题**：…（第 N 条）」这种分组行里的条号做成可点的跳转。"""
    out = []
    for ln in lines:
        h = inline(ln)
        if ln.startswith("**") and "<a " not in h:
            h = re.sub(r"(?<!节)第\s*(\d+)\s*条",
                       r'<button type="button" class="jl" data-no="\1">第 \1 条</button>', h)
        out.append("<p>%s</p>" % h)
    return out


def entry_data(e, sec_no):
    """一条建议 → 前端用的紧凑 JSON。HTML 片段在这里就转好，前端只拼接不解析 markdown。"""
    t = parse_tags(e["tags_raw"])
    f = e["fields"]
    grade = (f.get("证据等级") or "?").strip()[:1]
    ratio = ratio_of(t)
    cost = []
    for k, label in (("钱", "花钱"), ("时间", "花时间"), ("毅力", "要毅力")):
        if t.get(k):
            cost.append([label, t[k], COST_W[k].get(t[k], 1)])
    src = f.get("来源", "")
    return {
        "s": sec_no,
        "no": e["no"],
        "t": inline(e["title"]),
        "g": grade,
        "r": RATIO_ORDER[ratio] if ratio else 9,
        "c": cost,
        "y": t.get("收益", ""),
        "k": t.get("口径", ""),
        "p": inline(f.get("说人话", "")),
        "f": [[k, inline(f[k])] for k in ("成本", "收益") if f.get(k)],
        "m": inline(f["备注"]) if f.get("备注") else "",
        "src": inline(src) if src else "",
        "sn": link_count(src),
    }


def hue(n):
    # 黄金角错开色相，每节一个主色，相邻两节不会撞色
    return int(round((150 + n * 137.508) % 360))


def main():
    secs, items, tiles = [], [], []
    total = 0
    grade_cnt = {"A": 0, "B": 0, "C": 0}
    link_total = 0

    for pos, n in enumerate(SECTIONS):
        p = find_file(n)
        title, intro, entries = parse(p)
        name = re.sub(r"^\d+\.\s*", "", title).strip()
        a_cnt = hi_cnt = 0
        for e in entries:
            g = (e["fields"].get("证据等级") or "?").strip()[:1]
            if g in grade_cnt:
                grade_cnt[g] += 1
            if g == "A":
                a_cnt += 1
            if ratio_of(parse_tags(e["tags_raw"])) in ("极高", "高"):
                hi_cnt += 1
            total += 1
            link_total += link_count(e["fields"].get("来源", "")) + link_count(e["fields"].get("备注", ""))
            items.append(entry_data(e, n))
        secs.append({"n": n, "t": name, "h": hue(n), "in": intro_html(intro)})
        tiles.append(
            '<button class="tile" type="button" data-n="%d" style="--h:%d;--i:%d">'
            '<span class="t-no">%02d</span><span class="t-name">%s</span>'
            '<span class="t-meta"><span class="t-cnt">%d 条</span><span>A 级 %d</span></span>'
            '<span class="t-bar"><i></i></span></button>'
            % (n, hue(n), pos, n, html.escape(name), len(entries), a_cnt))

    rev, rev_date = source_rev()

    data = {"secs": secs, "items": items, "icon": ICON}
    # 统一把 < 转成 <：JSON 依旧合法，又不会有 </script> 或 <!-- 提前截断脚本块
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")

    head = ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="color-scheme" content="light dark">'
            '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#f4f1ec">'
            '<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#131315">'
            '<meta name="apple-mobile-web-app-capable" content="yes">'
            '<meta name="mobile-web-app-capable" content="yes">'
            '<meta name="description" content="《高性价比人生指南》%s，共 %d 条建议，'
            '每条标注成本、收益、证据等级（A/B/C）与原始文献链接。单文件、零依赖、可离线阅读。">'
            '<title>高性价比人生指南 · %s</title>'
            # 主题要在首帧之前定下来，否则深色用户会先闪一下白
            "<script>try{var t=localStorage.getItem('hltb-theme');"
            "if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t)}catch(e){}</script>"
            '<style>%s</style></head><body>'
            % (SCOPE, total, SCOPE, CSS))

    src_line = '数据来源：<a href="%s" target="_blank" rel="noopener">eternity4719/HowToLiveBetter</a>' % UPSTREAM
    src_line += '（Unlicense，公有领域）'
    if rev:
        src_line += '，数据截至 <span style="font-family:var(--mono)">%s</span>%s' % (
            rev, '（%s）' % rev_date if rev_date else '')

    footer = ('<footer>%s。<br>'
              '「说人话」「收益」等栏目为原文摘录，未作改写；本页共 %d 条，'
              'A 级 %d 条、B 级 %d 条、C 级 %d 条，含 %d 条文献外链。<br>'
              '单文件自包含，不引用任何外部资源（正文中的文献链接除外），可离线阅读。'
              '由 build.py 生成。</footer>'
              % (src_line, total, grade_cnt["A"], grade_cnt["B"], grade_cnt["C"], link_total))

    home = (
        '<main class="home" id="home">'
        '<header class="hero"><div class="txt"><div class="kicker">HOW TO LIVE BETTER</div>'
        '<h1>高性价比人生指南</h1>'
        '<p><b>%d</b> 节 · <b>%d</b> 条建议 · A 级证据 <b>%d</b> 条<br>'
        '挑一节，像翻卡片一样一条条看</p></div>'
        '<button class="icon-btn" type="button" data-theme-btn aria-label="切换明暗">%s</button></header>'
        '<div class="tools"><form class="search" id="sform" role="search">%s'
        '<input id="q" type="search" placeholder="搜索建议、说人话、来源…" autocomplete="off" enterkeyhint="search" aria-label="搜索">'
        '<button class="clr hidden" id="clr" type="button" aria-label="清空搜索">%s</button></form>'
        '<div class="chips-row" role="group" aria-label="筛选">'
        '<button class="pill" type="button" data-f="all" aria-pressed="true">全部</button>'
        '<button class="pill" type="button" data-f="A" aria-pressed="false">只看 A 级</button>'
        '<button class="pill" type="button" data-f="hi" aria-pressed="false">高性价比</button>'
        '</div></div>'
        '<noscript><p class="nojs">卡片翻阅需要浏览器开启 JavaScript。</p></noscript>'
        '<button class="resume hidden" id="resume" type="button"><span class="play">'
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z"/></svg></span>'
        '<span class="rt"><small>继续上次</small><b id="r-sec"></b><span id="r-at"></span></span></button>'
        '<div class="hits hidden" id="hits"><div id="hits-t"></div>'
        '<button class="pill" type="button" id="hits-go">全部翻看%s</button></div>'
        '<div class="label"><div><b>选一节开始</b><span id="grid-c">%d 条</span></div>'
        '<button class="pill ghost" type="button" id="shuffle">%s随机翻翻</button></div>'
        '<div class="grid" id="grid">%s</div>%s</main>'
        % (len(SECTIONS), total, grade_cnt["A"], svg("theme"), svg("search"), svg("x"),
           svg("arrow"), total, svg("shuffle"), "".join(tiles), footer))

    deck = (
        '<section class="deck" id="deck" aria-hidden="true" aria-label="卡片阅读">'
        '<div class="d-top"><button class="icon-btn" id="back" type="button" aria-label="返回目录">%s</button>'
        '<button class="d-title" id="d-title" type="button" aria-label="本组卡片目录"><span id="d-name"></span>%s</button>'
        '<button class="icon-btn" type="button" data-theme-btn aria-label="切换明暗">%s</button></div>'
        '<div class="d-prog"><div class="track"><i id="d-bar"></i></div><span id="d-pos" aria-live="polite"></span></div>'
        '<div class="stage" id="stage"></div>'
        '<nav class="d-ctl" aria-label="翻页"><button class="icon-btn" id="prev" type="button" aria-label="上一张">%s</button>'
        '<button class="act" id="act" type="button"></button>'
        '<button class="icon-btn" id="next" type="button" aria-label="下一张">%s</button></nav></section>'
        '<div class="sheet" id="sheet" aria-hidden="true" role="dialog" aria-modal="true" aria-labelledby="sheet-t">'
        '<div class="sheet-bg" id="sheet-bg"></div><div class="sheet-panel"><div class="sheet-h"><h3 id="sheet-t"></h3>'
        '<button class="icon-btn" id="sheet-x" type="button" aria-label="关闭">%s</button></div>'
        '<div class="sheet-list" id="sheet-list"></div></div></div>'
        '<div class="toast" id="toast" role="status"></div>'
        % (svg("left"), svg("down"), svg("theme"), svg("left"), svg("right"), svg("x")))

    # 注意：JS 字符串只含脚本体，<script> 开合标签在这里拼。
    out = (head + home + deck
           + '<script type="application/json" id="data">' + data_json + '</script>'
           + "<script>" + JS + "</script></body></html>")

    if ARGS.out:
        name = Path(ARGS.out)
        if not name.is_absolute():
            name = HERE / name
    else:
        name = HERE / ("高性价比人生指南_%s.html" % "_".join("第%d节" % n for n in SECTIONS))

    name.write_text(out, encoding="utf-8")
    print("范围 %s ｜ 节数 %d ｜ 条目 %d ｜ A %d B %d C %d ｜ 外链 %d"
          % (SCOPE, len(SECTIONS), total, grade_cnt["A"], grade_cnt["B"], grade_cnt["C"], link_total))
    print("输出：%s  (%d 字节)" % (name, len(out.encode("utf-8"))))


if __name__ == "__main__":
    main()
