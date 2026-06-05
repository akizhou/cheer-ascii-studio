# Cheer ASCII Studio

Local, human-in-the-loop tool that builds a braille portrait gallery of people and pets you love, for the `Cheer Me Up`
Claude Code output style. Three parts, all local — nothing is deployed:

- **Service** — FastAPI backend (`server.py`) + vanilla-JS frontend (`static/index.html`), runs on `localhost:8000`.
- **Extension** — MV3 browser extension (`extension/`), captures images from any site (including full Instagram carousel
  scans) and sends them to the local service. Loaded unpacked; not on any web store.
- **Pipeline** — `studio/` modules: download/validate → background removal (rembg, GrabCut fallback) → braille rendering
  (tonal + contour hybrid).

## Setup (first clone)

`run.sh` expects `.venv/` at the repo root — it does NOT create it. One-time setup:

```bash
uv sync                       # if uv is available (creates .venv from pyproject.toml)
# or without uv:
python3.12 -m venv .venv && .venv/bin/pip install -e .
```

Requires Python >= 3.12. Then:

```bash
./run.sh                      # = .venv/bin/uvicorn server:app --port 8000
```

Open http://localhost:8000.

## Loading the extension

1. `chrome://extensions` (or the Chromium-equivalent) → enable Developer mode → Load unpacked → select `extension/`.
2. Use it while the service is running: right-click an image → "Send image to Cheer Studio", or click the toolbar icon
   to scan the current page/post. A picker tab opens; choose images and Send.
3. Sent images land in the chosen subject's candidates in the studio.

## Data flow

```
extension / manual import
  → data/<subject>/candidates/    (git-ignored staging)
  → crop in the studio UI → auto braille render
  → Keep → data/<subject>/gallery/
  → "Replace live gallery" → ~/.claude/cheer-gallery/<subject>/NN.txt
```

`~/.claude/cheer-gallery/` is what the Cheer Me Up output style reads at runtime. Subjects are arbitrary folder names (a
kid, a pet, a friend).

## Gotchas

- First conversion downloads the rembg `u2net` model (~170 MB) — expect a one-time delay; needs network.
- The extension requires the service to be running to fetch the subject list; otherwise it falls back to a cached list
  plus free-text entry.
- `data/` is git-ignored — galleries are personal and never committed.
- Port is hardcoded to 8000 in `run.sh` and the extension's `host_permissions`; change both if you move it.

## Helping the user

If the user is setting this up for the first time, asking how to use it, or something is broken, invoke the `onboard`
skill (`.claude/skills/onboard/`) — it walks them through setup, capture, conversion, and troubleshooting interactively.
