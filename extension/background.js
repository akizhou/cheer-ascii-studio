const API = "http://127.0.0.1:8000";
const CAP = 6000;
const MAX_POSTS = 150; // safety cap; full 280-post runs are slow + risk an IG action-block

// ---- single writer: serialize incremental "cap" batches from the scraper ----
let writeQueue = Promise.resolve();
function enqueueCap(urls) {
  writeQueue = writeQueue.then(
    () =>
      new Promise((resolve) => {
        chrome.storage.local.get("captured", (o) => {
          const merged = Array.from(new Set([...(o.captured || []), ...urls]));
          chrome.storage.local.set({ captured: merged.slice(-CAP) }, resolve);
        });
      }),
  );
}
chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "cap" && Array.isArray(msg.urls)) enqueueCap(msg.urls);
});

// ---- context menu (send a single image) ----
function setupMenu() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "cheer-send", title: "Send image to Cheer Studio", contexts: ["image"] });
  });
}
chrome.runtime.onInstalled.addListener(setupMenu);
chrome.runtime.onStartup.addListener(setupMenu);

function badge(text, color, sticky) {
  chrome.action.setBadgeBackgroundColor({ color });
  chrome.action.setBadgeText({ text });
  if (!sticky) setTimeout(() => chrome.action.setBadgeText({ text: "" }), 1800);
}
async function getSubject() {
  const { subject } = await chrome.storage.sync.get("subject");
  return subject || null;
}

// ---- injected: scrape one post, or walk every post in a profile/feed ----
async function scrapeAll(maxPosts) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const NEXT = /next|次|다음|siguiente|suivant|weiter|avanti|pr[óo]xim/i;
  const KEEP = /cdninstagram|fbcdn|pinimg|gstatic|twimg|\/wp-content\/|\.(jpg|jpeg|png|webp)(\?|$)/i;
  const SKIP = /favicon|sprite|emoji|profile_pic|\/static\//i;
  const largest = (ss) => {
    if (!ss) return "";
    const c = ss
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    c.sort((a, b) => (parseInt(b.split(/\s+/)[1] || "0") || 0) - (parseInt(a.split(/\s+/)[1] || "0") || 0));
    return c.length ? c[0].split(/\s+/)[0] : "";
  };
  const best = (im) =>
    largest(im.srcset || im.getAttribute("data-srcset")) ||
    im.currentSrc ||
    im.src ||
    im.getAttribute("data-src") ||
    "";
  const ok = (u) => u && /^https?:/.test(u) && KEEP.test(u) && !SKIP.test(u);
  const sent = new Set();
  const addUrl = (u) => {
    if (ok(u) && !sent.has(u)) {
      sent.add(u);
      try {
        chrome.runtime.sendMessage({ type: "cap", urls: [u] });
      } catch (e) {}
    }
  };
  const shortcode = () => {
    const m = location.pathname.match(/\/(p|reel)\/([^/]+)/);
    return m ? m[2] : "";
  };

  // the big image nearest the viewport center = the post photo / current carousel slide
  // (this is what avoids grabbing avatars, "suggested posts", and icons = the junk).
  const centerImg = (scope) => {
    const cx = innerWidth / 2,
      cy = innerHeight / 2;
    let pick = null,
      bd = 1e9;
    for (const im of scope.querySelectorAll("img")) {
      const r = im.getBoundingClientRect();
      if (r.width < 200 || r.height < 200) continue;
      const d = Math.abs(r.left + r.width / 2 - cx) + Math.abs(r.top + r.height / 2 - cy);
      if (d < bd) {
        bd = d;
        pick = im;
      }
    }
    return pick;
  };
  // carousel arrow: over the current image, vertical middle
  const carouselNext = (scope, ir) => {
    for (const el of scope.querySelectorAll("[aria-label]")) {
      if (!NEXT.test(el.getAttribute("aria-label") || "")) continue;
      const b = el.closest("button");
      if (!b || !b.offsetParent) continue;
      const r = b.getBoundingClientRect(),
        bx = r.left + r.width / 2,
        by = r.top + r.height / 2;
      if (
        bx > ir.left + ir.width * 0.5 &&
        bx < ir.right - ir.width * 0.02 &&
        by > ir.top + ir.height * 0.25 &&
        by < ir.bottom - ir.height * 0.25
      )
        return b;
    }
    return null;
  };
  const carousel = async (scope) => {
    const slides = new Set();
    for (let i = 0; i < 25; i++) {
      const im = centerImg(scope);
      if (!im) break;
      addUrl(best(im));
      const cur = im.currentSrc || im.src || "";
      if (cur) {
        if (slides.has(cur)) break;
        slides.add(cur);
      }
      const nb = carouselNext(scope, im.getBoundingClientRect());
      if (!nb) break;
      try {
        nb.click();
      } catch (e) {
        break;
      }
      await sleep(480);
    }
  };

  // standalone post page (no profile grid behind it): just that post
  if (/\/(p|reel)\//.test(location.pathname) && !document.querySelector('[role="dialog"]')) {
    await carousel(document.querySelector("article") || document);
    return;
  }

  // profile / feed (or a post modal open over a profile): walk every post via URL changes
  window.scrollTo(0, 0);
  await sleep(400);
  const first = document.querySelector('a[href*="/p/"], a[href*="/reel/"]');
  if (!first) {
    // non-IG / inline feed fallback: scroll, grab only large images
    for (let i = 0; i < 14; i++) {
      document.querySelectorAll("img").forEach((im) => {
        const r = im.getBoundingClientRect();
        if (r.width >= 200 && r.height >= 200) addUrl(best(im));
      });
      window.scrollBy(0, innerHeight * 0.9);
      await sleep(700);
    }
    return;
  }
  if (!shortcode()) {
    try {
      first.click();
    } catch (e) {}
    await sleep(1600);
  }

  const seen = new Set();
  for (let p = 0; p < maxPosts; p++) {
    const sc = shortcode();
    if (!sc || seen.has(sc)) break;
    seen.add(sc);
    await carousel(document.querySelector('[role="dialog"]') || document);

    // go to the NEXT post; accept only a click that actually changes the URL shortcode
    const before = sc;
    const im = centerImg(document);
    const ir = im ? im.getBoundingClientRect() : null;
    const cands = [];
    for (const el of document.querySelectorAll("[aria-label]")) {
      if (!NEXT.test(el.getAttribute("aria-label") || "")) continue;
      const b = el.closest("button") || el.closest("a");
      if (!b || !b.offsetParent) continue;
      const r = b.getBoundingClientRect(),
        bx = r.left + r.width / 2,
        by = r.top + r.height / 2;
      if (ir && bx > ir.left && bx < ir.right && by > ir.top + ir.height * 0.25 && by < ir.bottom - ir.height * 0.25)
        continue; // skip carousel arrow
      cands.push(b);
    }
    cands.sort((a, b) => b.getBoundingClientRect().left - a.getBoundingClientRect().left);
    const waitChange = async () => {
      for (let w = 0; w < 18; w++) {
        await sleep(200);
        if (shortcode() && shortcode() !== before) return true;
      }
      return false;
    };
    let advanced = false;
    for (const c of cands) {
      try {
        c.click();
      } catch (e) {
        continue;
      }
      if (await waitChange()) {
        advanced = true;
        break;
      }
    }
    if (!advanced) {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", keyCode: 39, bubbles: true }));
      advanced = await waitChange();
    }
    if (!advanced) break;
    await sleep(700);
  }
}

// ---- toolbar icon: run scrape in the focused tab, then open the picker ----
chrome.action.onClicked.addListener(async (tab) => {
  await chrome.storage.local.set({ captured: [] });
  badge("…", "#5b8cff", true);
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: scrapeAll, args: [MAX_POSTS] });
  } catch (e) {}
  await new Promise((r) => setTimeout(r, 1000));
  chrome.action.setBadgeText({ text: "" });
  chrome.tabs.create({ url: chrome.runtime.getURL("picker.html") });
});

// ---- context menu: send a single right-clicked image ----
async function toDataUrl(srcUrl) {
  const blob = await (await fetch(srcUrl)).blob();
  return await new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = rej;
    fr.readAsDataURL(blob);
  });
}
chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== "cheer-send" || !info.srcUrl) return;
  const subject = await getSubject();
  if (!subject) {
    // no subject chosen yet — open the picker so the user can pick / type one
    badge("?", "#d9a441", true);
    chrome.tabs.create({ url: chrome.runtime.getURL("picker.html") });
    return;
  }
  let body;
  try {
    body = { subject, data_url: await toDataUrl(info.srcUrl) };
  } catch (e) {
    body = { subject, url: info.srcUrl };
  }
  try {
    const j = await (
      await fetch(API + "/api/import_image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
    ).json();
    badge(j.ok ? "OK" : "!", j.ok ? "#3ddc84" : "#d9a441");
  } catch (e) {
    badge("x", "#e0556b");
  }
});
