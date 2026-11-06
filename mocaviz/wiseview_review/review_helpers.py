"""Headless review helpers ported from the maintained SPHEREx pipeline.

Only browser-runtime dependencies are included; no desktop GUI or workers.
"""
from __future__ import annotations
from .lane_utils import (
    STACKER_VISUAL_VETTING_TABLE, SUBLIMEAPERTURE_VISUAL_VETTING_TABLE,
    default_spiffviz_vetting_tables,
)
import argparse


import json


import math


import os


import pathlib


import re


import urllib.request


import xml.etree.ElementTree as ET


from dataclasses import dataclass


from decimal import Decimal


from typing import Iterable, Optional, Sequence


from urllib.parse import urlencode


import pymysql


WISEVIEW_VETTING_TABLE = "pcat_wiseview_visual_vetting"


DEFAULT_SOURCE_TABLE = "pcat_sublime_candidates_v2"


ORIGIN = pathlib.Path(__file__).name


TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


WISEVIEW_BASE_URL = "http://byw.tools/wiseview-v2"


NEARBY_BD_FILTER_MIN_SPECTRAL_TYPE_NUMBER = 10


WISEVIEW_PS1_FALLBACK_CUTOUT_ID = "wiseview-vetting-ps1-fallback-cutout"


WISEVIEW_DES_SUPPLEMENT_CUTOUTS_ID = "wiseview-vetting-des-supplement-cutouts"


UHS_DR1_J_HIPS_CUT_OPTIONS = {
    "minCut": "10%",
    "maxCut": "99.8%",
    "stretch": "linear",
}


WISEVIEW_PS1_FALLBACK_CUTOUT_SOURCES = (
    {
        "survey": "DES",
        "type": "hips",
        "label": "DES DR2 ColorIRG",
        "epoch": "2013-2019 coadd",
        "hips": "CDS/P/DES-DR2/ColorIRG",
    },
    {
        "survey": "NSC",
        "type": "sia",
        "label": "NSC DR2",
        "epoch": "per-exposure",
        "siaUrl": "https://datalab.noirlab.edu/sia/nsc_dr2",
        "flip_x": True,
    },
    {
        "survey": "UKIDSS",
        "type": "hips",
        "label": "UKIDSS JHK color",
        "epoch": "2005-2012 coadd",
        "hips": "VOXASTRO/P/UKIDSS/JHK/color",
    },
    {
        "survey": "UHS",
        "type": "hips",
        "label": "UHS DR1 J",
        "epoch": "2012-2018 coadd",
        "hips": "wfau.roe.ac.uk/P/UHSDR1/J",
        "cut_options": UHS_DR1_J_HIPS_CUT_OPTIONS,
    },
    {
        "survey": "VHS",
        "type": "hips",
        "label": "VHS J/Ks color",
        "epoch": "2009-2018 coadd",
        "hips": "VOXASTRO/P/VHS/JKs/color",
    },
)


WISEVIEW_DES_IRG_SOURCE = {
    "label": "DES DR2 IRG",
    "epoch": "2013-2019 coadd",
    "hips": "CDS/P/DES-DR2/ColorIRG",
}


WISEVIEW_DES_YZI_SOURCE = {
    "label": "DES DR2 YZI",
    "epoch": "2013-2019 coadd",
    "red_hips": "CDS/P/DES-DR2/Y",
    "green_hips": "CDS/P/DES-DR2/z",
    "blue_hips": "CDS/P/DES-DR2/i",
}


WISEVIEW_PS1_IZY_SOURCE = {
    "survey": "PS1 DR2 IZY",
    "type": "ps1_color",
    "label": "PS1 DR2 IZY",
    "epoch": "stack coadd",
    "filters": ("i", "z", "y"),
}


WISEVIEW_PS1_IRG_SOURCE = {
    "survey": "PS1 DR2 IRG",
    "type": "ps1_color",
    "label": "PS1 DR2 IRG",
    "epoch": "stack coadd",
    "filters": ("i", "r", "g"),
}


WISEVIEW_PS1_SUPPLEMENT_ROW = (WISEVIEW_PS1_IZY_SOURCE, WISEVIEW_PS1_IRG_SOURCE)


WISEVIEW_UNWISE_COLOR_SOURCE = {
    "survey": "unWISE color",
    "type": "hips",
    "label": "unWISE color",
    "epoch": "coadd",
    "hips": "CDS/P/unWISE/color-W2-W1W2-W1",
    "fov_deg": 15.0 / 60.0,
    "span_columns": True,
}


WISEVIEW_DES_SUPPLEMENT_SURVEY_ROWS = (
    (
        {
            "survey": "UHS",
            "type": "hips",
            "label": "UHS DR1 J",
            "epoch": "2012-2018 coadd",
            "hips": "wfau.roe.ac.uk/P/UHSDR1/J",
            "cut_options": UHS_DR1_J_HIPS_CUT_OPTIONS,
        },
        {
            "survey": "NSC",
            "type": "sia",
            "label": "NSC DR2",
            "epoch": "per-exposure",
            "siaUrl": "https://datalab.noirlab.edu/sia/nsc_dr2",
            "flip_x": True,
        },
    ),
    (
        {
            "survey": "NSC DR2 IZY",
            "type": "sia_color",
            "label": "NSC DR2 IZY",
            "epoch": "per-exposure",
            "siaUrl": "https://datalab.noirlab.edu/sia/nsc_dr2",
            "channels": ("i", "z", "Y"),
            "gains": (1.0, 0.95, 0.9),
            "flip_x": True,
        },
        {
            "survey": "NSC DR1 IRG",
            "type": "first_available",
            "label": "NSC DR1 IRG",
            "candidates": (
                {
                    "survey": "NSC DR1 IRG native",
                    "type": "sia_color",
                    "label": "NSC DR1 IRG",
                    "epoch": "per-exposure",
                    "siaUrl": "https://datalab.noirlab.edu/sia/nsc_dr1",
                    "channels": ("i", "r", "g"),
                    "gains": (1.15, 1.0, 0.9),
                    "flip_x": True,
                },
                {
                    "survey": "NSC DR1 IRG calibrated",
                    "type": "sia_color",
                    "label": "NSC DR1 IRG",
                    "epoch": "calibrated exposures",
                    "siaUrl": "https://datalab.noirlab.edu/sia/calibrated_all",
                    "channels": ("i", "r", "g"),
                    "gains": (1.15, 1.0, 0.9),
                    "flip_x": True,
                },
            ),
        },
    ),
    (
        {
            "survey": "UKIDSS",
            "type": "hips",
            "label": "UKIDSS JHK color",
            "epoch": "2005-2012 coadd",
            "hips": "VOXASTRO/P/UKIDSS/JHK/color",
        },
        {
            "survey": "VHS",
            "type": "hips",
            "label": "VHS J/Ks color",
            "epoch": "2009-2018 coadd",
            "hips": "VOXASTRO/P/VHS/JKs/color",
        },
    ),
    (
        {
            "survey": "2MASS",
            "type": "hips",
            "label": "2MASS color J/H/K",
            "epoch": "1997-2001 coadd",
            "hips": "CDS/P/2MASS/color",
        },
        {
            "survey": "SDSS",
            "type": "hips",
            "label": "SDSS9 color",
            "epoch": "2000-2008 coadd",
            "hips": "CDS/P/SDSS9/color",
        },
    ),
)


def _wiseview_default_size_arcsec() -> float:
    for key, value in WISEVIEW_DEFAULT_PARAMS:
        if key == "size":
            try:
                return float(value)
            except (TypeError, ValueError):
                break
    return 75.0


def _source_key(source: dict[str, object]) -> str:
    return str(source.get("survey") or source.get("label") or source.get("siaUrl") or "")


def _local_xml_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _iter_xml_elements(root: ET.Element, name: str) -> Iterable[ET.Element]:
    for element in root.iter():
        if _local_xml_name(element.tag) == name:
            yield element


def _sia_query_url(
    source: dict[str, object],
    *,
    ra_deg: float,
    dec_deg: float,
    fov_arcsec: Optional[float] = None,
) -> str:
    fov_deg = float(fov_arcsec if fov_arcsec is not None else _wiseview_default_size_arcsec()) / 3600.0
    params = urlencode(
        {
            "POS": f"{float(ra_deg) % 360.0},{float(dec_deg)}",
            "SIZE": f"{fov_deg},{fov_deg}",
            "FORMAT": "ALL",
            "INTERSECT": "OVERLAPS",
            "VERB": "2",
        }
    )
    return f"{source['siaUrl']}?{params}"


def _td_value(cells: Sequence[ET.Element], index_by_name: dict[str, int], name: str) -> str:
    index = index_by_name.get(str(name).lower())
    if index is None or index >= len(cells):
        return ""
    return "".join(cells[index].itertext()).strip()


def _sia_preview_rows(text: str) -> list[dict[str, object]]:
    root = ET.fromstring(text)
    index_by_name: dict[str, int] = {}
    for index, field in enumerate(_iter_xml_elements(root, "FIELD")):
        for key in (field.attrib.get("name"), field.attrib.get("ID")):
            if key:
                index_by_name[str(key).lower()] = index

    rows: list[dict[str, object]] = []
    for table_row in _iter_xml_elements(root, "TR"):
        cells = list(_iter_xml_elements(table_row, "TD"))
        preview = _td_value(cells, index_by_name, "preview").replace("&amp;", "&")
        prodtype = _td_value(cells, index_by_name, "prodtype").lower()
        if not preview or prodtype != "image":
            continue
        try:
            seeing = float(_td_value(cells, index_by_name, "seeing") or "999")
        except ValueError:
            seeing = 999.0
        rows.append(
            {
                "preview": preview,
                "band": _td_value(cells, index_by_name, "obs_bandpass"),
                "date_obs": _td_value(cells, index_by_name, "date_obs"),
                "seeing": seeing,
            }
        )
    return rows


def _parse_sia_preview_source(text: str, source: dict[str, object]) -> dict[str, object]:
    rows = _sia_preview_rows(text)
    if not rows:
        raise ValueError(f"{source.get('label', 'SIA')} returned no image previews")

    band_priority = {"z": 0, "i": 1, "r": 2, "y": 3, "g": 4}
    rows.sort(
        key=lambda row: (
            band_priority.get(str(row["band"]).lower(), len(band_priority)),
            float(row["seeing"]),
        )
    )
    row = rows[0]
    epoch = str(row["date_obs"]).split("T", 1)[0] if row.get("date_obs") else str(source.get("epoch", "unknown"))
    band_text = f" {row['band']}" if row.get("band") else ""
    resolved = dict(source)
    resolved["type"] = "resolved_image"
    resolved["url"] = str(row["preview"])
    resolved["title"] = f"{source.get('label', 'SIA')}{band_text} epoch {epoch} (N up, E left)"
    resolved["flip_x"] = bool(source.get("flip_x", False))
    return resolved


def _parse_sia_color_preview_source(text: str, source: dict[str, object]) -> dict[str, object]:
    rows = _sia_preview_rows(text)
    if not rows:
        raise ValueError(f"{source.get('label', 'SIA')} returned no image previews")

    channels = tuple(str(channel) for channel in source.get("channels", ()))
    if len(channels) != 3:
        raise ValueError(f"{source.get('label', 'SIA')} color source requires exactly 3 channels")

    channel_items: list[dict[str, object]] = []
    for channel in channels:
        channel_rows = [
            row for row in rows
            if str(row.get("band") or "").lower() == channel.lower()
        ]
        if not channel_rows:
            raise ValueError(f"{source.get('label', 'SIA')} returned no {channel}-band image previews")
        channel_rows.sort(
            key=lambda row: (
                float(row["seeing"]),
                str(row.get("date_obs") or ""),
            )
        )
        row = channel_rows[0]
        epoch = str(row["date_obs"]).split("T", 1)[0] if row.get("date_obs") else str(source.get("epoch", "unknown"))
        channel_items.append(
            {
                "band": channel,
                "url": str(row["preview"]),
                "epoch": epoch,
            }
        )

    epochs = [str(item["epoch"]) for item in channel_items if item.get("epoch")]
    unique_epochs = []
    for epoch in epochs:
        if epoch not in unique_epochs:
            unique_epochs.append(epoch)
    epoch_text = unique_epochs[0] if len(unique_epochs) == 1 else "/".join(unique_epochs)
    channel_label = "/".join(channels)
    resolved = dict(source)
    resolved["type"] = "resolved_color_image"
    resolved["channels"] = channel_items
    resolved["title"] = f"{source.get('label', 'SIA')} epoch {epoch_text} ({channel_label} = RGB; N up, E left)"
    resolved["gains"] = tuple(float(value) for value in source.get("gains", (1.0, 1.0, 1.0)))
    resolved["flip_x"] = bool(source.get("flip_x", False))
    return resolved


def resolve_sia_preview_source(
    source: dict[str, object],
    *,
    ra_deg: float,
    dec_deg: float,
    fov_arcsec: Optional[float] = None,
    timeout: float = 8.0,
) -> dict[str, object]:
    request = urllib.request.Request(
        _sia_query_url(source, ra_deg=ra_deg, dec_deg=dec_deg, fov_arcsec=fov_arcsec),
        headers={"User-Agent": "spherex-pipeline-wiseview-vetting/1.0"},
    )
    with urllib.request.urlopen(request, timeout=float(timeout)) as response:
        text = response.read().decode("utf-8", errors="replace")
    if source.get("type") == "sia_color":
        return _parse_sia_color_preview_source(text, source)
    return _parse_sia_preview_source(text, source)


def _iter_sia_sources(value: object) -> Iterable[dict[str, object]]:
    if isinstance(value, dict):
        if value.get("type") in {"sia", "sia_color"}:
            yield value
        for child in value.values():
            yield from _iter_sia_sources(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_sia_sources(child)


def _pending_sia_source(source: dict[str, object]) -> dict[str, object]:
    pending = dict(source)
    pending["type"] = "pending_sia"
    pending["message"] = "Resolving SIA preview outside browser..."
    return pending


def _apply_resolved_sia_sources(
    value: object,
    resolved_sia_sources: Optional[dict[str, dict[str, object]]],
) -> object:
    if isinstance(value, dict):
        if value.get("type") in {"sia", "sia_color"}:
            resolved = (resolved_sia_sources or {}).get(_source_key(value))
            return dict(resolved) if resolved is not None else _pending_sia_source(value)
        return {
            str(key): _apply_resolved_sia_sources(child, resolved_sia_sources)
            for key, child in value.items()
        }
    if isinstance(value, tuple):
        return tuple(_apply_resolved_sia_sources(child, resolved_sia_sources) for child in value)
    if isinstance(value, list):
        return [_apply_resolved_sia_sources(child, resolved_sia_sources) for child in value]
    return value


def _source_signature(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def build_wiseview_ps1_fallback_cutout_js(
    *,
    moca_oid: int,
    ra_deg: float,
    dec_deg: float,
    fov_arcsec: Optional[float] = None,
    resolved_sia_sources: Optional[dict[str, dict[str, object]]] = None,
) -> str:
    fallback_id = json.dumps(WISEVIEW_PS1_FALLBACK_CUTOUT_ID)
    sources = _apply_resolved_sia_sources(WISEVIEW_PS1_FALLBACK_CUTOUT_SOURCES, resolved_sia_sources)
    payload = {
        "moca_oid": int(moca_oid),
        "ra_deg": float(ra_deg) % 360.0,
        "dec_deg": float(dec_deg),
        "fov_deg": float(fov_arcsec if fov_arcsec is not None else _wiseview_default_size_arcsec()) / 3600.0,
        "sources": sources,
        "source_signature": _source_signature(sources),
    }
    payload_json = json.dumps(payload)
    return f"""
(function (payload) {{
  const fallbackId = {fallback_id};
  const state = window.__wiseviewVettingPs1FallbackState || {{}};
  const sourceSignature = String(payload.source_signature || "");
  if (state.mocaOid !== payload.moca_oid || state.sourceSignature !== sourceSignature) {{
    state.mocaOid = payload.moca_oid;
    state.sourceSignature = sourceSignature;
    state.pending = false;
    state.done = false;
    state.failed = false;
    state.lastError = "";
  }}
  window.__wiseviewVettingPs1FallbackState = state;

  function ps1Container() {{
    return document.querySelector("#pawnstars");
  }}

  function visibleRect(element) {{
    if (!element) {{
      return null;
    }}
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      Number(style.opacity || 1) === 0 ||
      rect.width < 40 ||
      rect.height < 40
    ) {{
      return null;
    }}
    return rect;
  }}

  function mainImageTarget() {{
    const selectors = ["#overlayCanvas", "#daCanvas", "#image canvas", "#image img", "#image svg", "#image video"];
    for (const selector of selectors) {{
      const element = document.querySelector(selector);
      if (visibleRect(element)) {{
        return element;
      }}
    }}
    return null;
  }}

  function nativePs1Image() {{
    const image = document.querySelector("#pawnstars img");
    if (!image || image.dataset.wiseviewFallbackCutout === "1") {{
      return null;
    }}
    return image;
  }}

  function isLoadedImage(image) {{
    return Boolean(
      image &&
      image.complete &&
      image.naturalWidth > 20 &&
      image.naturalHeight > 20
    );
  }}

  function hasNativePs1Cutout() {{
    return isLoadedImage(nativePs1Image());
  }}

  function currentFovDeg() {{
    const sizeInput = document.querySelector("#sizeInput");
    const sizeInputValue = Number(sizeInput && sizeInput.value);
    if (Number.isFinite(sizeInputValue) && sizeInputValue > 0) {{
      return sizeInputValue / 3600.0;
    }}
    const hash = String(window.location.hash || "").replace(/^#/, "");
    const hashParams = new URLSearchParams(hash);
    const hashSizeValue = Number(hashParams.get("size"));
    if (Number.isFinite(hashSizeValue) && hashSizeValue > 0) {{
      return hashSizeValue / 3600.0;
    }}
    return Number(payload.fov_deg || {float(_wiseview_default_size_arcsec()) / 3600.0});
  }}

  function fallbackPixelWidth() {{
    const mainRect = visibleRect(mainImageTarget());
    if (mainRect) {{
      return Math.max(180, Math.round(mainRect.width));
    }}
    const containerRect = visibleRect(ps1Container());
    if (containerRect) {{
      return Math.max(180, Math.min(520, Math.round(containerRect.width)));
    }}
    return 420;
  }}

  function applyFallbackSizing(container, panel) {{
    const width = fallbackPixelWidth();
    if (container) {{
      container.style.width = `${{width}}px`;
      container.style.maxWidth = `${{width}}px`;
      container.style.height = "auto";
    }}
    panel.style.width = `${{width}}px`;
    panel.style.maxWidth = `${{width}}px`;
    panel.style.height = "auto";
  }}

  function existingFallback() {{
    const panel = document.getElementById(fallbackId);
    if (!panel || panel.dataset.mocaOid !== String(payload.moca_oid)) {{
      return null;
    }}
    return panel;
  }}

  function setFallbackMessage(message) {{
    const container = ps1Container();
    if (!container) {{
      return;
    }}
    let panel = existingFallback();
    if (!panel) {{
      panel = document.createElement("div");
      panel.id = fallbackId;
      panel.dataset.mocaOid = String(payload.moca_oid);
      panel.style.boxSizing = "border-box";
      panel.style.width = "100%";
      panel.style.height = "100%";
      panel.style.minHeight = "140px";
      panel.style.display = "flex";
      panel.style.flexDirection = "column";
      panel.style.justifyContent = "center";
      panel.style.alignItems = "center";
      panel.style.background = "black";
      panel.style.color = "white";
      panel.style.font = "13px sans-serif";
      panel.style.textAlign = "center";
      panel.style.padding = "6px";
      container.replaceChildren(panel);
    }}
    applyFallbackSizing(container, panel);
    panel.replaceChildren();
    panel.textContent = message;
  }}

  function hips2fitsUrl(candidate) {{
    const fovDeg = currentFovDeg();
    const pixelWidth = Math.max(180, Math.min(900, fallbackPixelWidth()));
    const cutOptions = candidate.cut_options || {{}};
    const params = new URLSearchParams();
    params.set("hips", candidate.hips);
    params.set("width", String(pixelWidth));
    params.set("height", String(pixelWidth));
    params.set("projection", "TAN");
    params.set("ra", String(payload.ra_deg));
    params.set("dec", String(payload.dec_deg));
    params.set("fov", String(fovDeg));
    params.set("coordsys", "icrs");
    params.set("rotation_angle", "0");
    params.set("format", "png");
    params.set("min_cut", cutOptions.minCut || "1%");
    params.set("max_cut", cutOptions.maxCut || "99%");
    params.set("stretch", cutOptions.stretch || "asinh");
    params.set("cmap", cutOptions.cmap || "Greys_r");
    return "https://alasky.cds.unistra.fr/hips-image-services/hips2fits?" + params.toString();
  }}

  function siaUrl(candidate) {{
    const fovDeg = currentFovDeg();
    const params = new URLSearchParams();
    params.set("POS", `${{payload.ra_deg}},${{payload.dec_deg}}`);
    params.set("SIZE", `${{fovDeg}},${{fovDeg}}`);
    params.set("FORMAT", "ALL");
    params.set("INTERSECT", "OVERLAPS");
    params.set("VERB", "2");
    return candidate.siaUrl + "?" + params.toString();
  }}

  function fieldIndexByName(doc) {{
    const fields = Array.from(doc.querySelectorAll("FIELD"));
    const indexByName = {{}};
    fields.forEach(function (field, index) {{
      for (const key of [field.getAttribute("name"), field.getAttribute("ID")]) {{
        if (key) {{
          indexByName[key.toLowerCase()] = index;
        }}
      }}
    }});
    return indexByName;
  }}

  function tdValue(cells, indexByName, name) {{
    const index = indexByName[String(name).toLowerCase()];
    if (index === undefined || !cells[index]) {{
      return "";
    }}
    return (cells[index].textContent || "").trim();
  }}

  function parseNscPreview(text, candidate) {{
    const doc = new DOMParser().parseFromString(text, "application/xml");
    if (doc.querySelector("parsererror")) {{
      throw new Error("NSC SIA XML parse failed");
    }}
    const indexByName = fieldIndexByName(doc);
    const rows = Array.from(doc.querySelectorAll("TR")).map(function (row) {{
      const cells = Array.from(row.querySelectorAll("TD"));
      return {{
        preview: tdValue(cells, indexByName, "preview").replace(/&amp;/g, "&"),
        band: tdValue(cells, indexByName, "obs_bandpass"),
        dateObs: tdValue(cells, indexByName, "date_obs"),
        prodtype: tdValue(cells, indexByName, "prodtype"),
        proctype: tdValue(cells, indexByName, "proctype"),
        seeing: Number(tdValue(cells, indexByName, "seeing") || "999"),
      }};
    }}).filter(function (row) {{
      return row.preview && row.prodtype.toLowerCase() === "image";
    }});
    if (!rows.length) {{
      throw new Error("NSC SIA returned no image previews");
    }}
    const bandPriority = ["z", "i", "r", "Y", "g"];
    rows.sort(function (left, right) {{
      const leftBand = bandPriority.indexOf(left.band);
      const rightBand = bandPriority.indexOf(right.band);
      const leftPriority = leftBand === -1 ? bandPriority.length : leftBand;
      const rightPriority = rightBand === -1 ? bandPriority.length : rightBand;
      if (leftPriority !== rightPriority) {{
        return leftPriority - rightPriority;
      }}
      return left.seeing - right.seeing;
    }});
    const row = rows[0];
    const epoch = row.dateObs ? row.dateObs.split("T")[0] : candidate.epoch;
    const bandText = row.band ? ` ${{row.band}}` : "";
    return {{
      url: row.preview,
      title: `${{candidate.label}}${{bandText}} epoch ${{epoch}} (N up, E left)`,
      flip_x: Boolean(candidate.flip_x),
    }};
  }}

  async function resolveCandidate(candidate) {{
    if (candidate.type === "hips") {{
      return {{
        url: hips2fitsUrl(candidate),
        title: `${{candidate.label}} epoch ${{candidate.epoch}} (N up, E left)`,
      }};
    }}
    if (candidate.type === "sia") {{
      const response = await fetch(siaUrl(candidate), {{cache: "force-cache"}});
      if (!response.ok) {{
        throw new Error(`${{candidate.label}} SIA HTTP ${{response.status}}`);
      }}
      return parseNscPreview(await response.text(), candidate);
    }}
    if (candidate.type === "resolved_image") {{
      return {{
        url: candidate.url,
        title: candidate.title || `${{candidate.label}} (N up, E left)`,
        flip_x: Boolean(candidate.flip_x),
      }};
    }}
    if (candidate.type === "pending_sia") {{
      throw new Error(`${{candidate.label}} SIA preview is still resolving`);
    }}
    throw new Error(`Unknown fallback cutout type: ${{candidate.type}}`);
  }}

  function loadImage(src) {{
    return new Promise(function (resolve, reject) {{
      const image = new Image();
      const timeout = window.setTimeout(function () {{
        reject(new Error("image load timed out"));
      }}, 15000);
      image.onload = function () {{
        window.clearTimeout(timeout);
        if (image.naturalWidth > 20 && image.naturalHeight > 20) {{
          resolve(image);
        }} else {{
          reject(new Error("loaded image is empty"));
        }}
      }};
      image.onerror = function () {{
        window.clearTimeout(timeout);
        reject(new Error("image load failed"));
      }};
      image.src = src;
    }});
  }}

  function showFallback(image, resolved) {{
    const container = ps1Container();
    if (!container || hasNativePs1Cutout()) {{
      return;
    }}
    const panel = document.createElement("div");
    panel.id = fallbackId;
    panel.dataset.mocaOid = String(payload.moca_oid);
    panel.style.boxSizing = "border-box";
    panel.style.width = "100%";
    panel.style.height = "100%";
    panel.style.minHeight = "140px";
    panel.style.display = "flex";
    panel.style.flexDirection = "column";
    panel.style.alignItems = "stretch";
    panel.style.justifyContent = "center";
    panel.style.background = "black";
    panel.style.color = "white";
    panel.style.font = "12px sans-serif";
    panel.style.overflow = "hidden";
    applyFallbackSizing(container, panel);

    const title = document.createElement("div");
    title.textContent = resolved.title;
    title.style.flex = "0 0 auto";
    title.style.padding = "3px 4px";
    title.style.lineHeight = "1.15";
    title.style.overflowWrap = "anywhere";
    panel.appendChild(title);

    image.dataset.wiseviewFallbackCutout = "1";
    image.alt = resolved.title;
    image.style.display = "block";
    image.style.flex = "1 1 auto";
    image.style.minHeight = "0";
    image.style.width = "100%";
    image.style.height = "auto";
    image.style.aspectRatio = "1 / 1";
    image.style.objectFit = "contain";
    image.style.background = "black";
    if (resolved.flip_x) {{
      image.style.transform = "scaleX(-1)";
      image.style.transformOrigin = "center center";
    }}
    panel.appendChild(image);
    container.replaceChildren(panel);
    window.setTimeout(function () {{
      window.dispatchEvent(new Event("resize"));
    }}, 0);
  }}

  async function tryCandidates(index) {{
    if (hasNativePs1Cutout()) {{
      state.pending = false;
      state.done = false;
      return;
    }}
    if (index >= payload.sources.length) {{
      state.pending = false;
      state.failed = true;
      setFallbackMessage("No PS1/DES/NSC/UKIDSS/UHS/VHS cutout found");
      return;
    }}
    const candidate = payload.sources[index];
    try {{
      const resolved = await resolveCandidate(candidate);
      const image = await loadImage(resolved.url);
      showFallback(image, resolved);
      state.pending = false;
      state.done = true;
    }} catch (error) {{
      state.lastError = `${{candidate.survey}}: ${{error && error.message ? error.message : error}}`;
      tryCandidates(index + 1);
    }}
  }}

  if (!ps1Container() || hasNativePs1Cutout() || existingFallback() || state.pending || state.done) {{
    return;
  }}
  state.pending = true;
  tryCandidates(0);
}})({payload_json});
"""


def build_wiseview_des_supplement_cutouts_js(
    *,
    moca_oid: int,
    ra_deg: float,
    dec_deg: float,
    fov_arcsec: Optional[float] = None,
    resolved_sia_sources: Optional[dict[str, dict[str, object]]] = None,
) -> str:
    panel_id = json.dumps(WISEVIEW_DES_SUPPLEMENT_CUTOUTS_ID)
    survey_rows = _apply_resolved_sia_sources(WISEVIEW_DES_SUPPLEMENT_SURVEY_ROWS, resolved_sia_sources)
    payload = {
        "moca_oid": int(moca_oid),
        "ra_deg": float(ra_deg) % 360.0,
        "dec_deg": float(dec_deg),
        "fov_deg": float(fov_arcsec if fov_arcsec is not None else _wiseview_default_size_arcsec()) / 3600.0,
        "irg": WISEVIEW_DES_IRG_SOURCE,
        "yzi": WISEVIEW_DES_YZI_SOURCE,
        "ps1_row": WISEVIEW_PS1_SUPPLEMENT_ROW,
        "unwise_row": (WISEVIEW_UNWISE_COLOR_SOURCE,),
        "survey_rows": survey_rows,
        "source_signature": _source_signature((WISEVIEW_PS1_SUPPLEMENT_ROW, WISEVIEW_UNWISE_COLOR_SOURCE, survey_rows)),
    }
    payload_json = json.dumps(payload)
    return f"""
(function (payload) {{
  const panelId = {panel_id};
  const state = window.__wiseviewVettingDesSupplementState || {{}};
  const sourceSignature = String(payload.source_signature || "");
  if (state.mocaOid !== payload.moca_oid || state.sourceSignature !== sourceSignature) {{
    state.mocaOid = payload.moca_oid;
    state.sourceSignature = sourceSignature;
    state.pending = false;
    state.done = false;
    state.lastError = "";
  }}
  window.__wiseviewVettingDesSupplementState = state;

  function visibleRect(element) {{
    if (!element) {{
      return null;
    }}
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      Number(style.opacity || 1) === 0 ||
      rect.width < 40 ||
      rect.height < 40
    ) {{
      return null;
    }}
    return rect;
  }}

  function mainImageTarget() {{
    const selectors = ["#overlayCanvas", "#daCanvas", "#image canvas", "#image img", "#image svg", "#image video"];
    for (const selector of selectors) {{
      const element = document.querySelector(selector);
      if (visibleRect(element)) {{
        return element;
      }}
    }}
    return null;
  }}

  function currentFovDeg() {{
    const sizeInput = document.querySelector("#sizeInput");
    const sizeInputValue = Number(sizeInput && sizeInput.value);
    if (Number.isFinite(sizeInputValue) && sizeInputValue > 0) {{
      return sizeInputValue / 3600.0;
    }}
    const hash = String(window.location.hash || "").replace(/^#/, "");
    const hashParams = new URLSearchParams(hash);
    const hashSizeValue = Number(hashParams.get("size"));
    if (Number.isFinite(hashSizeValue) && hashSizeValue > 0) {{
      return hashSizeValue / 3600.0;
    }}
    return Number(payload.fov_deg || {float(_wiseview_default_size_arcsec()) / 3600.0});
  }}

  function supplementWidth() {{
    const mainRect = visibleRect(mainImageTarget());
    if (mainRect) {{
      return Math.min(
        Math.max(720, Math.round(mainRect.width * 2 + 6)),
        Math.max(720, Math.round(window.innerWidth - 24))
      );
    }}
    const ps1Rect = visibleRect(document.querySelector("#pawnstars"));
    if (ps1Rect) {{
      return Math.min(
        Math.max(720, Math.round(ps1Rect.width * 2 + 6)),
        Math.max(720, Math.round(window.innerWidth - 24))
      );
    }}
    return Math.max(720, Math.round(window.innerWidth - 24));
  }}

  function imagePixelWidth() {{
    return Math.max(320, Math.min(1100, Math.floor((supplementWidth() - 8) / 2)));
  }}

  function anchorElement() {{
    return document.querySelector("#pawnstarsLink") || document.querySelector("#pawnstars");
  }}

  function ensurePanel() {{
    const anchor = anchorElement();
    if (!anchor) {{
      return null;
    }}
    let panel = document.getElementById(panelId);
    if (!panel) {{
      panel = document.createElement("div");
      panel.id = panelId;
      panel.style.boxSizing = "border-box";
      panel.style.display = "grid";
      panel.style.gridTemplateColumns = "minmax(0, 1fr) minmax(0, 1fr)";
      panel.style.gap = "6px";
      panel.style.marginTop = "6px";
      panel.style.background = "black";
      panel.style.color = "white";
      panel.style.font = "12px sans-serif";
      panel.style.overflow = "hidden";
      anchor.insertAdjacentElement("afterend", panel);
    }}
    const width = supplementWidth();
    panel.dataset.mocaOid = String(payload.moca_oid);
    panel.style.width = `${{width}}px`;
    panel.style.maxWidth = `${{width}}px`;
    return panel;
  }}

  function makeCard(titleText) {{
    const card = document.createElement("div");
    card.style.boxSizing = "border-box";
    card.style.display = "flex";
    card.style.flexDirection = "column";
    card.style.alignItems = "stretch";
    card.style.justifyContent = "center";
    card.style.minWidth = "0";
    card.style.background = "black";
    card.style.overflow = "hidden";

    const title = document.createElement("div");
    title.textContent = titleText;
    title.style.flex = "0 0 auto";
    title.style.padding = "3px 4px";
    title.style.lineHeight = "1.15";
    title.style.overflowWrap = "anywhere";
    card.appendChild(title);
    return card;
  }}

  function showMessage(panel, message) {{
    panel.replaceChildren();
    const card = makeCard(message);
    card.style.gridColumn = "1 / span 2";
    card.style.minHeight = "90px";
    card.style.textAlign = "center";
    card.style.alignItems = "center";
    panel.appendChild(card);
  }}

  function makeErrorCard(titleText, error) {{
    const card = makeCard(titleText);
    const message = document.createElement("div");
    message.textContent = error && error.message ? error.message : String(error);
    message.style.flex = "1 1 auto";
    message.style.display = "flex";
    message.style.alignItems = "center";
    message.style.justifyContent = "center";
    message.style.minHeight = "120px";
    message.style.padding = "6px";
    message.style.textAlign = "center";
    message.style.lineHeight = "1.2";
    card.appendChild(message);
    return card;
  }}

  function makeInfoCard(titleText, messageText) {{
    const card = makeCard(titleText);
    const message = document.createElement("div");
    message.textContent = messageText;
    message.style.flex = "1 1 auto";
    message.style.display = "flex";
    message.style.alignItems = "center";
    message.style.justifyContent = "center";
    message.style.minHeight = "120px";
    message.style.padding = "6px";
    message.style.textAlign = "center";
    message.style.lineHeight = "1.2";
    card.appendChild(message);
    return card;
  }}

  function hips2fitsUrl(hips, options, fovDegOverride, fullWidth) {{
    if (hips === "CDS/P/2MASS/color") {{
      const params = new URLSearchParams({{
        mode: "getImage", file_type: "colorimage", survey: "2mass",
        subsetsize: String(currentFovDeg() * 60), RA: String(payload.ra_deg),
        DEC: String(payload.dec_deg), reproject: "true"
      }});
      return "https://irsa.ipac.caltech.edu/applications/finderchart/servlet/api?" + params.toString();
    }}
    const cutOptions = options || {{}};
    const params = new URLSearchParams();
    const pixelWidth = fullWidth ? Math.max(320, Math.min(1400, supplementWidth())) : imagePixelWidth();
    const overrideFovDeg = Number(fovDegOverride);
    const fovDeg = Number.isFinite(overrideFovDeg) && overrideFovDeg > 0 ? overrideFovDeg : currentFovDeg();
    params.set("hips", hips);
    params.set("width", String(pixelWidth));
    params.set("height", String(pixelWidth));
    params.set("projection", "TAN");
    params.set("ra", String(payload.ra_deg));
    params.set("dec", String(payload.dec_deg));
    params.set("fov", String(fovDeg));
    params.set("coordsys", "icrs");
    params.set("rotation_angle", "0");
    params.set("format", "png");
    params.set("min_cut", cutOptions.minCut || "1%");
    params.set("max_cut", cutOptions.maxCut || "99%");
    params.set("stretch", cutOptions.stretch || "asinh");
    params.set("cmap", cutOptions.cmap || "Greys_r");
    return "https://alasky.cds.unistra.fr/hips-image-services/hips2fits?" + params.toString();
  }}

  function siaUrl(source) {{
    const fovDeg = currentFovDeg();
    const params = new URLSearchParams();
    params.set("POS", `${{payload.ra_deg}},${{payload.dec_deg}}`);
    params.set("SIZE", `${{fovDeg}},${{fovDeg}}`);
    params.set("FORMAT", "ALL");
    params.set("INTERSECT", "OVERLAPS");
    params.set("VERB", "2");
    return source.siaUrl + "?" + params.toString();
  }}

  function ps1CutoutSizePixels() {{
    const fovArcsec = currentFovDeg() * 3600.0;
    return Math.max(32, Math.min(4096, Math.round(fovArcsec / 0.25)));
  }}

  function ps1FilenamesUrl(source) {{
    const params = new URLSearchParams();
    params.set("ra", String(payload.ra_deg));
    params.set("dec", String(payload.dec_deg));
    params.set("filters", (source.filters || []).join(""));
    return "https://ps1images.stsci.edu/cgi-bin/ps1filenames.py?" + params.toString();
  }}

  function parsePs1Filenames(text, source) {{
    const lines = String(text || "").split(/\\r?\\n/).map(function (line) {{
      return line.trim();
    }}).filter(Boolean);
    const headerIndex = lines.findIndex(function (line) {{
      return /\\bfilter\\b/.test(line) && /\\bfilename\\b/.test(line);
    }});
    if (headerIndex < 0) {{
      throw new Error(`${{source.label}} filename table has no header`);
    }}
    const header = lines[headerIndex].split(/\\s+/);
    const filterIndex = header.indexOf("filter");
    const filenameIndex = header.indexOf("filename");
    if (filterIndex < 0 || filenameIndex < 0) {{
      throw new Error(`${{source.label}} filename table is missing filter/filename columns`);
    }}
    const filenameByFilter = {{}};
    for (const line of lines.slice(headerIndex + 1)) {{
      const parts = line.split(/\\s+/);
      if (parts.length <= Math.max(filterIndex, filenameIndex)) {{
        continue;
      }}
      const band = parts[filterIndex];
      const filename = parts[filenameIndex];
      if (!filename || !filename.includes(".fits")) {{
        continue;
      }}
      if (!filenameByFilter[band]) {{
        filenameByFilter[band] = filename;
      }}
    }}
    const filters = Array.isArray(source.filters) ? source.filters : [];
    if (filters.length !== 3) {{
      throw new Error(`${{source.label}} needs 3 PS1 filters`);
    }}
    const filenames = filters.map(function (filter) {{
      const filename = filenameByFilter[filter];
      if (!filename) {{
        throw new Error(`${{source.label}} has no PS1 ${{filter}} image at this position`);
      }}
      return filename;
    }});
    return {{red: filenames[0], green: filenames[1], blue: filenames[2]}};
  }}

  function ps1FitsCutUrl(filenames) {{
    const params = new URLSearchParams();
    params.set("ra", String(payload.ra_deg));
    params.set("dec", String(payload.dec_deg));
    params.set("size", String(ps1CutoutSizePixels()));
    params.set("output_size", String(imagePixelWidth()));
    params.set("format", "png");
    params.set("red", filenames.red);
    params.set("green", filenames.green);
    params.set("blue", filenames.blue);
    return "https://ps1images.stsci.edu/cgi-bin/fitscut.cgi?" + params.toString();
  }}

  function fieldIndexByName(doc) {{
    const fields = Array.from(doc.querySelectorAll("FIELD"));
    const indexByName = {{}};
    fields.forEach(function (field, index) {{
      for (const key of [field.getAttribute("name"), field.getAttribute("ID")]) {{
        if (key) {{
          indexByName[key.toLowerCase()] = index;
        }}
      }}
    }});
    return indexByName;
  }}

  function tdValue(cells, indexByName, name) {{
    const index = indexByName[String(name).toLowerCase()];
    if (index === undefined || !cells[index]) {{
      return "";
    }}
    return (cells[index].textContent || "").trim();
  }}

  function parseNscPreview(text, source) {{
    const doc = new DOMParser().parseFromString(text, "application/xml");
    if (doc.querySelector("parsererror")) {{
      throw new Error("NSC SIA XML parse failed");
    }}
    const indexByName = fieldIndexByName(doc);
    const rows = Array.from(doc.querySelectorAll("TR")).map(function (row) {{
      const cells = Array.from(row.querySelectorAll("TD"));
      return {{
        preview: tdValue(cells, indexByName, "preview").replace(/&amp;/g, "&"),
        band: tdValue(cells, indexByName, "obs_bandpass"),
        dateObs: tdValue(cells, indexByName, "date_obs"),
        prodtype: tdValue(cells, indexByName, "prodtype"),
        seeing: Number(tdValue(cells, indexByName, "seeing") || "999"),
      }};
    }}).filter(function (row) {{
      return row.preview && row.prodtype.toLowerCase() === "image";
    }});
    if (!rows.length) {{
      throw new Error("NSC SIA returned no image previews");
    }}
    const bandPriority = ["z", "i", "r", "Y", "g"];
    rows.sort(function (left, right) {{
      const leftBand = bandPriority.indexOf(left.band);
      const rightBand = bandPriority.indexOf(right.band);
      const leftPriority = leftBand === -1 ? bandPriority.length : leftBand;
      const rightPriority = rightBand === -1 ? bandPriority.length : rightBand;
      if (leftPriority !== rightPriority) {{
        return leftPriority - rightPriority;
      }}
      return left.seeing - right.seeing;
    }});
    const row = rows[0];
    const epoch = row.dateObs ? row.dateObs.split("T")[0] : source.epoch;
    const bandText = row.band ? ` ${{row.band}}` : "";
    return {{
      url: row.preview,
      title: `${{source.label}}${{bandText}} epoch ${{epoch}} (N up, E left)`,
      flip_x: Boolean(source.flip_x),
    }};
  }}

  async function resolveSource(source) {{
    if (source.type === "hips") {{
      return {{
        url: hips2fitsUrl(source.hips, source.cut_options, source.fov_deg, Boolean(source.span_columns)),
        title: `${{source.label}} epoch ${{source.epoch}} (N up, E left)`,
      }};
    }}
    if (source.type === "sia") {{
      const response = await fetch(siaUrl(source), {{cache: "force-cache"}});
      if (!response.ok) {{
        throw new Error(`${{source.label}} SIA HTTP ${{response.status}}`);
      }}
      return parseNscPreview(await response.text(), source);
    }}
    if (source.type === "ps1_color") {{
      const response = await fetch(ps1FilenamesUrl(source), {{cache: "force-cache"}});
      if (!response.ok) {{
        throw new Error(`${{source.label}} filenames HTTP ${{response.status}}`);
      }}
      const filenames = parsePs1Filenames(await response.text(), source);
      const channelLabel = (source.filters || []).join("/");
      return {{
        url: ps1FitsCutUrl(filenames),
        title: `${{source.label}} epoch ${{source.epoch}} (${{channelLabel}} = RGB; N up, E left)`,
        cross_origin: false,
      }};
    }}
    if (source.type === "resolved_image") {{
      return {{
        url: source.url,
        title: source.title || `${{source.label}} (N up, E left)`,
        flip_x: Boolean(source.flip_x),
      }};
    }}
    if (source.type === "resolved_color_image") {{
      return source;
    }}
    if (source.type === "pending_sia") {{
      throw new Error(`${{source.label}} SIA preview is still resolving`);
    }}
    if (source.type === "first_available") {{
      let lastError = null;
      for (const candidate of source.candidates || []) {{
        try {{
          const resolved = await resolveSource(candidate);
          if (resolved.type === "resolved_color_image") {{
            return {{resolved: resolved, image: null}};
          }}
          const image = await loadImage(resolved.url);
          return {{resolved: resolved, image: image}};
        }} catch (error) {{
          lastError = error;
        }}
      }}
      throw lastError || new Error(`${{source.label}} unavailable`);
    }}
    throw new Error(`Unknown supplement cutout type: ${{source.type}}`);
  }}

  function loadImage(src, options) {{
    return new Promise(function (resolve, reject) {{
      const image = new Image();
      if (!options || options.crossOrigin !== false) {{
        image.crossOrigin = "anonymous";
      }}
      const timeout = window.setTimeout(function () {{
        reject(new Error("image load timed out"));
      }}, 15000);
      image.onload = function () {{
        window.clearTimeout(timeout);
        if (image.naturalWidth > 20 && image.naturalHeight > 20) {{
          resolve(image);
        }} else {{
          reject(new Error("loaded image is empty"));
        }}
      }};
      image.onerror = function () {{
        window.clearTimeout(timeout);
        reject(new Error("image load failed"));
      }};
      image.src = src;
    }});
  }}

  function styleImageElement(image) {{
    image.style.display = "block";
    image.style.width = "100%";
    image.style.height = "100%";
    image.style.aspectRatio = "1 / 1";
    image.style.objectFit = "contain";
    image.style.background = "black";
  }}

  function applyResolvedImageOrientation(image, resolved) {{
    if (resolved && resolved.flip_x) {{
      image.style.transform = "scaleX(-1)";
      image.style.transformOrigin = "center center";
    }}
  }}

  function makeCrosshairPart(left, top, width, height) {{
    const part = document.createElement("div");
    part.style.position = "absolute";
    part.style.left = left;
    part.style.top = top;
    part.style.width = width;
    part.style.height = height;
    part.style.background = "#00e7ff";
    part.style.boxShadow = "0 0 2px black";
    return part;
  }}

  function wrapWithCrosshair(content) {{
    const wrapper = document.createElement("div");
    wrapper.style.position = "relative";
    wrapper.style.width = "100%";
    wrapper.style.aspectRatio = "1 / 1";
    wrapper.style.background = "black";
    wrapper.style.overflow = "hidden";
    content.style.display = "block";
    content.style.width = "100%";
    content.style.height = "100%";
    content.style.objectFit = "contain";
    wrapper.appendChild(content);

    const marker = document.createElement("div");
    marker.style.position = "absolute";
    marker.style.left = "50%";
    marker.style.top = "50%";
    marker.style.width = "0";
    marker.style.height = "0";
    marker.style.pointerEvents = "none";
    marker.appendChild(makeCrosshairPart("-28px", "0", "22px", "2px"));
    marker.appendChild(makeCrosshairPart("6px", "0", "22px", "2px"));
    marker.appendChild(makeCrosshairPart("0", "-28px", "2px", "22px"));
    marker.appendChild(makeCrosshairPart("0", "6px", "2px", "22px"));
    wrapper.appendChild(marker);
    return wrapper;
  }}

  function applySourceCardLayout(card, source) {{
    if (source && source.span_columns) {{
      card.style.gridColumn = "1 / span 2";
    }}
    return card;
  }}

  function grayscaleData(image, size) {{
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d", {{willReadFrequently: true}});
    context.drawImage(image, 0, 0, size, size);
    return context.getImageData(0, 0, size, size).data;
  }}

  function channelValue(data, index, gain) {{
    const raw = data[index] / 255.0;
    const black = 0.025;
    const scaled = Math.max(0, (raw - black) / (1.0 - black));
    return Math.pow(scaled, 1.12) * gain;
  }}

  function colorPreservingPixel(red, green, blue) {{
    const gray = (red + green + blue) / 3.0;
    const saturation = 1.55;
    let outRed = gray + saturation * (red - gray);
    let outGreen = gray + saturation * (green - gray);
    let outBlue = gray + saturation * (blue - gray);
    outRed = Math.max(0, outRed);
    outGreen = Math.max(0, outGreen);
    outBlue = Math.max(0, outBlue);
    const peak = Math.max(outRed, outGreen, outBlue, 1.0);
    return [
      Math.round(255 * outRed / peak),
      Math.round(255 * outGreen / peak),
      Math.round(255 * outBlue / peak),
    ];
  }}

  function composeColorCanvas(images, gains) {{
    const size = imagePixelWidth();
    const redData = grayscaleData(images[0], size);
    const greenData = grayscaleData(images[1], size);
    const blueData = grayscaleData(images[2], size);
    const channelGains = Array.isArray(gains) && gains.length === 3 ? gains : [1.0, 1.0, 1.0];
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d", {{willReadFrequently: true}});
    const output = context.createImageData(size, size);
    for (let index = 0; index < output.data.length; index += 4) {{
      const rgb = colorPreservingPixel(
        channelValue(redData, index, Number(channelGains[0] || 1.0)),
        channelValue(greenData, index, Number(channelGains[1] || 1.0)),
        channelValue(blueData, index, Number(channelGains[2] || 1.0))
      );
      output.data[index] = rgb[0];
      output.data[index + 1] = rgb[1];
      output.data[index + 2] = rgb[2];
      output.data[index + 3] = 255;
    }}
    context.putImageData(output, 0, 0);
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.aspectRatio = "1 / 1";
    canvas.style.background = "black";
    return canvas;
  }}

  function composeYziCanvas(redImage, greenImage, blueImage) {{
    return composeColorCanvas([redImage, greenImage, blueImage], [1.60, 0.90, 0.70]);
  }}

  async function buildIrgCard() {{
    const source = payload.irg;
    const image = await loadImage(hips2fitsUrl(source.hips));
    styleImageElement(image);
    const card = makeCard(`${{source.label}} epoch ${{source.epoch}} (N up, E left)`);
    card.appendChild(wrapWithCrosshair(image));
    return card;
  }}

  async function buildYziCard() {{
    const source = payload.yzi;
    const yziCuts = {{maxCut: "99.9%"}};
    const images = await Promise.all([
      loadImage(hips2fitsUrl(source.red_hips, yziCuts)),
      loadImage(hips2fitsUrl(source.green_hips, yziCuts)),
      loadImage(hips2fitsUrl(source.blue_hips, yziCuts)),
    ]);
    const card = makeCard(`${{source.label}} epoch ${{source.epoch}} (Y/Z/I = RGB; N up, E left)`);
    card.appendChild(wrapWithCrosshair(composeYziCanvas(images[0], images[1], images[2])));
    return card;
  }}

  async function buildResolvedColorCard(source) {{
    const channels = Array.isArray(source.channels) ? source.channels : [];
    if (channels.length !== 3) {{
      throw new Error(`${{source.label || source.survey}} color source needs 3 channels`);
    }}
    const images = await Promise.all(channels.map(function (channel) {{
      return loadImage(channel.url);
    }}));
    const canvas = composeColorCanvas(images, source.gains || [1.0, 1.0, 1.0]);
    applyResolvedImageOrientation(canvas, source);
    const card = makeCard(source.title || `${{source.label || source.survey}} (N up, E left)`);
    card.appendChild(wrapWithCrosshair(canvas));
    return card;
  }}

  async function buildSurveyCard(source) {{
    if (source.type === "pending_sia") {{
      return applySourceCardLayout(
        makeInfoCard(
          `${{source.label || source.survey}} resolving`,
          source.message || "Resolving SIA preview outside browser..."
        ),
        source
      );
    }}
    if (source.type === "resolved_color_image") {{
      return applySourceCardLayout(await buildResolvedColorCard(source), source);
    }}
    let resolved;
    let image;
    if (source.type === "first_available") {{
      const result = await resolveSource(source);
      if (result.resolved && result.resolved.type === "resolved_color_image") {{
        return applySourceCardLayout(await buildResolvedColorCard(result.resolved), source);
      }}
      resolved = result.resolved;
      image = result.image;
    }} else {{
      resolved = await resolveSource(source);
      image = await loadImage(resolved.url, {{crossOrigin: resolved.cross_origin !== false}});
    }}
    styleImageElement(image);
    applyResolvedImageOrientation(image, resolved);
    const card = makeCard(resolved.title);
    card.appendChild(wrapWithCrosshair(image));
    return applySourceCardLayout(card, source);
  }}

  async function loadSupplements() {{
    const panel = ensurePanel();
    if (!panel || state.pending || state.done) {{
      return;
    }}
    state.pending = true;
    showMessage(panel, "Loading supplemental survey cutouts...");
    try {{
      const cardPromises = [];
      for (const source of payload.unwise_row || []) {{
        cardPromises.push(
          buildSurveyCard(source).catch(function (error) {{
            return applySourceCardLayout(makeErrorCard(`${{source.label || source.survey}} unavailable`, error), source);
          }})
        );
      }}
      cardPromises.push(
        buildIrgCard().catch(function (error) {{
          return makeErrorCard("DES DR2 IRG unavailable", error);
        }}),
        buildYziCard().catch(function (error) {{
          return makeErrorCard("DES DR2 YZI unavailable", error);
        }})
      );
      for (const source of payload.ps1_row || []) {{
        cardPromises.push(
          buildSurveyCard(source).catch(function (error) {{
            return applySourceCardLayout(makeErrorCard(`${{source.label || source.survey}} unavailable`, error), source);
          }})
        );
      }}
      for (const row of payload.survey_rows || []) {{
        for (const source of row) {{
          cardPromises.push(
            buildSurveyCard(source).catch(function (error) {{
              return applySourceCardLayout(makeErrorCard(`${{source.label || source.survey}} unavailable`, error), source);
            }})
          );
        }}
      }}
      const cards = await Promise.all(cardPromises);
      panel.replaceChildren();
      for (const card of cards) {{
        panel.appendChild(card);
      }}
      state.done = true;
      window.setTimeout(function () {{
        window.dispatchEvent(new Event("resize"));
      }}, 0);
    }} catch (error) {{
      state.lastError = error && error.message ? error.message : String(error);
      state.done = false;
      showMessage(panel, `Supplemental cutouts unavailable: ${{state.lastError}}`);
    }} finally {{
      state.pending = false;
    }}
  }}

  loadSupplements();
}})({payload_json});
"""


WISEVIEW_DEFAULT_PARAMS = (
    ("size", "75"),
    ("band", "3"),
    ("speed", "500"),
    ("minbright", "-50.0000"),
    ("maxbright", "500.0000"),
    ("window", "5.0"),
    ("diff_window", "1"),
    ("linear", "1"),
    ("color", ""),
    ("zoom", "14.0"),
    ("border", "0"),
    ("gaia", "1"),
    ("invert", "1"),
    ("maxdyr", "1"),
    ("scandir", "0"),
    ("neowise", "0"),
    ("diff", "0"),
    ("outer_epochs", "1"),
    ("unique_window", "1"),
    ("smooth_scan", "0"),
    ("shift", "0"),
    ("pmra", "0"),
    ("pmdec", "0"),
    ("synth_a", "0"),
    ("synth_a_sub", "0"),
    ("synth_a_ra", ""),
    ("synth_a_dec", ""),
    ("synth_a_w1", ""),
    ("synth_a_w2", ""),
    ("synth_a_pmra", "0"),
    ("synth_a_pmdec", "0"),
    ("synth_a_mjd", ""),
    ("synth_b", "0"),
    ("synth_b_sub", "0"),
    ("synth_b_ra", ""),
    ("synth_b_dec", ""),
    ("synth_b_w1", ""),
    ("synth_b_w2", ""),
    ("synth_b_pmra", "0"),
    ("synth_b_pmdec", "0"),
    ("synth_b_mjd", ""),
)


_AUTOTYPE_REVIEW_MODULE = None


def _autotype_review():
    from . import autotype_helpers
    return autotype_helpers


@dataclass(frozen=True)
class ClassificationSpec:
    key: str
    classification: str
    classification_integer: Decimal


CLASSIFICATION_SPECS = (
    ClassificationSpec("6", "clear motion, red detection", Decimal("6")),
    ClassificationSpec("5", "clear motion, black detection", Decimal("5")),
    ClassificationSpec("4", "potential motion, red detection", Decimal("4")),
    ClassificationSpec("3", "potential motion, black detection", Decimal("3")),
    ClassificationSpec("2", "still, red detection", Decimal("2")),
    ClassificationSpec("1", "still, black detection", Decimal("1")),
    ClassificationSpec("n", "no detection", Decimal("0.5")),
    ClassificationSpec("0", "cannot determine", Decimal("0")),
    ClassificationSpec("b", "bad", Decimal("-1")),
    ClassificationSpec("g", "bad/galaxy", Decimal("-1")),
    ClassificationSpec("i", "bad/giant", Decimal("-1")),
    ClassificationSpec("h", "bad/halo", Decimal("-1")),
    ClassificationSpec("d", "bad/should be detected", Decimal("-1")),
    ClassificationSpec("c", "unclear detection, significant source confusion", Decimal("-1")),
    ClassificationSpec("m", "mis-centered SPHEREx but red", Decimal("-1")),
)


@dataclass
class ReviewObject:
    moca_oid: int
    ra_deg: float
    dec_deg: float
    designation: str
    adopted_spectral_type: str = ""
    adopted_spectral_type_reference: str = ""
    adopted_spectral_type_photometric_estimate: bool = False
    adopted_spectral_type_calculation_method: str = ""
    adopted_spectral_type_moca_specpackid: Optional[int] = None
    public_adopted_spectral_type: str = ""
    public_adopted_spectral_type_reference: str = ""
    public_adopted_spectral_type_photometric_estimate: bool = False
    object_origin: str = ""
    disc_reference: str = ""
    in_byw: bool = False
    mocadb_m8plus_100arcsec_count: Optional[int] = None
    mocadb_l0plus_100arcsec_count: Optional[int] = None
    nearby_nonsublime_100arcsec_count: Optional[int] = None
    nearby_sublime_100arcsec_count: Optional[int] = None
    wise_w1mag: Optional[float] = None
    wise_w1mag_synthetic: bool = False
    wise_w2mag: Optional[float] = None
    wise_w2mag_synthetic: bool = False
    wise_w1_w2: Optional[float] = None
    sublime_visual_nn_classification: str = ""
    sublime_visual_nn_good_probability: Optional[float] = None
    sublime_detection_snr: Optional[float] = None
    sublime_autotype_spectral_type: str = ""
    moca_spectra_median_snr_per_pix: Optional[float] = None
    classification: Optional[str] = None
    classification_integer: Optional[Decimal] = None
    comments: str = ""
    vetting_row_exists: bool = False
    reviewer: str = ""
    vetting_source_table: str = ""
    vetting_origin: str = ORIGIN
    modified_timestamp: Optional[str] = None


@dataclass(frozen=True)
class NearbyCountDiagnostics:
    m8plus: int = 0
    l0plus: int = 0
    nonsublime: int = 0
    sublime: int = 0


@dataclass(frozen=True)
class NearbyBdFilterSpec:
    attr: str
    option: str
    adoption_column: str
    photometric_estimate: bool
    description: str


NEARBY_BD_FILTER_SPECS = (
    NearbyBdFilterSpec(
        attr="nearpublicphotobd",
        option="--nearpublicphotobd",
        adoption_column="public_adopted",
        photometric_estimate=True,
        description="public-adopted photometric-estimate",
    ),
    NearbyBdFilterSpec(
        attr="nearpublicbd",
        option="--nearpublicbd",
        adoption_column="public_adopted",
        photometric_estimate=False,
        description="public-adopted non-photometric",
    ),
    NearbyBdFilterSpec(
        attr="nearphotobd",
        option="--nearphotobd",
        adoption_column="adopted",
        photometric_estimate=True,
        description="private adopted photometric-estimate",
    ),
    NearbyBdFilterSpec(
        attr="nearbd",
        option="--nearbd",
        adoption_column="adopted",
        photometric_estimate=False,
        description="private adopted non-photometric",
    ),
)


def _mocadb_ssl_options(host):
    if str(host or "").strip().lower() in {"localhost", "127.0.0.1", "::1"}:
        return None
    return {"verify_mode": False, "check_hostname": False}


def _validate_table_name(table: str) -> str:
    table_name = str(table).strip()
    if not TABLE_NAME_RE.fullmatch(table_name):
        raise ValueError(f"Unsafe table name: {table!r}")
    return table_name


def _connect_db(*, autocommit: bool = False) -> pymysql.connections.Connection:
    cfg = _autotype_review()._load_base_db_config()
    return pymysql.connect(
        host=str(cfg["host"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        database=str(cfg["database"]),
        port=int(cfg["port"]),
        ssl=_mocadb_ssl_options(cfg["host"]),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=autocommit,
        connect_timeout=15,
        read_timeout=300,
        write_timeout=300,
    )


def add_nearby_bd_filter_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument(
        "--nearpublicphotobd",
        type=float,
        default=None,
        metavar="ARCSEC",
        help=(
            "Require a public-adopted photometric-estimate L0+ MOCAdb object "
            "within ARCSEC of the SUBLIME source position."
        ),
    )
    ap.add_argument(
        "--nearpublicbd",
        type=float,
        default=None,
        metavar="ARCSEC",
        help=(
            "Require a public-adopted non-photometric L0+ MOCAdb object "
            "within ARCSEC of the SUBLIME source position."
        ),
    )
    ap.add_argument(
        "--nearphotobd",
        type=float,
        default=None,
        metavar="ARCSEC",
        help=(
            "Require a private adopted photometric-estimate L0+ MOCAdb object "
            "within ARCSEC of the SUBLIME source position."
        ),
    )
    ap.add_argument(
        "--nearbd",
        type=float,
        default=None,
        metavar="ARCSEC",
        help=(
            "Require a private adopted non-photometric L0+ MOCAdb object "
            "within ARCSEC of the SUBLIME source position."
        ),
    )


def iter_nearby_bd_filter_args(
    args: argparse.Namespace,
) -> Iterable[tuple[NearbyBdFilterSpec, float]]:
    for spec in NEARBY_BD_FILTER_SPECS:
        value = getattr(args, spec.attr, None)
        if value is None:
            continue
        yield spec, float(value)


def validate_nearby_bd_filter_args(args: argparse.Namespace) -> None:
    for spec, radius_arcsec in iter_nearby_bd_filter_args(args):
        if radius_arcsec <= 0:
            raise ValueError(f"{spec.option} must be positive")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Vet MOCAdb objects in WiseView and upsert classifications.")
    ap.add_argument("--table", default=WISEVIEW_VETTING_TABLE, help=f"Target vetting table, default {WISEVIEW_VETTING_TABLE}.")
    ap.add_argument("--source-table", default=DEFAULT_SOURCE_TABLE, help=f"Source table for the default queue, default {DEFAULT_SOURCE_TABLE}.")
    ap.add_argument("--moca-oids", default=None, help="Optional comma/space-separated moca_oid list. Overrides --source-table as the base queue.")
    ap.add_argument("--limit", type=int, default=None, help="Limit the number of queued objects after filtering.")
    ap.add_argument("--start-oid", type=int, default=None, help="Start the GUI at this moca_oid if it is present.")
    ap.add_argument("--reclass", action="store_true", help="Include objects already present in the WiseView vetting table.")
    ap.add_argument("--reviewer", default=os.getenv("USER", ""), help="Reviewer name stored with each upsert.")
    ap.add_argument("--dry-run", action="store_true", help="Print the final queue summary without opening the GUI.")
    ap.add_argument("--stacker", action="store_true", help="Use SPIFFstacker lane defaults for queue/autotype filters.")
    ap.add_argument("--sublimeaperture", action="store_true", help="Use SUBLIME aperture lane defaults for queue/autotype filters.")
    ap.add_argument("--autotype-root", type=pathlib.Path, action="append", default=None, help="Autotype PNG root for [a]; can be repeated. Defaults to the TData2 plot archive.")
    ap.add_argument("--local", action="store_true", help="Use repository-local autotype roots instead of the external archive. Off by default.")
    ap.add_argument("--queue", action="store_true", help="Restrict to the autotype queue table for the selected lane.")
    ap.add_argument("--souleymane", action="store_true", help="Restrict to pcat_souleymane_candidates_may20_2026_v1.")
    ap.add_argument("--noclaim", action="store_true", help="Exclude OIDs in pcat_kirkpatrick_yadu_2026_claim and matching BYW claims.")
    ap.add_argument("--claimed-only", action="store_true", help="Review only BYW or Kirkpatrick/Yadu claimed objects.")
    ap.add_argument("--nogaia", action="store_true", help="Exclude OIDs with an entry in cat_gaiadr3 or cat_gaiadr2.")
    ap.add_argument("--gaia-only", action="store_true", help="Include only objects in Gaia DR2 or DR3.")
    ap.add_argument("--no-known", "--noknown", dest="no_known", action="store_true", help="Exclude public-adopted non-photometric known M0+ OIDs.")
    ap.add_argument("--known", action="store_true", help="Require public-adopted non-photometric known M0+ OIDs.")
    ap.add_argument("--nophotoknown", action="store_true", help="Exclude public-adopted photometric-estimate known M0+ OIDs.")
    ap.add_argument("--photoknown", action="store_true", help="Require public-adopted photometric-estimate known M0+ OIDs.")
    add_nearby_bd_filter_arguments(ap)
    ap.add_argument("--skip-missing-w2", action="store_true", help="Exclude objects without an adopted wise_w2mag in data_photometry.")
    ap.add_argument("--min-w2", type=float, default=None, help="Minimum adopted W2 magnitude, inclusive.")
    ap.add_argument("--max-w2", type=float, default=None, help="Maximum adopted W2 magnitude, inclusive.")
    ap.add_argument("--spiffviz", default=None, metavar="CLASS[,CLASS...]", help="Require visual-vetting classes; supports 'none'.")
    ap.add_argument("--notspiffviz", default=None, metavar="CLASS[,CLASS...]", help="Exclude visual-vetting classes; supports 'none'.")
    ap.add_argument("--spiffstackerviz", "--spifftsackerviz", dest="spiffstackerviz", default=None, metavar="CLASS[,CLASS...]", help="Require SPIFFstacker visual-vetting classes; supports 'none'.")
    ap.add_argument("--notspiffstackerviz", default=None, metavar="CLASS[,CLASS...]", help="Exclude SPIFFstacker visual-vetting classes; supports 'none'.")
    ap.add_argument("--sublimeapertureviz", default=None, metavar="CLASS[,CLASS...]", help="Require SUBLIME aperture visual-vetting classes; supports 'none'.")
    ap.add_argument("--notsublimeapertureviz", default=None, metavar="CLASS[,CLASS...]", help="Exclude SUBLIME aperture visual-vetting classes; supports 'none'.")
    ap.add_argument("--sublime2cnn", default=None, metavar="CLASS[,CLASS...]", help="Require pcat_sublime_candidates_v2.visual_nn_classification class list.")
    ap.add_argument("--sublime2snr", type=float, default=None, help="Require pcat_sublime_candidates_v2.detection_snr >= value.")
    ap.add_argument("--sublime2cnnprob", type=float, default=None, help="Require pcat_sublime_candidates_v2.visual_nn_good_probability >= value.")
    ap.add_argument("--sublime2sptn", type=float, default=None, help="Require pcat_sublime_candidates_v2.autotype_spectral_type_number >= value.")
    ap.add_argument("--median-snr", type=float, default=None, help="Require latest lane spectrum median_snr_per_pix >= value.")
    ap.add_argument("--max-median-snr", type=float, default=None, help="Require latest lane spectrum median_snr_per_pix <= value.")
    ap.add_argument("--chi2", "--max-chi2", dest="chi2_max", type=float, default=None, help="Require stored autotype chi2 <= value.")
    ap.add_argument("--min-chi2", dest="chi2_min", type=float, default=None, help="Require stored autotype chi2 >= value.")
    ap.add_argument("--min-abs-gb", "--min-abs-galactic-latitude", dest="min_abs_galactic_latitude", type=float, default=None, help="Require abs(galactic latitude) >= value.")
    ap.add_argument("--spectral-type-number-min", type=float, default=None, help="Require pcat_sublime_candidates_v2.autotype_spectral_type_number >= value.")
    ap.add_argument("--spectral-type-number-max", type=float, default=None, help="Require pcat_sublime_candidates_v2.autotype_spectral_type_number <= value.")
    return ap.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    _validate_table_name(args.table)
    _validate_table_name(args.source_table)
    if getattr(args, "nogaia", False) and getattr(args, "gaia_only", False):
        raise ValueError("--nogaia cannot be combined with --gaia-only")
    if getattr(args, "noclaim", False) and getattr(args, "claimed_only", False):
        raise ValueError("--noclaim cannot be combined with --claimed-only")
    if args.stacker and args.sublimeaperture:
        raise ValueError("--stacker cannot be combined with --sublimeaperture")
    if args.known and args.no_known:
        raise ValueError("--known cannot be combined with --no-known/--noknown")
    if args.photoknown and args.nophotoknown:
        raise ValueError("--photoknown cannot be combined with --nophotoknown")
    validate_nearby_bd_filter_args(args)
    for value in (getattr(args, "min_w2", None), getattr(args, "max_w2", None)):
        if value is not None and not math.isfinite(value):
            raise ValueError("W2 magnitude bounds must be finite")
    if getattr(args, "min_w2", None) is not None and getattr(args, "max_w2", None) is not None and args.min_w2 > args.max_w2:
        raise ValueError("--min-w2 cannot be greater than --max-w2")
    if args.limit is not None and int(args.limit) <= 0:
        raise ValueError("--limit must be positive")
    if args.median_snr is not None and args.median_snr < 0:
        raise ValueError("--median-snr must be non-negative")
    if args.max_median_snr is not None and args.max_median_snr < 0:
        raise ValueError("--max-median-snr must be non-negative")
    if args.median_snr is not None and args.max_median_snr is not None and args.median_snr > args.max_median_snr:
        raise ValueError("--median-snr cannot be greater than --max-median-snr")
    if args.chi2_min is not None and args.chi2_min < 0:
        raise ValueError("--min-chi2 must be non-negative")
    if args.chi2_max is not None and args.chi2_max < 0:
        raise ValueError("--chi2/--max-chi2 must be non-negative")
    if args.chi2_min is not None and args.chi2_max is not None and args.chi2_min > args.chi2_max:
        raise ValueError("--min-chi2 cannot be greater than --chi2/--max-chi2")
    if args.min_abs_galactic_latitude is not None and not (0 <= args.min_abs_galactic_latitude <= 90):
        raise ValueError("--min-abs-gb must be between 0 and 90")
    if (
        args.spectral_type_number_min is not None
        and args.spectral_type_number_max is not None
        and args.spectral_type_number_min > args.spectral_type_number_max
    ):
        raise ValueError("--spectral-type-number-min cannot be greater than --spectral-type-number-max")


def _format_wiseview_float(value: float) -> str:
    return f"{float(value):.10f}".rstrip("0").rstrip(".")


def build_wiseview_url(*, ra_deg: float, dec_deg: float) -> str:
    params = [
        ("ra", _format_wiseview_float(ra_deg)),
        ("dec", _format_wiseview_float(dec_deg)),
        *WISEVIEW_DEFAULT_PARAMS,
    ]
    return f"{WISEVIEW_BASE_URL}#{urlencode(params)}"


def _format_filter_number(value: float) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:g}"


def _spectral_type_number_to_text(value: float) -> str:
    numeric = float(value)
    if numeric < 0:
        prefix = "K"
        subtype = numeric + 10
    elif numeric < 10:
        prefix = "M"
        subtype = numeric
    elif numeric < 20:
        prefix = "L"
        subtype = numeric - 10
    elif numeric < 30:
        prefix = "T"
        subtype = numeric - 20
    else:
        prefix = "Y"
        subtype = numeric - 30
    return f"{prefix}{_format_filter_number(subtype)}"


def fetch_source_oids(source_table: str) -> set[int]:
    table = _validate_table_name(source_table)
    conn = _connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT moca_oid
                FROM `{table}`
                WHERE moca_oid IS NOT NULL
                """,
                (),
            )
            return {int(row["moca_oid"]) for row in cur.fetchall() if row.get("moca_oid") is not None}
    finally:
        conn.close()


def fetch_existing_vetting_oids(table: str) -> set[int]:
    table_name = _validate_table_name(table)
    conn = _connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT moca_oid
                FROM `{table_name}`
                WHERE moca_oid IS NOT NULL
                """,
                (),
            )
            return {int(row["moca_oid"]) for row in cur.fetchall() if row.get("moca_oid") is not None}
    finally:
        conn.close()


def _chunked(values: Sequence[int], chunk_size: int = 1000) -> Iterable[Sequence[int]]:
    for start in range(0, len(values), chunk_size):
        yield values[start:start + chunk_size]


def fetch_missing_visual_vetting_oids(oids: set[int], *, visual_vetting_tables: Iterable[str]) -> set[int]:
    if not oids:
        return set()
    table_names = tuple(_validate_table_name(table) for table in visual_vetting_tables)
    if not table_names:
        return set(oids)
    seen_oids: set[int] = set()
    all_oids = sorted(oids)
    conn = _connect_db()
    try:
        with conn.cursor() as cur:
            for table in table_names:
                for chunk in _chunked(all_oids):
                    placeholders = ", ".join(["%s"] * len(chunk))
                    cur.execute(
                        f"""
                        SELECT DISTINCT moca_oid
                        FROM `{table}`
                        WHERE moca_oid IN ({placeholders})
                        """,
                        tuple(chunk),
                    )
                    seen_oids.update(
                        int(row["moca_oid"])
                        for row in cur.fetchall()
                        if row.get("moca_oid") is not None
                    )
    finally:
        conn.close()
    return set(oids) - seen_oids


def apply_visual_vetting_filter(
    oids: set[int],
    classes: Iterable[str],
    *,
    exclude: bool,
    option_name: str,
    visual_vetting_tables: Iterable[str],
) -> set[int]:
    class_values, include_missing = _autotype_review()._split_missing_spiffviz_token(classes)
    matched_oids: set[int] = set()
    if class_values:
        matched_oids = _autotype_review().fetch_spiffviz_oids(
            class_values,
            option_name=option_name,
            visual_vetting_tables=visual_vetting_tables,
        )
    if include_missing:
        matched_oids |= fetch_missing_visual_vetting_oids(oids, visual_vetting_tables=visual_vetting_tables)
    return (oids - matched_oids) if exclude else (oids & matched_oids)


def filter_oids_by_min_abs_galactic_latitude(oids: set[int], min_abs_galactic_latitude: Optional[float]) -> set[int]:
    if min_abs_galactic_latitude is None or not oids:
        return set(oids)
    keep_oids: set[int] = set()
    all_oids = sorted(oids)
    conn = _connect_db()
    try:
        with conn.cursor() as cur:
            for chunk in _chunked(all_oids):
                placeholders = ", ".join(["%s"] * len(chunk))
                cur.execute(
                    "SELECT DISTINCT moca_oid "
                    "FROM calc_galactic_coordinates "
                    f"WHERE moca_oid IN ({placeholders}) "
                    "AND gb IS NOT NULL "
                    "AND ABS(gb) >= %s",
                    tuple([*chunk, float(min_abs_galactic_latitude)]),
                )
                keep_oids.update(
                    int(row["moca_oid"])
                    for row in cur.fetchall()
                    if row.get("moca_oid") is not None
                )
    finally:
        conn.close()
    return oids & keep_oids


def filter_oids_by_valid_w2mag(oids: set[int], *, min_w2: Optional[float] = None, max_w2: Optional[float] = None) -> set[int]:
    if not oids:
        return set()
    keep_oids: set[int] = set()
    all_oids = sorted(oids)
    conn = _connect_db()
    try:
        with conn.cursor() as cur:
            for chunk in _chunked(all_oids):
                placeholders = ", ".join(["%s"] * len(chunk))
                sql = ("SELECT DISTINCT moca_oid FROM data_photometry "
                       f"WHERE moca_oid IN ({placeholders}) AND adopted = 1 "
                       "AND moca_psid = 'wise_w2mag' AND magnitude IS NOT NULL")
                params: list[object] = list(chunk)
                if min_w2 is not None:
                    sql += " AND magnitude >= %s"
                    params.append(float(min_w2))
                if max_w2 is not None:
                    sql += " AND magnitude <= %s"
                    params.append(float(max_w2))
                cur.execute(sql, tuple(params))
                keep_oids.update(
                    int(row["moca_oid"])
                    for row in cur.fetchall()
                    if row.get("moca_oid") is not None
                )
    finally:
        conn.close()
    return oids & keep_oids


def filter_oids_by_sublime_autotype_sptn(
    oids: set[int],
    *,
    spt_min: Optional[float],
    spt_max: Optional[float],
) -> set[int]:
    if (spt_min is None and spt_max is None) or not oids:
        return set(oids)
    keep_oids: set[int] = set()
    all_oids = sorted(oids)
    conn = _connect_db()
    try:
        with conn.cursor() as cur:
            for chunk in _chunked(all_oids):
                placeholders = ", ".join(["%s"] * len(chunk))
                where_parts = [
                    f"psc.moca_oid IN ({placeholders})",
                    "psc.autotype_spectral_type_number IS NOT NULL",
                ]
                params: list[object] = list(chunk)
                if spt_min is not None:
                    where_parts.append("psc.autotype_spectral_type_number >= %s")
                    params.append(float(spt_min))
                if spt_max is not None:
                    where_parts.append("psc.autotype_spectral_type_number <= %s")
                    params.append(float(spt_max))
                cur.execute(
                    """
                    SELECT DISTINCT psc.moca_oid
                    FROM pcat_sublime_candidates_v2 psc
                    JOIN (
                        SELECT moca_oid, MAX(id) AS id
                        FROM pcat_sublime_candidates_v2
                        WHERE moca_oid IS NOT NULL
                        GROUP BY moca_oid
                    ) latest_sublime
                        ON latest_sublime.id = psc.id
                    WHERE """
                    + " AND ".join(where_parts),
                    tuple(params),
                )
                keep_oids.update(
                    int(row["moca_oid"])
                    for row in cur.fetchall()
                    if row.get("moca_oid") is not None
                )
    finally:
        conn.close()
    return oids & keep_oids


def _coord_query_rectangles(
    ra_deg: float,
    dec_deg: float,
    radius_arcsec: float,
) -> list[tuple[float, float, float, float]]:
    radius_deg = float(radius_arcsec) / 3600.0
    ra = float(ra_deg) % 360.0
    dec = float(dec_deg)
    dx = radius_deg / max(math.cos(math.radians(dec)), 0.01)
    dy = radius_deg
    ra_min = ra - dx
    ra_max = ra + dx
    dec_min = dec - dy
    dec_max = dec + dy
    if ra_min >= 0.0 and ra_max <= 360.0:
        return [(ra_min, ra_max, dec_min, dec_max)]
    if ra_min < 0.0:
        return [
            (0.0, ra_max, dec_min, dec_max),
            (360.0 + ra_min, 360.0, dec_min, dec_max),
        ]
    return [
        (ra_min, 360.0, dec_min, dec_max),
        (0.0, ra_max - 360.0, dec_min, dec_max),
    ]


def _format_wkt_float(value: float) -> str:
    return f"{float(value):.12g}"


def _spatial_rectangle_wkt(ra_min: float, ra_max: float, dec_min: float, dec_max: float) -> str:
    points = (
        (ra_min, dec_min),
        (ra_max, dec_min),
        (ra_max, dec_max),
        (ra_min, dec_max),
        (ra_min, dec_min),
    )
    return "POLYGON((" + ",".join(f"{_format_wkt_float(ra)} {_format_wkt_float(dec)}" for ra, dec in points) + "))"


def _fetch_sublime_source_coordinate_rows(
    *,
    source_oids: Optional[set[int]] = None,
) -> list[dict[str, object]]:
    if source_oids is not None and not source_oids:
        return []
    rows: list[dict[str, object]] = []
    conn = _connect_db()
    try:
        with conn.cursor() as cur:
            if source_oids is None:
                cur.execute(
                    f"""
                    SELECT psc.moca_oid, psc.ra_deg, psc.dec_deg
                    FROM `{DEFAULT_SOURCE_TABLE}` psc
                    WHERE psc.moca_oid IS NOT NULL
                        AND psc.ra_deg IS NOT NULL
                        AND psc.dec_deg IS NOT NULL
                    ORDER BY psc.moca_oid, psc.id
                    """,
                    (),
                )
                rows.extend(cur.fetchall())
            else:
                for chunk in _chunked(sorted(source_oids)):
                    placeholders = ", ".join(["%s"] * len(chunk))
                    cur.execute(
                        f"""
                        SELECT psc.moca_oid, psc.ra_deg, psc.dec_deg
                        FROM `{DEFAULT_SOURCE_TABLE}` psc
                        WHERE psc.moca_oid IS NOT NULL
                            AND psc.ra_deg IS NOT NULL
                            AND psc.dec_deg IS NOT NULL
                            AND psc.moca_oid IN ({placeholders})
                        ORDER BY psc.moca_oid, psc.id
                        """,
                        tuple(chunk),
                    )
                    rows.extend(cur.fetchall())
    finally:
        conn.close()
    return rows


def fetch_sublime_oids_near_bd(
    *,
    radius_arcsec: float,
    photometric_estimate: bool,
    public_adopted: bool,
    source_oids: Optional[set[int]] = None,
) -> set[int]:
    radius = float(radius_arcsec)
    if radius <= 0:
        raise ValueError("radius_arcsec must be positive")
    source_rows = _fetch_sublime_source_coordinate_rows(source_oids=source_oids)
    if not source_rows:
        return set()

    adoption_column = "public_adopted" if public_adopted else "adopted"
    photometric_flag = 1 if photometric_estimate else 0
    matched_oids: set[int] = set()
    conn = _connect_db()
    try:
        with conn.cursor() as cur:
            for row in source_rows:
                source_oid = row.get("moca_oid")
                ra_deg = row.get("ra_deg")
                dec_deg = row.get("dec_deg")
                if source_oid is None or ra_deg is None or dec_deg is None:
                    continue
                select_blocks: list[str] = []
                params: list[object] = []
                for rectangle in _coord_query_rectangles(float(ra_deg), float(dec_deg), radius):
                    select_blocks.append(
                        f"""
                        SELECT mo.moca_oid
                        FROM moca_objects mo
                        JOIN data_spectral_types spt
                            ON spt.moca_oid = mo.moca_oid
                            AND spt.{adoption_column} = 1
                            AND spt.photometric_estimate = %s
                            AND spt.spectral_type_number >= {NEARBY_BD_FILTER_MIN_SPECTRAL_TYPE_NUMBER}
                        WHERE mo.ignored = 0
                            AND mo.ra IS NOT NULL
                            AND mo.`dec` IS NOT NULL
                            AND mo.spatial_coord IS NOT NULL
                            AND MBRIntersects(mo.spatial_coord, ST_GeomFromText(%s, 4326))
                            AND angular_distance(%s, %s, mo.ra, mo.`dec`) < %s
                        """
                    )
                    params.extend(
                        (
                            photometric_flag,
                            _spatial_rectangle_wkt(*rectangle),
                            float(ra_deg) % 360.0,
                            float(dec_deg),
                            radius,
                        )
                    )
                cur.execute(
                    f"""
                    SELECT nearby.moca_oid
                    FROM (
                        {" UNION ALL ".join(select_blocks)}
                    ) nearby
                    LIMIT 1
                    """,
                    tuple(params),
                )
                if cur.fetchall():
                    matched_oids.add(int(source_oid))
    finally:
        conn.close()
    return matched_oids


def fetch_sublime_oids_for_nearby_bd_filter(
    spec: NearbyBdFilterSpec,
    *,
    radius_arcsec: float,
    source_oids: Optional[set[int]] = None,
) -> set[int]:
    return fetch_sublime_oids_near_bd(
        radius_arcsec=radius_arcsec,
        photometric_estimate=spec.photometric_estimate,
        public_adopted=spec.adoption_column == "public_adopted",
        source_oids=source_oids,
    )


def fetch_mocadb_nearby_100arcsec_diagnostics(
    target_coords: dict[int, tuple[float, float]],
) -> dict[int, NearbyCountDiagnostics]:
    if not target_coords:
        return {}
    radius_arcsec = 100.0
    conn = _connect_db()
    try:
        counts: dict[int, NearbyCountDiagnostics] = {}
        with conn.cursor() as cur:
            for target_oid, (ra_deg, dec_deg) in target_coords.items():
                select_blocks: list[str] = []
                params: list[object] = []
                for rectangle in _coord_query_rectangles(ra_deg, dec_deg, radius_arcsec):
                    select_blocks.append(
                        """
                        SELECT
                            mo.moca_oid,
                            CASE
                                WHEN spt.moca_oid IS NOT NULL THEN mo.moca_oid
                                ELSE NULL
                            END AS m8plus_moca_oid,
                            CASE WHEN spt.spectral_type_number >= 10 THEN mo.moca_oid ELSE NULL END AS l0plus_moca_oid,
                            CASE
                                WHEN mo.designation IS NULL OR mo.designation NOT LIKE 'SUBLIME%%'
                                THEN mo.moca_oid
                                ELSE NULL
                            END AS nonsublime_moca_oid,
                            CASE
                                WHEN mo.designation LIKE 'SUBLIME%%'
                                THEN mo.moca_oid
                                ELSE NULL
                            END AS sublime_moca_oid
                        FROM moca_objects mo
                        LEFT JOIN data_spectral_types spt
                            ON spt.moca_oid = mo.moca_oid
                            AND spt.adopted = 1
                            AND spt.spectral_type_number IS NOT NULL
                            AND spt.spectral_type_number >= 8
                        WHERE mo.ignored = 0
                            AND mo.moca_oid <> %s
                            AND mo.ra IS NOT NULL
                            AND mo.`dec` IS NOT NULL
                            AND mo.spatial_coord IS NOT NULL
                            AND MBRIntersects(mo.spatial_coord, ST_GeomFromText(%s, 4326))
                            AND angular_distance(%s, %s, mo.ra, mo.`dec`) < %s
                        """
                    )
                    params.extend(
                        (
                            int(target_oid),
                            _spatial_rectangle_wkt(*rectangle),
                            float(ra_deg) % 360.0,
                            float(dec_deg),
                            radius_arcsec,
                        )
                    )
                cur.execute(
                    f"""
                    SELECT
                        COUNT(DISTINCT nearby.m8plus_moca_oid) AS nearby_m8plus_count,
                        COUNT(DISTINCT nearby.l0plus_moca_oid) AS nearby_l0plus_count,
                        COUNT(DISTINCT nearby.nonsublime_moca_oid) AS nearby_nonsublime_count,
                        COUNT(DISTINCT nearby.sublime_moca_oid) AS nearby_sublime_count
                    FROM (
                        {" UNION ALL ".join(select_blocks)}
                    ) nearby
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
                row = rows[0] if rows else {}
                counts[int(target_oid)] = NearbyCountDiagnostics(
                    m8plus=int(row.get("nearby_m8plus_count") or 0),
                    l0plus=int(row.get("nearby_l0plus_count") or 0),
                    nonsublime=int(row.get("nearby_nonsublime_count") or 0),
                    sublime=int(row.get("nearby_sublime_count") or 0),
                )
    finally:
        conn.close()
    return counts


def fetch_review_objects(oids: Iterable[int], *, table: str) -> list[ReviewObject]:
    table_name = _validate_table_name(table)
    ordered_oids = [int(oid) for oid in oids]
    if not ordered_oids:
        return []
    rows_by_oid: dict[int, dict[str, object]] = {}
    conn = _connect_db()
    try:
        with conn.cursor() as cur:
            for chunk in _chunked(ordered_oids):
                placeholders = ", ".join(["%s"] * len(chunk))
                cur.execute(
                    f"""
                    SELECT
                        mo.moca_oid,
                        mo.designation AS designation,
                        mo.origin AS object_origin,
                        EXISTS (
                            SELECT 1
                            FROM pcat_byw_mar9_2026 byw_exists
                            WHERE byw_exists.moca_oid = mo.moca_oid
                            LIMIT 1
                        ) AS in_byw,
                        CASE
                            WHEN mo.origin LIKE '%%backyard_worlds%%'
                            THEN (
                                SELECT GROUP_CONCAT(
                                    DISTINCT NULLIF(byw9.disc, '')
                                    ORDER BY byw9.disc SEPARATOR ', '
                                )
                                FROM pcat_byw_mar9_2026 byw9
                                WHERE byw9.moca_oid = mo.moca_oid
                            )
                            ELSE NULL
                        END AS disc_reference,
                        COALESCE(
                            NULLIF(spt.spectral_type, ''),
                            NULLIF(spt.complete_spectral_type, '')
                        ) AS adopted_spectral_type,
                        COALESCE(
                            NULLIF(spt.moca_pid, ''),
                            NULLIF(spt.origin, ''),
                            NULLIF(spt.calculation_method, '')
                        ) AS adopted_spectral_type_reference,
                        spt.photometric_estimate AS adopted_spectral_type_photometric_estimate,
                        spt.calculation_method AS adopted_spectral_type_calculation_method,
                        spt_ms.moca_specpackid AS adopted_spectral_type_moca_specpackid,
                        sublime.visual_nn_classification AS sublime_visual_nn_classification,
                        sublime.visual_nn_good_probability AS sublime_visual_nn_good_probability,
                        sublime.detection_snr AS sublime_detection_snr,
                        sublime.autotype_spectral_type AS sublime_autotype_spectral_type,
                        snr_ms.median_snr_per_pix AS moca_spectra_median_snr_per_pix,
                        COALESCE(
                            NULLIF(spt_pub.spectral_type, ''),
                            NULLIF(spt_pub.complete_spectral_type, '')
                        ) AS public_adopted_spectral_type,
                        COALESCE(
                            NULLIF(spt_pub.moca_pid, ''),
                            NULLIF(spt_pub.origin, ''),
                            NULLIF(spt_pub.calculation_method, '')
                        ) AS public_adopted_spectral_type_reference,
                        spt_pub.photometric_estimate AS public_adopted_spectral_type_photometric_estimate,
                        w1.magnitude AS wise_w1mag,
                        w1.is_synthetic AS wise_w1mag_synthetic,
                        w2.magnitude AS wise_w2mag,
                        w2.is_synthetic AS wise_w2mag_synthetic,
                        CASE
                            WHEN w1.magnitude IS NOT NULL AND w2.magnitude IS NOT NULL
                            THEN w1.magnitude - w2.magnitude
                            ELSE NULL
                        END AS wise_w1_w2,
                        de.ra,
                        de.`dec`,
                        vet.moca_oid AS vetting_moca_oid,
                        vet.classification,
                        vet.classification_integer,
                        vet.comments,
                        vet.reviewer,
                        vet.source_table AS vetting_source_table,
                        vet.origin AS vetting_origin,
                        vet.modified_timestamp
                    FROM moca_objects mo
                    LEFT JOIN data_equatorial_coordinates de
                        ON de.moca_oid = mo.moca_oid
                        AND de.adopt_as_reference = 1
                    LEFT JOIN data_spectral_types spt
                        ON spt.moca_oid = mo.moca_oid
                        AND spt.adopted = 1
                    LEFT JOIN moca_spectra spt_ms
                        ON spt_ms.moca_specid = spt.moca_specid
                    LEFT JOIN (
                        SELECT psc.*
                        FROM pcat_sublime_candidates_v2 psc
                        JOIN (
                            SELECT moca_oid, MAX(id) AS id
                            FROM pcat_sublime_candidates_v2
                            WHERE moca_oid IS NOT NULL
                            GROUP BY moca_oid
                        ) latest_sublime
                            ON latest_sublime.id = psc.id
                    ) sublime
                        ON sublime.moca_oid = mo.moca_oid
                    LEFT JOIN moca_spectra snr_ms
                        ON snr_ms.moca_specid = (
                            SELECT ms2.moca_specid
                            FROM moca_spectra ms2
                            WHERE ms2.moca_oid = mo.moca_oid
                                AND ms2.ignored = 0
                                AND ms2.moca_specpackid IN (54, 55, 62, 63, 76)
                                AND ms2.median_snr_per_pix IS NOT NULL
                            ORDER BY FIELD(ms2.moca_specpackid, 76, 63, 62, 55, 54),
                                ms2.moca_specid DESC
                            LIMIT 1
                        )
                    LEFT JOIN data_spectral_types spt_pub
                        ON spt_pub.moca_oid = mo.moca_oid
                        AND spt_pub.public_adopted = 1
                    LEFT JOIN data_photometry w1
                        ON w1.moca_oid = mo.moca_oid
                        AND w1.adopted = 1
                        AND w1.moca_psid = 'wise_w1mag'
                    LEFT JOIN data_photometry w2
                        ON w2.moca_oid = mo.moca_oid
                        AND w2.adopted = 1
                        AND w2.moca_psid = 'wise_w2mag'
                    LEFT JOIN `{table_name}` vet
                        ON vet.moca_oid = mo.moca_oid
                    WHERE mo.moca_oid IN ({placeholders})
                    """,
                    tuple(chunk),
                )
                for row in cur.fetchall():
                    if row.get("moca_oid") is not None:
                        rows_by_oid[int(row["moca_oid"])] = row
    finally:
        conn.close()

    target_coords: dict[int, tuple[float, float]] = {}
    for oid, row in rows_by_oid.items():
        if row.get("ra") is None or row.get("dec") is None:
            continue
        target_coords[int(oid)] = (float(row["ra"]), float(row["dec"]))
    try:
        nearby_diagnostics = fetch_mocadb_nearby_100arcsec_diagnostics(target_coords)
    except Exception as exc:
        print(f"[review] warning: failed to compute 100arcsec nearby diagnostics: {exc}")
        nearby_diagnostics = None

    objects: list[ReviewObject] = []
    for oid in ordered_oids:
        row = rows_by_oid.get(oid)
        if not row or row.get("ra") is None or row.get("dec") is None:
            print(f"[review] skipping moca_oid={oid}: missing adopted reference coordinates")
            continue
        classification_integer = row.get("classification_integer")
        objects.append(
            ReviewObject(
                moca_oid=oid,
                ra_deg=float(row["ra"]),
                dec_deg=float(row["dec"]),
                designation=str(row.get("designation") or ""),
                adopted_spectral_type=str(row.get("adopted_spectral_type") or ""),
                adopted_spectral_type_reference=str(row.get("adopted_spectral_type_reference") or ""),
                adopted_spectral_type_photometric_estimate=bool(
                    int(row.get("adopted_spectral_type_photometric_estimate") or 0)
                ),
                adopted_spectral_type_calculation_method=str(
                    row.get("adopted_spectral_type_calculation_method") or ""
                ),
                adopted_spectral_type_moca_specpackid=(
                    int(row["adopted_spectral_type_moca_specpackid"])
                    if row.get("adopted_spectral_type_moca_specpackid") is not None
                    else None
                ),
                public_adopted_spectral_type=str(row.get("public_adopted_spectral_type") or ""),
                public_adopted_spectral_type_reference=str(row.get("public_adopted_spectral_type_reference") or ""),
                public_adopted_spectral_type_photometric_estimate=bool(
                    int(row.get("public_adopted_spectral_type_photometric_estimate") or 0)
                ),
                object_origin=str(row.get("object_origin") or ""),
                disc_reference=str(row.get("disc_reference") or ""),
                in_byw=bool(int(row.get("in_byw") or 0)),
                mocadb_m8plus_100arcsec_count=(
                    int(nearby_diagnostics.get(oid, NearbyCountDiagnostics()).m8plus)
                    if nearby_diagnostics is not None
                    else None
                ),
                mocadb_l0plus_100arcsec_count=(
                    int(nearby_diagnostics.get(oid, NearbyCountDiagnostics()).l0plus)
                    if nearby_diagnostics is not None else None
                ),
                nearby_nonsublime_100arcsec_count=(
                    int(nearby_diagnostics.get(oid, NearbyCountDiagnostics()).nonsublime)
                    if nearby_diagnostics is not None
                    else None
                ),
                nearby_sublime_100arcsec_count=(
                    int(nearby_diagnostics.get(oid, NearbyCountDiagnostics()).sublime)
                    if nearby_diagnostics is not None
                    else None
                ),
                wise_w1mag=float(row["wise_w1mag"]) if row.get("wise_w1mag") is not None else None,
                wise_w1mag_synthetic=bool(int(row.get("wise_w1mag_synthetic") or 0)),
                wise_w2mag=float(row["wise_w2mag"]) if row.get("wise_w2mag") is not None else None,
                wise_w2mag_synthetic=bool(int(row.get("wise_w2mag_synthetic") or 0)),
                wise_w1_w2=float(row["wise_w1_w2"]) if row.get("wise_w1_w2") is not None else None,
                sublime_visual_nn_classification=str(row.get("sublime_visual_nn_classification") or ""),
                sublime_visual_nn_good_probability=(
                    float(row["sublime_visual_nn_good_probability"])
                    if row.get("sublime_visual_nn_good_probability") is not None
                    else None
                ),
                sublime_detection_snr=(
                    float(row["sublime_detection_snr"])
                    if row.get("sublime_detection_snr") is not None
                    else None
                ),
                sublime_autotype_spectral_type=str(row.get("sublime_autotype_spectral_type") or ""),
                moca_spectra_median_snr_per_pix=(
                    float(row["moca_spectra_median_snr_per_pix"])
                    if row.get("moca_spectra_median_snr_per_pix") is not None
                    else None
                ),
                classification=str(row["classification"]) if row.get("classification") is not None else None,
                classification_integer=Decimal(str(classification_integer)) if classification_integer is not None else None,
                comments=str(row.get("comments") or ""),
                vetting_row_exists=row.get("vetting_moca_oid") is not None,
                reviewer=str(row.get("reviewer") or ""),
                vetting_source_table=str(row.get("vetting_source_table") or ""),
                vetting_origin=str(row.get("vetting_origin") or ORIGIN),
                modified_timestamp=str(row["modified_timestamp"]) if row.get("modified_timestamp") is not None else None,
            )
        )
    return objects
