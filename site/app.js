(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const audio = $("audio");
  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  };

  // Order sections are read in. "city" is filled from the chosen city.
  const ORDER = ["top", "state", "city", "india", "world", "sports", "business", "cinema"];

  let data = null;
  let paper = null;
  let queue = [];      // [{sectionIdx, title, intro?}]
  let sections = [];   // [{id, name, items, start}]
  let pos = 0;
  let playing = false;
  let token = 0;       // cancels stale callbacks
  let wakeLock = null;

  // ---------- loading ----------
  fetch("data/news.json?t=" + Date.now())
    .then((r) => r.json())
    .then((d) => { data = d; renderHome(); })
    .catch(() => { $("updated").textContent = "செய்திகளை ஏற்ற முடியவில்லை. சிறிது நேரம் கழித்து மீண்டும் முயலவும்."; });

  function renderHome() {
    $("updated").textContent = "புதுப்பிக்கப்பட்டது: " + data.updatedText;
    const box = $("papers");
    box.innerHTML = "";
    data.papers.forEach((p) => {
      const n = p.sections.reduce((a, s) => a + s.items.length, 0);
      if (!n) return;
      const b = document.createElement("button");
      b.className = "paper";
      b.innerHTML = `${p.name}<small>${n} செய்திகள்</small>`;
      b.onclick = () => openPaper(p);
      box.appendChild(b);
    });
    const sel = $("city");
    sel.innerHTML = data.cities.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
    sel.value = store.get("city", "chennai");
    sel.onchange = () => store.set("city", sel.value);
    const sp = $("speed");
    sp.value = store.get("speed", "1");
    sp.onchange = () => store.set("speed", sp.value);
  }

  // ---------- reader ----------
  function openPaper(p) {
    paper = p;
    const cityId = $("city").value;
    const city = data.cities.find((c) => c.id === cityId) || data.cities[0];
    const byId = Object.fromEntries(p.sections.map((s) => [s.id, s]));
    byId.city = { id: "city", name: city.name + " செய்திகள்", items: p.cities[city.id] || [] };
    sections = ORDER.map((id) => byId[id]).filter((s) => s && s.items.length);
    queue = [];
    sections.forEach((s, i) => {
      s.start = queue.length;
      queue.push({ sectionIdx: i, intro: true, title: `${p.name}. ${s.name}.` });
      s.items.forEach((it, j) => queue.push({ sectionIdx: i, title: it.title, num: j + 1, of: s.items.length }));
    });
    $("paperName").textContent = p.name;
    renderSections();
    $("home").hidden = true;
    $("reader").hidden = false;
    window.scrollTo(0, 0);
    history.pushState({ reader: true }, "");
    pos = 0;
    play();
  }

  function renderSections() {
    const box = $("sections");
    box.innerHTML = "";
    sections.forEach((s, i) => {
      const b = document.createElement("button");
      b.className = "sec";
      b.dataset.idx = i;
      b.innerHTML = `${s.name}<span>${s.items.length}</span>`;
      b.onclick = () => { pos = s.start; play(); };
      box.appendChild(b);
    });
  }

  function show() {
    const q = queue[pos];
    if (!q) return;
    const s = sections[q.sectionIdx];
    $("sectionName").textContent = s.name;
    $("counter").textContent = q.intro ? "" : `செய்தி ${q.num} / ${q.of}`;
    $("headline").textContent = q.intro ? "" : q.title;
    document.querySelectorAll(".sec").forEach((b) =>
      b.classList.toggle("active", Number(b.dataset.idx) === q.sectionIdx));
  }

  function setPlayIcon() { $("play").textContent = playing ? "⏸" : "▶"; }

  function play() {
    stopSound();
    playing = true;
    setPlayIcon();
    keepAwake(true);
    speakCurrent();
  }

  function pause() {
    playing = false;
    stopSound();
    setPlayIcon();
    keepAwake(false);
  }

  function finished() {
    pause();
    pos = 0;
    $("sectionName").textContent = "இன்றைய செய்திகள் முடிந்தன";
    $("counter").textContent = "";
    $("headline").textContent = "மீண்டும் கேட்க ▶ அழுத்தவும்.";
    speakText("இன்றைய செய்திகள் முடிந்தன. நன்றி.", () => {}, ++token);
  }

  function speakCurrent() {
    if (pos >= queue.length) return finished();
    show();
    const my = ++token;
    speakText(queue[pos].title, () => {
      if (my !== token || !playing) return;
      pos++;
      setTimeout(() => { if (my === token && playing) speakCurrent(); }, 500);
    }, my);
  }

  function speakText(text, done, my) {
    const rate = Number($("speed").value) || 1;
    const file = data.audio && data.audio[text];
    if (file) {
      audio.src = "data/audio/" + file;
      audio.playbackRate = rate;
      audio.onended = done;
      audio.onerror = () => { if (my === token) browserSpeak(text, done, rate); };
      audio.play().catch(() => { if (my === token) browserSpeak(text, done, rate); });
    } else {
      browserSpeak(text, done, rate);
    }
  }

  // Fallback: the phone's own Tamil voice.
  function tamilVoice() {
    if (!("speechSynthesis" in window)) return null;
    return speechSynthesis.getVoices().find((v) => /^ta/i.test(v.lang)) || null;
  }
  function browserSpeak(text, done, rate) {
    if (!("speechSynthesis" in window)) { setTimeout(done, 3000); return; }
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ta-IN";
    const v = tamilVoice();
    if (v) u.voice = v; else warnNoVoice();
    u.rate = rate * 0.9;
    u.onend = done;
    u.onerror = done;
    speechSynthesis.speak(u);
  }
  function warnNoVoice() {
    const w = $("voiceWarn");
    w.textContent = "இந்த சாதனத்தில் தமிழ் குரல் இல்லை. Google Chrome-இல் திறக்கவும் அல்லது அமைப்புகளில் தமிழ் குரலைச் சேர்க்கவும்.";
    w.hidden = false;
  }

  function stopSound() {
    token++;
    audio.onended = null;
    audio.onerror = null;
    audio.pause();
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  async function keepAwake(on) {
    try {
      if (on && "wakeLock" in navigator && !wakeLock) {
        wakeLock = await navigator.wakeLock.request("screen");
        wakeLock.addEventListener("release", () => { wakeLock = null; });
      } else if (!on && wakeLock) { await wakeLock.release(); wakeLock = null; }
    } catch {}
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && playing) keepAwake(true);
  });

  // ---------- controls ----------
  $("play").onclick = () => (playing ? pause() : play());
  $("next").onclick = () => { pos = Math.min(pos + 1, queue.length - 1); play(); };
  $("prev").onclick = () => {
    pos = Math.max(pos - 1, 0);
    if (queue[pos] && queue[pos].intro && pos > 0) pos--;
    play();
  };
  $("nextSection").onclick = () => {
    const cur = queue[pos] ? queue[pos].sectionIdx : -1;
    const nxt = sections[cur + 1];
    if (nxt) { pos = nxt.start; play(); } else finished();
  };
  function goHome() {
    pause();
    $("reader").hidden = true;
    $("home").hidden = false;
    window.scrollTo(0, 0);
  }
  $("back").onclick = () => history.back();
  window.addEventListener("popstate", goHome);
})();
