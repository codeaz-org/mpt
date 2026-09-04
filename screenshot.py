"""Screenshot a repo's GitHub page so a Star Rising episode can show the real thing.

A video about someone else's project that never shows the project asks the viewer
to take the narrator's word for it. A tall capture of the repo page -- header,
stars, file tree, README -- panned slowly on screen is the proof, and it is the
one shot in the format that cannot be faked from a description.

Headless Chrome does the work. `ubuntu-latest` ships Google Chrome, so CI needs
no extra install; locally any Chrome or Chromium is used. There is no fallback
capture path: when no browser is found the caller renders the episode without the
screenshot rather than failing the run.

The capture is one tall viewport rather than a true full-page shot -- the old
`--screenshot` flag has no full-page mode -- which is exactly what we want: a
fixed, predictable height to pan across.
"""
import os, shutil, struct, subprocess, tempfile

# 880 is not arbitrary: it is exactly the width of the browser frame the template
# draws, so the capture maps 1:1 onto the canvas and nothing is downscaled. A
# 1280-wide capture squeezed into that frame rendered README body text too small
# to read on a phone, which defeats the point of showing the README at all.
WIDTH = 880
HEIGHT = 5200        # tall enough to reach well into the README
TIMEOUT = 90
# Chrome renders a page for this long (in ms of virtual time) before shooting, so
# late-loading README images and syntax highlighting make it into the frame.
VIRTUAL_TIME_BUDGET = 15000

CANDIDATES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")


def log(msg): print(f"[screenshot] {msg}", flush=True)


def find_browser():
    """Path to a usable Chrome, or None. CHROME_BIN wins so a runner with an
    unusual layout can point at its own binary."""
    override = (os.environ.get("CHROME_BIN") or "").strip()
    if override and os.path.exists(override):
        return override
    for name in CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return None


def png_size(path):
    """(width, height) from a PNG header -- no Pillow dependency, and the renderer
    needs the real dimensions to compute how far to pan."""
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("not a PNG")
    return struct.unpack(">II", head[16:24])


def capture(url, out_path, width=WIDTH, height=HEIGHT):
    """Shoot `url` into `out_path`. Returns (width, height); raises on any failure
    so the caller can decide whether the episode is still worth rendering."""
    browser = find_browser()
    if not browser:
        raise RuntimeError("no Chrome or Chromium on PATH (set CHROME_BIN)")
    # A throwaway profile: a shared one gets locked when two runs overlap, and
    # Chrome then exits without writing the file.
    with tempfile.TemporaryDirectory() as profile:
        cmd = [
            browser, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--disable-dev-shm-usage", "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--user-data-dir={profile}",
            f"--window-size={width},{height}",
            f"--virtual-time-budget={VIRTUAL_TIME_BUDGET}",
            f"--screenshot={out_path}",
            url,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 20_000:
        raise RuntimeError(
            f"chrome wrote no usable screenshot (rc={r.returncode}): {r.stderr[-300:]}")
    size = png_size(out_path)
    log(f"{url} -> {os.path.basename(out_path)} ({size[0]}x{size[1]}, "
        f"{os.path.getsize(out_path) // 1024} KB)")
    return size
