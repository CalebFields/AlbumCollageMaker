import io
import re
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont, ImageTk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------- Fetching album art ----------

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
UA = "AlbumCollageMaker/1.1"

def itunes_cover_url(artist: str, album: str) -> Optional[str]:
    q = f"{artist} {album}".strip()
    try:
        r = requests.get(
            ITUNES_SEARCH_URL,
            params={"term": q, "media": "music", "entity": "album", "limit": 1},
            headers={"User-Agent": UA},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("resultCount", 0) == 0:
            return None
        artwork = data["results"][0].get("artworkUrl100")
        if not artwork:
            return None
        # bump to 600x600
        return re.sub(r"/\d+x\d+bb\.", "/600x600bb.", artwork)
    except Exception:
        return None

def fetch_image(url: str) -> Optional[Image.Image]:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None

def get_album_art(artist: str, album: str, fallback_color=(25, 25, 25)) -> Image.Image:
    url = itunes_cover_url(artist, album)
    img = fetch_image(url) if url else None
    return img if img else Image.new("RGB", (600, 600), fallback_color)

# ---------- Text helpers (Pillow 10+ safe) ----------

def measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    """
    Returns (width, height) of text. Uses textbbox() if available, else textsize().
    """
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return right - left, bottom - top
    except AttributeError:
        # Pillow <10 fallback
        return draw.textsize(text, font=font)

def wrap_text_to_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    """
    Wrap text to a given pixel width. Uses draw.textlength when available; falls back to measure_text.
    """
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        try:
            ok = draw.textlength(test, font=font) <= max_width  # Pillow ≥8
        except AttributeError:
            ok = measure_text(draw, test, font)[0] <= max_width
        if ok:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]

# ---------- Collage logic ----------

@dataclass
class CollageConfig:
    cols: int
    rows: int
    cell_size: int = 300
    margin_width: int = 320
    padding: int = 0
    font_size: int = 20
    line_spacing: int = 4

def parse_entries(raw: str) -> List[Tuple[str, str]]:
    out = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        if " - " in s:
            a, b = s.split(" - ", 1)
        else:
            parts = s.split("-", 1)
            a, b = (parts[0], parts[1]) if len(parts) == 2 else ("", s)
        out.append((a.strip(), b.strip()))
    return out

def fit_and_paste(src: Image.Image, dst: Image.Image, x: int, y: int, size: int, pad: int = 0):
    w, h = src.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    cropped = src.crop((left, top, left + side, top + side))
    resized = cropped.resize((size - 2 * pad, size - 2 * pad), Image.LANCZOS)
    dst.paste(resized, (x + pad, y + pad))

def build_collage(entries: List[Tuple[str, str]], cfg: CollageConfig) -> Image.Image:
    total = cfg.cols * cfg.rows
    items = (entries[:total] + [("", "")] * total)[:total]

    images = [get_album_art(a, b) if (a or b) else Image.new("RGB", (600, 600), (20, 20, 20))
              for a, b in items]

    W = cfg.cols * cfg.cell_size + cfg.margin_width
    H = cfg.rows * cfg.cell_size
    collage = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(collage)

    try:
        font = ImageFont.truetype("arial.ttf", cfg.font_size)
    except Exception:
        font = ImageFont.load_default()

    # paste grid
    for r in range(cfg.rows):
        for c in range(cfg.cols):
            idx = r * cfg.cols + c
            x = c * cfg.cell_size
            y = r * cfg.cell_size
            fit_and_paste(images[idx], collage, x, y, cfg.cell_size, cfg.padding)

    # right margin text
    margin_x = cfg.cols * cfg.cell_size
    margin_inner_x = margin_x + 10
    margin_width_inner = cfg.margin_width - 20

    _, font_h = measure_text(draw, "Ag", font)
    line_h = font_h + cfg.line_spacing

    for r in range(cfg.rows):
        row_items = items[r * cfg.cols : (r + 1) * cfg.cols]
        y_ptr = r * cfg.cell_size + 10
        for (artist, album) in row_items:
            label = (f"{artist} - {album}").strip(" -") or "—"
            for ln in wrap_text_to_width(draw, label, font, margin_width_inner):
                draw.text((margin_inner_x, y_ptr), ln, fill=(255, 255, 255), font=font)
                y_ptr += line_h

    return collage

# ---------- Tkinter UI ----------

class CollageApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Album Collage Maker")
        self.geometry("1050x720")
        self.cfg = CollageConfig(cols=4, rows=4, cell_size=300, margin_width=320, padding=0, font_size=20)
        self.preview_imgtk = None
        self.preview_scale = 0.4
        self._build_ui()

    def _build_ui(self):
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)

        left = ttk.Frame(container); left.pack(side="left", fill="y", padx=10, pady=10)
        right = ttk.Frame(container); right.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        grid_frame = ttk.LabelFrame(left, text="Grid"); grid_frame.pack(fill="x", pady=5)
        self.cols_var = tk.IntVar(value=self.cfg.cols)
        self.rows_var = tk.IntVar(value=self.cfg.rows)
        ttk.Label(grid_frame, text="Columns (X):").grid(row=0, column=0, sticky="w")
        ttk.Entry(grid_frame, textvariable=self.cols_var, width=6).grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(grid_frame, text="Rows (Y):").grid(row=0, column=2, sticky="w", padx=(10,0))
        ttk.Entry(grid_frame, textvariable=self.rows_var, width=6).grid(row=0, column=3, sticky="w", padx=5)

        size_frame = ttk.LabelFrame(left, text="Sizes"); size_frame.pack(fill="x", pady=5)
        self.cell_var = tk.IntVar(value=self.cfg.cell_size)
        self.margin_var = tk.IntVar(value=self.cfg.margin_width)
        self.font_var = tk.IntVar(value=self.cfg.font_size)
        self.pad_var = tk.IntVar(value=self.cfg.padding)
        ttk.Label(size_frame, text="Cell px:").grid(row=0, column=0, sticky="w")
        ttk.Entry(size_frame, textvariable=self.cell_var, width=7).grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(size_frame, text="Margin px:").grid(row=0, column=2, sticky="w")
        ttk.Entry(size_frame, textvariable=self.margin_var, width=7).grid(row=0, column=3, sticky="w", padx=5)
        ttk.Label(size_frame, text="Font size:").grid(row=1, column=0, sticky="w", pady=(6,0))
        ttk.Entry(size_frame, textvariable=self.font_var, width=7).grid(row=1, column=1, sticky="w", padx=5, pady=(6,0))
        ttk.Label(size_frame, text="Padding:").grid(row=1, column=2, sticky="w", pady=(6,0))
        ttk.Entry(size_frame, textvariable=self.pad_var, width=7).grid(row=1, column=3, sticky="w", padx=5, pady=(6,0))

        list_frame = ttk.LabelFrame(left, text="Albums (Artist - Album), one per line")
        list_frame.pack(fill="both", expand=True, pady=5)
        self.text = tk.Text(list_frame, width=38, height=24, wrap="word")
        self.text.pack(fill="both", expand=True, padx=5, pady=5)

        btn_frame = ttk.Frame(left); btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Load Example", command=self.load_example).pack(side="left")
        ttk.Button(btn_frame, text="Build Preview", command=self.build_preview_threaded).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Export…", command=self.export_image_threaded).pack(side="left")

        canvas_frame = ttk.Frame(right); canvas_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg="#222")
        hbar = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        vbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.status = ttk.Label(right, text="Ready.", anchor="w")
        self.status.pack(fill="x", pady=(6,0))

    def load_example(self):
        sample = [
            "Radiohead - In Rainbows",
            "Kanye West - My Beautiful Dark Twisted Fantasy",
            "Lorde - Melodrama",
            "Daft Punk - Discovery",
            "Kendrick Lamar - To Pimp a Butterfly",
            "Taylor Swift - 1989",
            "Bon Iver - For Emma, Forever Ago",
            "Tame Impala - Currents",
            "Beyoncé - Lemonade",
            "Frank Ocean - Blonde",
            "Arctic Monkeys - AM",
            "Phoebe Bridgers - Punisher",
            "The Strokes - Is This It",
            "Fleetwood Mac - Rumours",
            "Tyler, The Creator - IGOR",
            "The Weeknd - After Hours",
        ]
        self.text.delete("1.0", "end")
        self.text.insert("1.0", "\n".join(sample))

    def _read_cfg(self) -> CollageConfig:
        return CollageConfig(
            cols=max(1, int(self.cols_var.get())),
            rows=max(1, int(self.rows_var.get())),
            cell_size=max(80, int(self.cell_var.get())),
            margin_width=max(120, int(self.margin_var.get())),
            padding=max(0, int(self.pad_var.get())),
            font_size=max(10, int(self.font_var.get())),
        )

    def _read_entries(self) -> List[Tuple[str, str]]:
        return parse_entries(self.text.get("1.0", "end"))

    def set_status(self, msg: str):
        self.status.config(text=msg)
        self.status.update_idletasks()

    # -------- threaded actions --------
    def build_preview_threaded(self):
        threading.Thread(target=self._build_preview_safe, daemon=True).start()

    def _build_preview_safe(self):
        try:
            self.set_status("Building preview…")
            cfg = self._read_cfg()
            entries = self._read_entries()
            img = build_collage(entries, cfg)
            scale = self.preview_scale
            w, h = img.size
            pw, ph = max(1, int(w * scale)), max(1, int(h * scale))
            prev = img.resize((pw, ph), Image.LANCZOS)
            self.preview_imgtk = ImageTk.PhotoImage(prev)
            def update_canvas():
                self.canvas.delete("all")
                self.canvas.create_image(0, 0, anchor="nw", image=self.preview_imgtk)
                self.canvas.config(scrollregion=(0, 0, pw, ph))
                self.set_status(f"Preview ready ({w}×{h}).")
            self.after(0, update_canvas)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.set_status("Error building preview.")

    def export_image_threaded(self):
        threading.Thread(target=self._export_image_safe, daemon=True).start()

    def _export_image_safe(self):
        try:
            cfg = self._read_cfg()
            entries = self._read_entries()
            fpath = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG Image", "*.png"), ("JPEG Image", "*.jpg;*.jpeg")],
                title="Export collage"
            )
            if not fpath:
                return
            self.set_status("Rendering full image…")
            img = build_collage(entries, cfg)
            if fpath.lower().endswith((".jpg", ".jpeg")):
                img = img.convert("RGB")
                img.save(fpath, format="JPEG", quality=95, subsampling=0)
            else:
                img.save(fpath, format="PNG", optimize=True)
            self.set_status(f"Saved: {fpath}")
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.set_status("Export failed.")

if __name__ == "__main__":
    app = CollageApp()
    app.mainloop()
