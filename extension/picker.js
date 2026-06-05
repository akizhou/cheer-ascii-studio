const API = "http://localhost:8000";
const $ = (s) => document.querySelector(s);
const sel = $("#subject"),
  custom = $("#custom"),
  grid = $("#grid"),
  statusEl = $("#statusEl"),
  sendBtn = $("#send");
const chosen = new Set();
const tiles = new Map();
let subjects = [];

function fillSubjects(list, stored) {
  subjects = list || [];
  sel.innerHTML = "";
  subjects.forEach((k) => {
    const o = document.createElement("option");
    o.value = k;
    o.textContent = k;
    sel.appendChild(o);
  });
  if (stored && subjects.includes(stored)) sel.value = stored;
  else if (stored) custom.value = stored;
}

// Fetch the known subjects from the local server; fall back to the cached list
// in chrome.storage (plus the free-text "custom" box) when the server is down.
async function initSubjects() {
  const stored = (await chrome.storage.sync.get("subject")).subject || "";
  let list = null;
  try {
    const r = await fetch(API + "/api/subjects");
    list = (await r.json()).subjects || [];
    chrome.storage.local.set({ subjects: list });
  } catch (e) {
    list = (await chrome.storage.local.get("subjects")).subjects || [];
  }
  fillSubjects(list, stored);
}

sel.onchange = () => {
  custom.value = "";
  chrome.storage.sync.set({ subject: sel.value });
};
custom.oninput = () => {
  const v = custom.value.trim();
  if (v) chrome.storage.sync.set({ subject: v });
};
const subject = () => custom.value.trim() || sel.value;

function updateSend() {
  sendBtn.textContent = "Send " + chosen.size + " selected →";
  sendBtn.disabled = chosen.size === 0;
}
function setSel(url, el, on) {
  if (on) {
    chosen.add(url);
    el.classList.add("sel");
  } else {
    chosen.delete(url);
    el.classList.remove("sel");
  }
}

function render(urls) {
  grid.innerHTML = "";
  chosen.clear();
  tiles.clear();
  statusEl.textContent = urls.length + " captured";
  urls.forEach((u) => {
    const d = document.createElement("div");
    d.className = "t";
    const img = document.createElement("img");
    img.src = u;
    img.loading = "lazy";
    img.onerror = () => {
      chosen.delete(u);
      tiles.delete(u);
      d.remove();
      updateSend();
    };
    d.appendChild(img);
    d.onclick = () => {
      setSel(u, d, !chosen.has(u));
      updateSend();
    };
    grid.appendChild(d);
    tiles.set(u, d);
  });
  updateSend();
}

function load() {
  chrome.storage.local.get("captured", ({ captured }) => render((captured || []).slice().reverse()));
}

$("#refresh").onclick = load;
$("#all").onclick = () => {
  tiles.forEach((el, u) => setSel(u, el, true));
  updateSend();
};
$("#clearSel").onclick = () => {
  tiles.forEach((el, u) => setSel(u, el, false));
  updateSend();
};
$("#clearCap").onclick = () => chrome.storage.local.set({ captured: [] }, () => render([]));

async function toDataUrl(u) {
  const b = await (await fetch(u)).blob();
  return await new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = rej;
    fr.readAsDataURL(b);
  });
}

$("#send").onclick = async () => {
  if (!chosen.size) return;
  const id = subject();
  if (!id) {
    statusEl.textContent = "pick a subject first";
    return;
  }
  const list = [...chosen];
  let ok = 0,
    fail = 0;
  sendBtn.disabled = true;
  for (let i = 0; i < list.length; i++) {
    statusEl.textContent = "sending " + (i + 1) + "/" + list.length + "…";
    let body;
    try {
      body = { subject: id, data_url: await toDataUrl(list[i]) };
    } catch (e) {
      body = { subject: id, url: list[i] };
    }
    try {
      const j = await (
        await fetch(API + "/api/import_image", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        })
      ).json();
      j.ok ? ok++ : fail++;
    } catch (e) {
      fail++;
    }
  }
  statusEl.textContent =
    "sent " + ok + (fail ? " / " + fail + " failed" : "") + " → " + id + " (open Studio → Convert)";
  sendBtn.disabled = false;
};

fetch(API + "/api/ping")
  .then((r) => r.json())
  .catch(() => {
    statusEl.textContent = "studio not running — start ./run.sh";
  });
initSubjects();
load();
