---
name: onboard
description:
  Interactive guide for setting up and using Cheer ASCII Studio — the local service, the browser extension, and the
  portrait workflow. Use when the user just cloned the repo, asks how to get started, how to set up or run the studio,
  how to load or use the extension, how to add a new subject or build a gallery, or when something is broken (server
  won't start, extension can't connect, braille looks wrong).
---

# Onboard: Cheer ASCII Studio

Walk the user through setup and usage interactively. Do not dump all steps at once — find out where they are, run
verification commands yourself where possible, and advance one stage at a time.

## Step 0: branch on intent

Use AskUserQuestion to ask what they need (skip if already obvious from their message):

- **First-time setup** — fresh clone, nothing installed yet → Stage 1
- **Capture images** — service runs, they want the extension workflow → Stage 3
- **Build a gallery** — images are in, they want portraits → Stage 4
- **Troubleshoot** — something is broken → Troubleshooting

## Stage 1: environment + service

1. Check Python: `python3 --version` (need >= 3.12). If missing/old, help them install one (mise, uv, pyenv, python.org
   — whatever they already use; suggest `uv` if nothing is set up).
2. Create the venv — `run.sh` does NOT do this:
   - with uv: `uv sync`
   - without: `python3.12 -m venv .venv && .venv/bin/pip install -e .`
3. Start it: `./run.sh` (run in background) and verify with
   `curl -s http://localhost:8000/ -o /dev/null -w '%{http_code}'` → expect `200`.
4. Tell them to open http://localhost:8000 — they should see the studio UI.
5. Warn: the first image conversion downloads the rembg `u2net` model (~170 MB), so the very first Convert is slow.

## Stage 2: load the browser extension

The extension cannot be installed for them — guide click-by-click:

1. Open `chrome://extensions` (Chrome/Edge/Brave/Arc all work) → toggle **Developer mode** (top right).
2. **Load unpacked** → select the `extension/` folder of this clone.
3. Confirm "Cheer Studio Importer" appears. Pin the toolbar icon for convenience.

## Stage 3: capture images

Two paths — explain both, let them pick:

- **Right-click** any image on any site → "Send image to Cheer Studio".
- **Toolbar icon** on a page → scans it. On a single Instagram post it walks the full carousel; on a profile/feed it
  opens each post and walks every carousel; on ordinary pages it grabs the large images as they scroll. A picker tab
  opens — they select images, choose a subject (existing, or type a new name in the custom box), and **Send**.

Subject names are arbitrary folder keys — a kid's name, a pet, a friend. Verify arrivals: sent images appear under
`data/<subject>/candidates/` and in the studio UI for that subject.

## Stage 4: convert and export

In the studio UI:

1. Pick the subject in the header dropdown (or `(custom…)` for a new one).
2. For each candidate: **drag on the original to crop** — head & shoulders crops work best; in a group photo, crop to
   the right face. Braille renders automatically (background removed, auto-contrast). **Keep** or **Discard**.
3. In Gallery & Export: review keepers, remove any, then **Replace live gallery** — this copies them to
   `~/.claude/cheer-gallery/<subject>/`.
4. Verify: `ls ~/.claude/cheer-gallery/` should show the subject with `.txt` files inside.

Aim for ~10+ portraits per subject so the random picker has variety.

## Stage 5: point them at the payoff

The gallery is consumed by the **Cheer Me Up** Claude Code output style (see README). If they have it installed,
activating is `/output-style Cheer Me Up` — Claude will then occasionally paste a portrait of their person/pet to cheer
them up. If they don't have the style, point them to the README section about it.

## Troubleshooting

- **`./run.sh` fails with "no such file .venv"** → Stage 1 step 2 was skipped; create the venv.
- **`uv sync` / pip install fails on rembg or onnxruntime** → check Python is 3.12+ and the platform wheel exists;
  retrying with `pip install --upgrade pip` first often fixes resolver issues.
- **First Convert hangs** → it is downloading the u2net model (~170 MB); check network, give it time. Progress appears
  in the server logs.
- **Extension picker shows no/stale subjects** → the service is not running (it falls back to a cached list); start
  `./run.sh`.
- **Extension sends nothing** → confirm the service is on port 8000 (`curl localhost:8000`); the extension's
  `host_permissions` are hardcoded to `localhost:8000` / `127.0.0.1:8000`.
- **Braille output looks like noise** → crop tighter (head & shoulders), pick higher-resolution source images, and
  prefer images where the subject is well lit against a distinct background.
- **Port 8000 already in use** → `./run.sh --port 8001` works for the studio, but the extension's manifest must be
  edited to match — easier to free port 8000.

When a server-side error is unclear, read the uvicorn log output and `studio/` source (`matte.py`, `braille.py`,
`download.py`) rather than guessing.
