#!/usr/bin/env python3
"""Build Vetting's local unWISE GIFs from public 19x19 FITS cutouts.

The two-frame reconstruction uses NEO1 and the weighted NEO11–NEO5
increment. These release windows approximate WiseView's outer epochs.
Usage: python scripts/cache_unwise_blinks.py ~/Documents/Vetting/unWISE/Build/targets.csv
"""

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import csv
from dataclasses import dataclass
from datetime import datetime
import fcntl
import gzip
from io import BytesIO
from itertools import groupby, islice
import json
import math
from pathlib import Path
import re
import sys
import tarfile
from tempfile import NamedTemporaryFile
from threading import Lock
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from astropy.io import fits
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mocaviz.local_unwise import CACHE, PROFILE, PREVIEW_ID, cached_preview

ARCHIVE = "https://unwise.me/cutout_fits"
BANDS = (1, 2)
RELEASES = ("neo1", "neo5", "neo11")
SIZE = 19
MAX_BYTES = 256 * 1024
GEOMETRY = ("CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2", "NAXIS1", "NAXIS2")
CUTOUT_NAME = re.compile(r"unwise-(\d{4}[pm]\d{3})-w([12])-(img|invvar)-m\.fits(?:\.gz)?")
PRIORITIES = {1: "SUBLIME4", 2: "SUBLIME3C", 3: "MOSHPIT", 4: "SUBLIME2", 5: "CatWISE red movers"}


@dataclass(frozen=True)
class Target:
    key: str
    priority: int
    ra: float
    dec: float


@dataclass
class Cutout:
    data: np.ndarray
    geometry: dict
    scale: tuple
    dates: tuple


def stamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Archive:
    def __init__(self, minimum_interval):
        self.minimum_interval = minimum_interval
        self.lock = Lock()
        self.next_request = 0.0

    def pace(self):
        while True:
            with self.lock:
                remaining = self.next_request - time.monotonic()
                if remaining <= 0:
                    self.next_request = time.monotonic() + self.minimum_interval
                    return
            time.sleep(min(remaining, 10))

    def pause(self, seconds):
        with self.lock:
            self.next_request = max(self.next_request, time.monotonic() + seconds)

    def cutout(self, target, release):
        fields = dict(version=release, ra=f"{target.ra:.10f}", dec=f"{target.dec:.10f}",
                      size=SIZE, bands="12", file_img_m="on")
        if release != "neo1":
            fields["file_invvar_m"] = "on"
        request = Request(ARCHIVE + "?" + urlencode(fields),
                          headers={"User-Agent": "Vetting-unWISE-cutout-cache/1.0"})
        for attempt in range(4):
            self.pace()
            try:
                with urlopen(request, timeout=25) as response:
                    payload = response.read(MAX_BYTES + 1)
                if len(payload) > MAX_BYTES:
                    raise ValueError("cutout response too large")
                return payload
            except HTTPError as exc:
                if exc.code not in (408, 425, 429, 500, 502, 503, 504) or attempt == 3:
                    raise
                delay = exc.headers.get("Retry-After", "")
                seconds = int(delay) if delay.isdecimal() else (60 if exc.code in (429, 503) else 5 * (2 ** attempt))
                self.pause(max(seconds, 1))
            except (URLError, TimeoutError, ConnectionError):
                if attempt == 3:
                    raise
                self.pause(5 * (2 ** attempt))


def planes(bundle, *, require_weights):
    results = {}
    with tarfile.open(fileobj=BytesIO(bundle), mode="r:gz") as archive:
        for entry in archive:
            match = CUTOUT_NAME.fullmatch(Path(entry.name).name)
            if not entry.isfile() or not match or entry.size > MAX_BYTES:
                continue
            tile, band, kind = match.groups()
            if kind == "invvar" and not require_weights:
                continue
            raw = archive.extractfile(entry).read()
            if entry.name.endswith(".gz"):
                with gzip.GzipFile(fileobj=BytesIO(raw)) as compressed:
                    raw = compressed.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("FITS cutout too large")
            with fits.open(BytesIO(raw), memmap=False) as hdus:
                header = hdus[0].header
                data = hdus[0].data
                if data is None or data.shape != (SIZE, SIZE):
                    continue
                geometry = {key: float(header[key]) for key in GEOMETRY}
                scale = tuple(header.get(key) for key in (
                    "CTYPE1", "CTYPE2", "CD1_1", "CD1_2", "CD2_1", "CD2_2", "CDELT1", "CDELT2"
                ))
                if kind == "img":
                    if header.get("MAGZP") != 22.5:
                        continue
                    dates = (float(header["MJDMIN"]), float(header["MJDMAX"]))
                else:
                    dates = ()
                results.setdefault(tile, {})[(int(band), kind)] = Cutout(
                    np.asarray(data[::-1], dtype=np.float64), geometry, scale, dates
                )
    return results


def select_tile(releases):
    for tile in releases[0]:
        if any(tile not in archive for archive in releases[1:]):
            continue
        sets = [archive[tile] for archive in releases]
        if any((band, "img") not in group for group in sets for band in BANDS):
            continue
        if any((band, "invvar") not in group for group in sets[1:] for band in BANDS):
            continue
        first = sets[0][1, "img"]
        if all(plane.geometry == first.geometry and plane.scale == first.scale
               for group in sets for plane in group.values()):
            return sets, first.geometry
    raise ValueError("no common 19x19 FITS image grid")


def color_frame(flux, valid):
    if not np.all(valid[:, 8:11, 8:11]) or np.mean(valid) < .85:
        raise ValueError("insufficient valid pixels after weight subtraction")
    lower = np.maximum(-50, np.min(np.where(valid, flux, np.inf), axis=(1, 2)))[:, None, None]
    upper = np.minimum(500, np.max(np.where(valid, flux, -np.inf), axis=(1, 2)))[:, None, None]
    if np.any(upper <= lower):
        raise ValueError("no usable image contrast")
    levels = np.where(valid, np.clip((flux - lower) / (upper - lower), 0, 1), 0)
    red = levels[0]
    blue = .2 * red + .8 * levels[1]
    green = (red + blue) / 2
    return Image.fromarray(np.rint(255 * (1 - np.stack([red, green, blue], axis=-1))).astype(np.uint8))


def render(bundles):
    sets, geometry = select_tile([planes(bundle, require_weights=index != 0)
                                  for index, bundle in enumerate(bundles)])
    early, baseline, latest = sets
    early_flux = np.stack([early[band, "img"].data for band in BANDS])
    late_flux = []
    valid_late = []
    for band in BANDS:
        old_image, old_weight = (baseline[band, kind].data for kind in ("img", "invvar"))
        new_image, new_weight = (latest[band, kind].data for kind in ("img", "invvar"))
        delta = new_weight - old_weight
        valid = np.isfinite(old_image) & np.isfinite(new_image) & np.isfinite(delta) & (delta > 0)
        result = np.zeros_like(new_image)
        np.divide(new_image * new_weight - old_image * old_weight, delta, out=result, where=valid)
        late_flux.append(result)
        valid_late.append(valid & np.isfinite(result))
    first = color_frame(early_flux, np.isfinite(early_flux))
    last = color_frame(np.stack(late_flux), np.stack(valid_late))
    gif = BytesIO()
    first.save(gif, "GIF", save_all=True, append_images=[last], duration=500, loop=0, disposal=2)
    bounds = [
        [min(early[band, "img"].dates[0] for band in BANDS), max(early[band, "img"].dates[1] for band in BANDS)],
        [max(baseline[band, "img"].dates[1] for band in BANDS), max(latest[band, "img"].dates[1] for band in BANDS)],
    ]
    return gif.getvalue(), geometry, bounds


def write_atomic(path, content):
    with NamedTemporaryFile(dir=path.parent, prefix=".preview-", delete=False) as output:
        temp = Path(output.name)
        try:
            output.write(content)
            output.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def generate(target, archive):
    start = time.monotonic()
    try:
        inputs = [archive.cutout(target, release) for release in RELEASES]
        gif, wcs, mjds = render(inputs)
        dest = CACHE / (target.key + ".gif")
        write_atomic(dest, gif)
        metadata = dict(profile=PROFILE, ra=target.ra, dec=target.dec, wcs=wcs, mjds=mjds,
                        input_bytes=sum(map(len, inputs)), source="unWISE NEO1, NEO5, NEO11 archive FITS cutouts")
        write_atomic(dest.with_suffix(".json"), json.dumps(metadata, allow_nan=False).encode())
        return target.key, "built", time.monotonic() - start, metadata["input_bytes"]
    except HTTPError as exc:
        reason = f"HTTP {exc.code}"
    except ValueError as exc:
        # Only locally authored ValueError messages are expected here, but HTTP
        # and parser errors can include coordinates. Keep network details out.
        reason = str(exc) if str(exc) in (
            "no common 19x19 FITS image grid", "insufficient valid pixels after weight subtraction",
            "no usable image contrast", "cutout response too large", "FITS cutout too large"
        ) else type(exc).__name__
    except (OSError, KeyError, tarfile.TarError) as exc:
        reason = type(exc).__name__
    return target.key, reason, time.monotonic() - start, 0


def read_targets(path):
    targets = {}
    with path.open(newline="") as stream:
        for item in csv.DictReader(stream):
            key = item["target_id"]
            target = Target(key, int(item["priority"]), float(item["ra"]), float(item["dec"]))
            if (not PREVIEW_ID.fullmatch(key) or target.priority not in PRIORITIES or
                    not 0 <= target.ra < 360 or not -90 <= target.dec <= 90 or
                    not math.isfinite(target.ra) or not math.isfinite(target.dec)):
                raise ValueError(f"Invalid target: {key}")
            if key in targets and targets[key] != target:
                raise ValueError(f"Conflicting catalog rows for {key}")
            targets[key] = target
    return sorted(targets.values(), key=lambda item: (item.priority, len(item.key), item.key))


def build(targets, workers, interval):
    progress = Counter()
    archive = Archive(interval)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for priority, rows in groupby(targets, key=lambda item: item.priority):
            cohort = list(rows)
            todo = [row for row in cohort if not cached_preview(row.key, row.ra, row.dec)]
            progress["cached"] += len(cohort) - len(todo)
            print(f"{stamp()} {PRIORITIES[priority]}: {len(todo):,} pending of {len(cohort):,}", flush=True)
            pending = iter(todo)
            active = {pool.submit(generate, row, archive) for row in islice(pending, workers)}
            while active:
                completed, active = wait(active, return_when=FIRST_COMPLETED)
                for future in completed:
                    target, state, duration, byte_count = future.result()
                    progress["built" if state == "built" else "failed"] += 1
                    print(f"{stamp()} {sum(progress.values())}/{len(targets)} {target} "
                          f"{state} {duration:.2f}s {byte_count}B", flush=True)
                    row = next(pending, None)
                    if row:
                        active.add(pool.submit(generate, row, archive))
    print(f"{stamp()} {progress['built']:,} built, {progress['cached']:,} cached, "
          f"{progress['failed']:,} failed", flush=True)
    return int(progress["failed"] > 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=3)
    parser.add_argument("--interval", type=float, default=.45, help="Minimum seconds between archive requests")
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval < .3 or (args.limit is not None and args.limit < 1):
        parser.error("Use an interval of at least 0.3 seconds and a positive limit")
    targets = read_targets(args.targets)[:args.limit]
    if not targets:
        parser.error("The target list is empty")
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    build_dir = CACHE.parent / "Build"
    build_dir.mkdir(exist_ok=True, mode=0o700)
    with (build_dir / "build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return build(targets, args.workers, args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
