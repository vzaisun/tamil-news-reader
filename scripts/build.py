"""Fetch today's Tamil news for each paper and section, write site/data/news.json,
and pre-record each headline as Tamil speech (MP3) with edge-tts.

Runs inside GitHub Actions on a schedule. News comes from Google News RSS,
filtered to each newspaper's website, so it works for any paper without
depending on each site's own (often broken) RSS feeds.
"""

import asyncio
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import feedparser
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "data")
AUDIO_DIR = os.path.join(OUT, "audio")

VOICE = os.environ.get("TTS_VOICE", "ta-IN-PallaviNeural")
IST = timezone(timedelta(hours=5, minutes=30))
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

PAPERS = [
    {"id": "dinamalar", "name": "தினமலர்", "site": "dinamalar.com"},
    {"id": "dailythanthi", "name": "தினத்தந்தி", "site": "dailythanthi.com"},
    {"id": "dinamani", "name": "தினமணி", "site": "dinamani.com"},
    {"id": "hindutamil", "name": "இந்து தமிழ்", "site": "hindutamil.in"},
    {"id": "maalaimalar", "name": "மாலைமலர்", "site": "maalaimalar.com"},
    {"id": "bbctamil", "name": "பிபிசி தமிழ்", "site": "bbc.com/tamil"},
]

# Each section is a Google News search. "{site}" is replaced with the paper's site.
SECTIONS = [
    {"id": "top", "name": "முக்கிய செய்திகள்", "q": "site:{site}", "n": 10},
    {"id": "state", "name": "தமிழ்நாடு செய்திகள்",
     "q": "site:{site} (தமிழ்நாடு OR தமிழகம் OR முதல்வர் OR அமைச்சர் OR சட்டசபை)", "n": 8},
    {"id": "india", "name": "இந்தியா செய்திகள்",
     "q": "site:{site} (இந்தியா OR பிரதமர் OR டெல்லி OR மத்திய அரசு)", "n": 8},
    {"id": "world", "name": "உலக செய்திகள்",
     "q": "site:{site} (அமெரிக்கா OR சீனா OR பாகிஸ்தான் OR இலங்கை OR உலக)", "n": 6},
    {"id": "sports", "name": "விளையாட்டு செய்திகள்",
     "q": "site:{site} (கிரிக்கெட் OR விளையாட்டு OR போட்டி OR கால்பந்து OR டென்னிஸ்)", "n": 8},
    {"id": "business", "name": "வணிகம் மற்றும் தங்கம் விலை",
     "q": "site:{site} (தங்கம் விலை OR பங்குச்சந்தை OR பெட்ரோல் OR வணிகம்)", "n": 6},
    {"id": "cinema", "name": "சினிமா செய்திகள்",
     "q": "site:{site} (சினிமா OR திரைப்படம் OR நடிகர் OR நடிகை)", "n": 6},
]

CITIES = [
    {"id": "chennai", "name": "சென்னை"},
    {"id": "coimbatore", "name": "கோவை"},
    {"id": "madurai", "name": "மதுரை"},
    {"id": "trichy", "name": "திருச்சி"},
    {"id": "salem", "name": "சேலம்"},
    {"id": "tirunelveli", "name": "நெல்லை"},
    {"id": "vellore", "name": "வேலூர்"},
    {"id": "thanjavur", "name": "தஞ்சாவூர்"},
]
CITY_ITEMS = 6

session = requests.Session()
session.headers["User-Agent"] = UA


def google_news(query, when="1d"):
    q = f"{query} when:{when}"
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
           + "&hl=ta&gl=IN&ceid=IN:ta")
    for attempt in range(3):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                return feedparser.parse(r.content).entries
            print(f"  HTTP {r.status_code} for {q}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  error {e} for {q}", file=sys.stderr)
        time.sleep(3 * (attempt + 1))
    return []


def clean_title(entry):
    title = html.unescape(entry.get("title", "")).strip()
    src = entry.get("source", {}).get("title") if entry.get("source") else None
    if src and title.endswith(" - " + src):
        title = title[: -len(src) - 3]
    elif " - " in title:
        title = title.rsplit(" - ", 1)[0]
    title = re.sub(r"\s+", " ", title).strip(" |-")
    return title


def has_tamil(s):
    return bool(re.search(r"[஀-௿]", s))


def entry_time(e):
    t = e.get("published_parsed")
    return time.mktime(t) if t else 0


def pick(entries, n, seen):
    out = []
    for e in sorted(entries, key=entry_time, reverse=True):
        t = clean_title(e)
        key = re.sub(r"\W", "", t)[:60]
        if not t or not has_tamil(t) or key in seen:
            continue
        seen.add(key)
        out.append({"title": t, "link": e.get("link", "")})
        if len(out) >= n:
            break
    return out


def fetch_paper(paper):
    seen = set()
    sections = []
    for s in SECTIONS:
        entries = google_news(s["q"].format(site=paper["site"]))
        if len(entries) < 3:
            entries += google_news(s["q"].format(site=paper["site"]), when="2d")
        items = pick(entries, s["n"], seen)
        print(f"{paper['id']:>12} {s['id']:<10} {len(entries):>3} found, {len(items)} kept")
        sections.append({"id": s["id"], "name": s["name"], "items": items})
        time.sleep(1)
    cities = {}
    for c in CITIES:
        entries = google_news(f"site:{paper['site']} {c['name']}", when="2d")
        items = pick(entries, CITY_ITEMS, set(seen))
        print(f"{paper['id']:>12} city:{c['id']:<10} {len(items)} kept")
        cities[c["id"]] = items
        time.sleep(1)
    return sections, cities


def audio_name(text):
    return hashlib.sha1((text).encode()).hexdigest()[:16] + ".mp3"


async def edge_save(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="-10%").save(path)


async def gtts_save(text, path):
    from gtts import gTTS
    await asyncio.to_thread(lambda: gTTS(text, lang="ta", tld="co.in").save(path))


async def tts_all(texts):
    """Record every phrase. Prefer Microsoft's neural Tamil voice; if that
    service refuses us, fall back to Google's Tamil voice."""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    texts = list(texts)
    engines = [("edge", edge_save), ("google", gtts_save)]
    engine = None
    for name, fn in engines:
        probe = os.path.join(AUDIO_DIR, "_probe.mp3")
        try:
            await asyncio.wait_for(fn("வணக்கம்", probe), 30)
            if os.path.getsize(probe) > 0:
                engine = (name, fn)
                os.remove(probe)
                break
        except Exception as e:  # noqa: BLE001
            print(f"  {name} voice unavailable: {e}", file=sys.stderr)
    if not engine:
        print("No voice service available; the site will use the phone's voice.")
        return {}
    name, fn = engine
    print(f"recording with {name} voice")
    sem = asyncio.Semaphore(6 if name == "edge" else 3)
    ok = {}

    async def one(text):
        fname = audio_name(text)
        path = os.path.join(AUDIO_DIR, fname)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            ok[text] = fname
            return
        async with sem:
            for attempt in range(3):
                try:
                    await asyncio.wait_for(fn(text, path), 60)
                    if os.path.getsize(path) > 0:
                        ok[text] = fname
                        return
                except Exception as e:  # noqa: BLE001
                    print(f"  tts retry {attempt}: {str(e)[:120]}", file=sys.stderr)
                    await asyncio.sleep(2 * (attempt + 1))

    await asyncio.gather(*(one(t) for t in texts))
    return ok


def main():
    os.makedirs(OUT, exist_ok=True)
    now = datetime.now(IST)
    data = {
        "updated": now.isoformat(timespec="minutes"),
        "updatedText": now.strftime("%d-%m-%Y, %I:%M %p"),
        "voice": VOICE,
        "cities": CITIES,
        "papers": [],
    }
    for p in PAPERS:
        sections, cities = fetch_paper(p)
        data["papers"].append({**p, "sections": sections, "cities": cities})

    # Collect every phrase to speak: section intros and each headline.
    texts = set()
    for p in data["papers"]:
        groups = [s["items"] for s in p["sections"]] + list(p["cities"].values())
        for items in groups:
            for it in items:
                texts.add(it["title"])
        for s in p["sections"]:
            texts.add(f"{p['name']}. {s['name']}.")
        for c in CITIES:
            texts.add(f"{p['name']}. {c['name']} செய்திகள்.")
    if os.environ.get("SKIP_TTS") != "1":
        audio = asyncio.run(tts_all(sorted(texts)))
        print(f"audio: {len(audio)}/{len(texts)} clips")
    else:
        audio = {}
    data["audio"] = audio

    with open(os.path.join(OUT, "news.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    total = sum(len(s["items"]) for p in data["papers"] for s in p["sections"])
    print(f"wrote news.json with {total} section headlines")
    if total == 0:
        sys.exit("No news fetched at all; keeping the previous site.")


if __name__ == "__main__":
    main()
