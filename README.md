# Cheer ASCII Studio

Local, human-in-the-loop tool to build a braille portrait gallery of the people and pets you love — your kids, your
partner, your friends, your dog — for the `Cheer Me Up` Claude Code output style. Images come in via the companion
**browser extension**; the studio crops/mattes them and auto-renders braille. Nothing here is deployed — it runs on
localhost and writes to `~/.claude/cheer-gallery/`.

## Run

```bash
./run.sh
# or
.venv/bin/uvicorn server:app --port 8000
```

Opens `http://localhost:8000`. Backend = FastAPI (`server.py`); frontend = one responsive `static/index.html` (vanilla
JS, no build step).

## Get images: the browser extension

Load `extension/` unpacked (`chrome://extensions` → Developer mode → Load unpacked). Then, while logged in / browsing:

- **Right-click an image → Send image to Cheer Studio**, or
- **Click the toolbar icon** to scan the page you're viewing. On a single Instagram post it walks the full carousel; on
  a profile/feed it opens each post and walks every carousel. It also works on ordinary pages by grabbing the large
  images as you scroll. Then pick images in the tab that opens and **Send**.

Sent images land in the chosen subject's candidates. This avoids search-scraping entirely and uses your own browsing
session.

The subject list in the picker is fetched from the local studio; pick an existing subject or type a new key in the
custom box. If the studio isn't running, it falls back to the last-known list (cached) plus free-text entry.

## Flow in the studio

1. **Pick a subject** — choose an existing subject in the header dropdown, or `(custom…)` to start a new one (e.g. a
   name).
2. **Convert** — for each candidate image: drag on the original to crop (head & shoulders works well; pick the right
   face in a group photo). The braille is produced **automatically** — background removed, auto-contrast, tonal+contour
   for maximum detail. Cropped preview on the left, braille on the right. **Keep** / **Discard**.
3. **Gallery & Export** — review what you kept, remove any, then **Replace live gallery** to copy them into
   `~/.claude/cheer-gallery/<subject>/`.

## Layout

```
server.py             # FastAPI backend (wraps studio/*) + serves the frontend
static/index.html     # responsive vanilla-JS UI (convert / gallery)
extension/            # MV3 browser extension (capture from Instagram/anywhere)
studio/
  download.py         # concurrent download + validation (manual import / extension url fallback)
  matte.py            # background removal (rembg, GrabCut fallback) + compose
  braille.py          # image -> braille (tonal / contour / hybrid, bg-aware)
data/<subject>/       # candidates/ crops/ gallery/ state.json   (git-ignored)
claude/               # the Cheer Me Up output style + optional welcome-back hook
```

## Install the Claude Code side

The gallery is consumed by the **Cheer Me Up** output style for Claude Code, bundled in `claude/`:

```bash
cp claude/cheer-me-up.md ~/.claude/output-styles/
```

Activate inside Claude Code with `/output-style Cheer Me Up`. Claude then occasionally pastes a portrait from
`~/.claude/cheer-gallery/` — when it senses you're frustrated, and sometimes just because.

Optional: the welcome-back hook adds a "first reply after a while" cheer (the model can't perceive idle time on its
own). Copy it and register it as a `UserPromptSubmit` hook:

```bash
cp claude/welcome-back-cheer.py ~/.claude/hooks/
```

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "~/.claude/hooks/welcome-back-cheer.py" }] }]
  }
}
```

(in `~/.claude/settings.json`; idle threshold defaults to 15 min, override with `CHEER_IDLE_SECONDS`). The style works
fine without the hook — you only lose the welcome-back beat.
