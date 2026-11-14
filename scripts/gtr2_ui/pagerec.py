"""Recognize which menu page is on screen by comparing it with saved references.

Each page has two files in baselines/: a small image, and a mask of the pixels to ignore because they
animate. A page's score is the mean pixel difference over the pixels that aren't masked; lower is closer.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from paths import BASELINES, HERE, LOCAL_BASELINES, MASK_SCALE, SHRINK_SIZE  # noqa: E402  (the size-dependent settings live in paths.py)

SIZE = SHRINK_SIZE  # 800 wide, the window's own aspect ratio (800x450 for 16:9). References are per test size (paths.py).
VOLATILE_THRESHOLD = 12


def scale_rows(y):
    """A row written for the 800x450 shrink, as a row of this size's shrink."""
    return round(y * MASK_SCALE)


# Animation slower than the sampling window can't be measured, so these are masked by hand. Coordinates are for the
# 800x450 (16:9) shrink; volatile_mask scales the rows to the active size.
FIXED_MASKS = {
    "MAIN MENU": [(0, 56, 800, 125)],  # Rotating car photos.
    "CREDITS_MAIN": [(0, 75, 800, 345)],  # Scrolling credits.
    # On track, the right-hand panel shows live temperatures and the monitor shows a live camera view.
    "MONITOR_SINGLE": [(678, 76, 800, 252), (372, 92, 648, 236)],
    "FULLGRID_SINGLE": [(678, 76, 800, 252)],
    "TRACKINFO_SINGLE": [(678, 76, 800, 252)],
    "GARAGEPAGE": [(678, 76, 800, 252)],
    # Starting a championship season shuffles the AI drivers within each class, so the standings tables differ every run.
    "DRIVERSTANDING_CHAMP": [(115, 112, 645, 352)],
    "TEAMSTANDINGS_CHAMP": [(115, 112, 645, 352)],
    # The replay studio draws its controls over a live 3D view: only the control bar along the bottom and the camera pad
    # on the right are compared.
    "REPLAY STUDIO PAGE": [(0, 0, 800, 325), (0, 325, 695, 400), (200, 425, 300, 450), (540, 425, 800, 450)],
    # The session's full-screen monitor view: a live 3D view with a control bar along the bottom.
    "GRIDMONITOR_NOLIST": [(0, 0, 800, 400)],
    # The full screen is the same 3D view with no controls: what's outside the car changes with the replay, so only the
    # cockpit interior along the bottom, where the studio draws its control bar, is compared. The two bottom corners
    # also show the track and the pit wall through the car's side, which change with the replay, so they're left out.
    "REPLAY STUDIO MAXIMIZED": [(0, 0, 800, 360), (0, 360, 160, 450), (560, 360, 720, 450)],
    # The results table lists every driver in the race, so its rows vary with the race (the first page to use it had one).
    "POST RACE MONITOR": [(60, 108, 720, 347)],
    "ENDURANCE POST RACE MONITOR": [(60, 108, 720, 347)],
    # The in-progress details grow as rounds are driven: position, points, the next event.
    "RESUMEORNEW_CHAMP IN PROGRESS": [(285, 115, 730, 255)],
}
# Accept a match only if it's close to the reference and clearly closer than the runner-up. In the game, true
# pages scored 0.4 or lower, while wrong pages scored about 4 against Credits, whose mask leaves only the shared
# bars to compare. A page with no reference must come back as unrecognized, not as its nearest neighbour.
MAX_SCORE = 2.0
# A page that is mostly a live 3D view scores a little higher against its own reference, and nothing else comes close, so it
# gets a wider limit. The replay studio scored 2.27 once (replay stopped at 0.000) and its full screen 3.02, each missed
# for 15 to 30 s with the page on screen; the next best page scored 29 or more both times.
# CONFIRM_EXIT is the "Leave Current Event?" popup: translucent, drawn over many pages, so its reference compares only the box and
# is refined (gtr2-nav.py refine) on each background; a wrong page scores 13 or more against it.
PAGE_MAX_SCORE = {"REPLAY STUDIO PAGE": 3.5, "REPLAY STUDIO MAXIMIZED": 4.0, "CONFIRM_EXIT": 6.0, "LEAVE LOBBY": 6.0, "MP_ADDGAME": 6.0}
MIN_MARGIN = 1.0


def shrink(frame):
    """Reduce a full-size captured frame to the size references are stored at."""
    img = Image.fromarray(frame.astype("uint8"))
    return np.asarray(img.resize(SIZE, Image.BOX), dtype=np.int16)


def file_stem(page):
    return page.replace(" ", "+")


def volatile_mask(page, frames):
    """Mark pixels that changed between frames, or that are in the page's fixed mask. True means ignore."""
    stack = np.stack(frames)
    changed = (stack.max(axis=0) - stack.min(axis=0)).max(axis=2) > VOLATILE_THRESHOLD
    mask = Image.fromarray((changed * 255).astype("uint8")).filter(ImageFilter.MaxFilter(5))
    result = np.asarray(mask) > 0
    result = result.copy()
    for left, top, right, bottom in FIXED_MASKS.get(page, []):
        result[scale_rows(top):scale_rows(bottom), left:right] = True
    return result


NAME_BOX = (522, 3, 575, 13)   # the player name in the header band (x0, y0, x1, y1; 800x450 picture): kept out of saved references


def scrub_name(image, mask):
    """Paint the header's player name out of a reference picture and mark it as ignored, so shared references carry no player name.
    Only the header is handled (the same place on every page with a header); names in lists or tables are not found here.
    Returns the picture and the mask (copies); both are unchanged when the picture is not the 800x450 size or shows no text there."""
    x0, y0, x1, y1 = NAME_BOX
    if image.shape[1] != 800 or image.shape[0] < y1 + 4:
        return image, mask
    lum = image[y0:y1, x0:x1].mean(axis=2)
    if lum.max() - lum.min() < 30:
        return image, mask
    image, mask = image.copy(), mask.copy()
    for y in range(y0, y1):
        left, right = image[y, x0 - 4:x0].mean(axis=0), image[y, x1:x1 + 4].mean(axis=0)
        for x in range(x0, x1):
            t = (x - x0 + 0.5) / (x1 - x0)
            image[y, x] = np.round(left * (1 - t) + right * t)
    mask[y0:y1, x0:x1] = True
    return image, mask


def reference_mask_of_shipped_size(page, directory):
    """The mask the shipped 1280x720 set has for this page, as a mask for a reference saved at another test size. Masks are in the
    800x450 picture's coordinates and the UI is stretched over the window, so a hand-made mask (the popup-only box of CONFIRM_EXIT,
    the live car view, the name boxes, the standings tables, found by comparing frames at 1280x720) still covers the same things
    at any size. Nothing is added for the shipped size itself."""
    if directory.name == "1280x720":
        return np.zeros((SIZE[1], SIZE[0]), dtype=bool)
    for folder in (HERE / "baselines" / "local" / "1280x720", HERE / "baselines" / "1280x720"):
        path = folder / f"{file_stem(page)}.mask.png"
        if path.exists():
            return np.asarray(Image.open(path).convert("L")) > 0
    return np.zeros((SIZE[1], SIZE[0]), dtype=bool)


def save_reference(page, frames, directory=BASELINES):
    directory.mkdir(parents=True, exist_ok=True)
    mask = volatile_mask(page, frames)
    mask = mask | reference_mask_of_shipped_size(page, directory)
    picture, mask = scrub_name(frames[0], mask)
    Image.fromarray(picture.astype("uint8")).save(directory / f"{file_stem(page)}.png", optimize=True)
    Image.fromarray((mask * 255).astype("uint8")).convert("1").save(directory / f"{file_stem(page)}.mask.png",
                                                                    optimize=True)
    return float(mask.mean())


def _load_one(path):
    mask_path = path.with_name(path.stem + ".mask.png")
    image = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
    mask = np.asarray(Image.open(mask_path).convert("L")) > 0
    return image, mask


class LazyReferences:
    """The references as a read-only mapping that decodes a page's images only when it is first used. Loading all of them takes
    about 1.7 s here, and a scripted path touches a dozen pages. Pages learned on this machine (LOCAL_BASELINES) replace the
    shipped copies of the same name."""

    def __init__(self, folders):
        self._paths = {}
        for folder in folders:
            if folder.exists():
                for path in sorted(folder.glob("*.png")):
                    if not path.name.endswith(".mask.png"):
                        self._paths[path.stem.replace("+", " ")] = path
        self._loaded = {}

    def __getitem__(self, name):
        if name not in self._loaded:
            self._loaded[name] = _load_one(self._paths[name])
        return self._loaded[name]

    def __contains__(self, name):
        return name in self._paths

    def __iter__(self):
        return iter(self._paths)

    def __len__(self):
        return len(self._paths)

    def keys(self):
        return self._paths.keys()

    def items(self):
        return ((name, self[name]) for name in self._paths)

    def values(self):
        return (self[name] for name in self._paths)


def load_references(directory=None):
    """The references of a folder; with no folder, the shipped baselines overridden by those learned on this machine."""
    if directory is None:
        return LazyReferences([BASELINES, LOCAL_BASELINES])
    return LazyReferences([directory])


@lru_cache(maxsize=1)
def cached_references():
    """The references, loaded once per process. Loading all of them takes about 185 ms."""
    return load_references()


def max_score(page):
    """The worst score still counted as this page."""
    return PAGE_MAX_SCORE.get(page, MAX_SCORE)


_keep = {}


def _kept(refs, page):
    """The page's unmasked pixels as (flat pixel indices, their reference values), made once: scoring a frame then touches only
    those pixels instead of the whole 800x450 picture."""
    key = (id(refs), page)
    if key not in _keep:
        image, mask = refs[page]
        idx = np.flatnonzero(~mask.reshape(-1))
        _keep[key] = (idx, image.reshape(-1, 3)[idx])
    return _keep[key]


def page_score(small, page, refs=None):
    """Score a shrunken frame against one page, for waiting on a page that's expected."""
    refs = refs or cached_references()
    idx, ref = _kept(refs, page)
    return float(np.abs(small.reshape(-1, 3)[idx] - ref).mean())


def scores(small, refs):
    """Score a shrunken frame against every reference, best first."""
    out = []
    for page, (image, mask) in refs.items():
        keep = ~mask
        out.append((float(np.abs(small - image).mean(axis=2)[keep].mean()), page))
    return sorted(out)


# Twin pages: the same layout in different modes (Setup, Driving School and 24 Hour each have their own Options and
# Controls pages) differ only in a tab bar, so they score within a few tenths of each other over the whole frame.
# To tell them apart, compare a frame with the two references only on the pixels where the references differ.
TWIN_PIXEL_DIFFERENCE = 30  # A pixel counts as different between two references above this (mean over R, G, B).
TWIN_MIN_PIXELS = 200  # Fewer different pixels than this and the two can't be told apart.


def _differing_pixels(ref_a, ref_b):
    (img_a, mask_a), (img_b, mask_b) = ref_a, ref_b
    diff = np.abs(img_a - img_b).mean(axis=2)
    return (diff > TWIN_PIXEL_DIFFERENCE) & ~mask_a & ~mask_b, diff


_pair_cache = {}


def _pair(refs, page, other):
    """Where two references differ: (flat indices, page's values there, other's values there, mean gap), or None if too few
    pixels differ. Kept, because it's needed for every capture while waiting on a page."""
    key = (id(refs), page, other)
    if key not in _pair_cache:
        where, diff = _differing_pixels(refs[page], refs[other])
        if where.sum() >= TWIN_MIN_PIXELS:
            idx = np.flatnonzero(where.reshape(-1))
            _pair_cache[key] = (idx, refs[page][0].reshape(-1, 3)[idx], refs[other][0].reshape(-1, 3)[idx],
                                float(diff[where].mean()))
        else:
            _pair_cache[key] = None
    return _pair_cache[key]


def beats_decisively(small, page, other, refs=None):
    """True if the frame is clearly `page` and clearly not `other`, judged only where those two references differ."""
    refs = refs or cached_references()
    pair = _pair(refs, page, other)
    if pair is None:
        return False
    idx, mine_ref, other_ref, gap = pair
    pixels = small.reshape(-1, 3)[idx]
    mine = float(np.abs(pixels - mine_ref).mean())
    theirs = float(np.abs(pixels - other_ref).mean())
    return mine <= 0.25 * gap and theirs - mine >= 0.5 * gap


REPLAY_BY_TRANSITION = {"REPLAY STUDIO PAGE", "REPLAY STUDIO MAXIMIZED"}


def longest_white_run(small):
    """How much of the replay studio's progress bar is drawn: the most bar-coloured pixels in any row of rows 404 to 421 of the 800x450
    shrink (scaled to this window size's shrink). The bar is white; the part already played is red, and the boundary pixel is neither, so
    the count is of pixels, not of an unbroken run."""
    best = 0
    for y in range(scale_rows(404), scale_rows(422)):
        row = small[y]
        bar = (row.min(axis=1) > 200) | ((row[:, 0] > 180) & (row[:, 1] < 80) & (row[:, 2] < 80))
        best = max(best, int(bar.sum()))
    return best


def replay_page_arrived(small, name):
    """The replay studio can't be matched to a reference: the scene behind its see-through bar changes with each replay and while it
    plays. So it is recognised by its progress bar (drawn full width, 375 px of white at 800 wide). The full screen view has no bar, so
    it is recognised by the bar being absent and the frame not being blank (a loose rule: any busy frame without the
    bar passes, so a path must only ask for it as the page a FULL SCREEN press leads to, and its own source check is the studio's bar)."""
    bar = longest_white_run(small) >= 300
    if name == "REPLAY STUDIO PAGE":
        return bar
    return not bar and float(small.mean()) > 10


def is_page(small, page, refs=None):
    """Whether a frame is this page: close to its reference, and not decisively one of its near-twins instead."""
    refs = refs or cached_references()
    if page in REPLAY_BY_TRANSITION and page in refs and replay_page_arrived(small, page):
        return True
    if page_score(small, page, refs) > max_score(page):
        return False
    return not any(beats_decisively(small, other, page, refs) for other in twins(page))


PAIR_FILE = HERE / f"pair_scores_{BASELINES.name}.json"   # committed: derived data, but a fresh clone would need minutes without it
SIG_FILE = HERE / "runs" / "sig_cache.json"                # local: file stamp -> content signature, so unchanged files aren't re-hashed
_tables = {}                                                # "pairs" / "sigs" -> loaded dict
_dirty = set()
_sigs = {}


def _table(name):
    import json
    if name not in _tables:
        path = PAIR_FILE if name == "pairs" else SIG_FILE
        try:
            _tables[name] = json.loads(path.read_text())
        except (OSError, ValueError):
            _tables[name] = {}
    return _tables[name]


def flush_caches():
    """Write the pair and signature tables if they changed. Called at exit and after indexing."""
    import json
    import os
    for name in list(_dirty):
        path = PAIR_FILE if name == "pairs" else SIG_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(_tables[name], separators=(",", ":")))
            os.replace(tmp, path)
            _dirty.discard(name)
        except OSError:
            pass  # only a speed-up


import atexit  # noqa: E402
atexit.register(flush_caches)


def _sig(name):
    """A page reference's content signature (image + mask), so cached scores follow the pictures, not file dates."""
    if name in _sigs:
        return _sigs[name]
    import hashlib
    path = cached_references()._paths[name]
    mask = path.with_name(path.stem + ".mask.png")
    stamp = [path.stat().st_size, path.stat().st_mtime_ns, mask.stat().st_size, mask.stat().st_mtime_ns]
    sigs = _table("sigs")
    row = sigs.get(str(path))
    if row and row[:4] == stamp:
        sig = row[4]
    else:
        h = hashlib.sha1()
        h.update(path.read_bytes())
        h.update(mask.read_bytes())
        sig = h.hexdigest()[:16]
        sigs[str(path)] = stamp + [sig]
        _dirty.add("sigs")
    _sigs[name] = sig
    return sig


@lru_cache(maxsize=None)
def ranked_self(page):
    """A page's own reference image scored against every reference, best first. The score of one reference image against another
    is kept by content signature (pair_scores_*.json), so adding or relearning one page computes only that page's pairs (about 3 ms
    each) instead of recomputing every ranking, which took about 0.6 s per page every time any reference changed."""
    refs = cached_references()
    pairs = _table("pairs")
    row = pairs.setdefault(_sig(page), {})
    out = []
    for other in refs:
        key = _sig(other)
        score = row.get(key)
        if score is None:
            image = refs[page][0]
            other_image, other_mask = refs[other]
            score = round(float(np.abs(image - other_image).mean(axis=2)[~other_mask].mean()), 4)
            row[key] = score
            _dirty.add("pairs")
        out.append((score, other))
    out.sort()
    return tuple(out)


def index_all():
    """Work out every missing pair score now (offline, no game needed). Returns the number of pairs computed."""
    before = sum(len(r) for r in _table("pairs").values())
    for page in cached_references():
        ranked_self(page)
    flush_caches()
    return sum(len(r) for r in _table("pairs").values()) - before


def twins(page):
    """The other pages whose references are within MAX_SCORE of this page's own, so the full-frame score can't separate them."""
    return tuple(p for s, p in ranked_self(page) if p != page and s <= MAX_SCORE)


_coarse = {}


def coarse_scores(small, refs, keep=12):
    """A quick first pass for recognizing an unknown frame: score every reference on a 4x smaller picture and return the `keep`
    best names. Scoring all references at full size takes about 2.8 s; this takes about 0.3 s once the pictures are decoded."""
    if id(refs) not in _coarse:
        small_refs = {}
        for page, (image, mask) in refs.items():
            h, w = (image.shape[0] // 4) * 4, (image.shape[1] // 4) * 4
            img = image[:h, :w].reshape(h // 4, 4, w // 4, 4, 3).mean(axis=(1, 3)).astype(np.float32)
            m = mask[:h, :w].reshape(h // 4, 4, w // 4, 4).all(axis=(1, 3))
            small_refs[page] = (img, ~m)
        _coarse[id(refs)] = small_refs
    h, w = (small.shape[0] // 4) * 4, (small.shape[1] // 4) * 4
    frame = small[:h, :w].reshape(h // 4, 4, w // 4, 4, 3).mean(axis=(1, 3)).astype(np.float32)
    out = []
    for page, (img, valid) in _coarse[id(refs)].items():
        out.append((float(np.abs(frame - img).mean(axis=2)[valid].mean()) if valid.any() else 1e9, page))
    out.sort()
    return [page for _s, page in out[:keep]]



def register_reference(page, directory=None):
    """Make a reference that was just saved (or replaced) visible to this process without reloading the others, and index its pair
    scores now. Dropping every decoded picture (cache_clear) cost 1.7 s of decoding at the next use."""
    refs = cached_references()
    directory = directory or LOCAL_BASELINES
    refs._paths[page] = directory / f"{file_stem(page)}.png"
    refs._loaded.pop(page, None)
    _sigs.pop(page, None)
    for key in [k for k in _keep if k[1] == page]:
        del _keep[key]
    for key in [k for k in _pair_cache if page in (k[1], k[2])]:
        del _pair_cache[key]
    _coarse.pop(id(refs), None)
    ranked_self.cache_clear()
    index_all()


def recognize_fast(small, refs):
    """recognize() on a short list found by coarse_scores: the same answer in a fraction of the time. (A page the coarse pass
    misses would be reported as unrecognized, never as a wrong page.)"""
    names = coarse_scores(small, refs)
    return recognize(small, {n: refs[n] for n in names})


def recognize(small, refs, ranked=None):
    """Return (page or None, best score, margin over the runner-up).

    A near tie is settled in favour of the best page only if it beats every page it's tied with, decisively, on
    the pixels where they differ; otherwise the page is unrecognized, as before. `ranked` is `scores(small, refs)`
    when the caller already has it.
    """
    ranked = ranked or scores(small, refs)
    if not ranked:  # no references for this window size yet: nothing can be recognized
        return None, float("inf"), 0.0
    best, page = ranked[0]
    margin = ranked[1][0] - best if len(ranked) > 1 else float("inf")
    if best <= max_score(page) and margin < MIN_MARGIN:
        tied = [p for s, p in ranked[1:] if s - best < MIN_MARGIN]
        if all(beats_decisively(small, page, other, refs) for other in tied):
            margin = MIN_MARGIN
    return (page if best <= max_score(page) and margin >= MIN_MARGIN else None), best, margin
