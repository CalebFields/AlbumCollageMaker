# Album Collage Maker (Tkinter)

A simple desktop app that builds an X×Y collage of album covers from lines like **`Artist - Album`**.  
It fetches cover art via the iTunes Search API, lays out a grid, and prints each row’s album list in a **right-hand black margin** (white text). Exports to **PNG** or **JPEG**.

---

## Features
- Paste a list of albums (`Artist - Album`, one per line)
- Set grid size (columns × rows), cell size, right margin width, font size, and padding
- Auto-fetch album art (600×600) from Apple iTunes Search (no API key)
- Word-wrapped, per-row album labels in a right-side black margin
- Preview inside the app; export to PNG/JPEG
- Works with Pillow 10+ (uses `textbbox()` / `textlength()`)

---

## Install

```bash
# 1) Create/activate a venv (recommended)
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 2) Install deps
pip install pillow requests
