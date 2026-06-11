from __future__ import annotations

import argparse
import csv
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import numpy as np


DEFAULT_SOURCE_IDL = Path(
    "/Users/jonathan/Documents/IDL/IDL_library/General_Astronomy/05-BASS/"
    "F_Spectral_Analysis/Spectral_Indices/spectra_index.pro"
)
DEFAULT_ALLERS13_IDL = DEFAULT_SOURCE_IDL.with_name("allers13_index.pro")
DEFAULT_OUT_DIR = Path("notes/spectral_index_explorer")

SOURCE_PID_BY_KEY = {
    "jones1973": "Jone73",
    "kirkpatrick1991": "Kirk91",
    "kirkpatrick1995": "Kirk95",
    "reid1995": "Reid95",
    "martin1996": "Mart96",
    "kenyon1998": "Keny98",
    "kirkpatrick1999": "Kirk99a",
    "martin1999": "Mart99a",
    "reid2001": "Reid01",
    "hawley2002": "Hawl02",
    "cruz2002": "Cruz02",
    "burgasser2002b": "Burg02b",
    "mclean2003": "McLe03",
    "lyo2004": "LyoA04",
    "cushing2005": "Cush05",
    "slesnick2004": "Sles04",
    "slesnick2006": "Sles06",
    "burgasser2006": "Burg06b",
    "warren2007": "Warr07",
    "delorme2008": "Delo08a",
    "burningham2008": "Burn08",
    "shkolnik2009": "Shko09",
    "cruz2009": "Cruz09",
    "burgasser2010": None,
    "covey2010": None,
    "rojasayala2010": None,
    "rojasayala2012": "Roja12",
    "allers2013": "Alle13",
    "newton2013": None,
    "canty2013": "Cant13",
    "bardalezgagliuffi2014": "Bard14",
    "schneider2023": "Schn23",
}

INDEX_ID_BY_SOURCE_AND_NAME = {
    ("jones1973", "cah_tio"): "cah_tio",
    ("jones1973", "color"): "color_j73",
    ("kirkpatrick1991", "a"): "a_k91",
    ("kirkpatrick1991", "b"): "b_k91",
    ("kirkpatrick1991", "c"): "c_k91",
    ("kirkpatrick1991", "d"): "d_k91",
    ("kirkpatrick1995", "z_vo"): "vo_z_k95",
    ("reid1995", "tio1"): "tio_1",
    ("reid1995", "tio2"): "tio_2",
    ("reid1995", "tio3"): "tio_3",
    ("reid1995", "tio4"): "tio_4",
    ("reid1995", "tio5"): "tio_5",
    ("reid1995", "cah1"): "cah_1",
    ("reid1995", "cah2"): "cah_2",
    ("reid1995", "cah3"): "cah_3",
    ("reid1995", "caoh"): "caoh",
    ("reid1995", "ha"): "ha_r95",
    ("kirkpatrick1999", "rb_a"): "rb_a",
    ("kirkpatrick1999", "rb_b"): "rb_b",
    ("kirkpatrick1999", "cs_a"): "cs_a",
    ("kirkpatrick1999", "cs_b"): "cs_b",
    ("kirkpatrick1999", "na_a"): "na_a",
    ("kirkpatrick1999", "na_b"): "na_b",
    ("kirkpatrick1999", "tio_a"): "tio_a",
    ("kirkpatrick1999", "tio_b"): "tio_b",
    ("kirkpatrick1999", "vo_a"): "vo_a",
    ("kirkpatrick1999", "vo_b"): "vo_b",
    ("kirkpatrick1999", "crh_a"): "crh_a",
    ("kirkpatrick1999", "crh_b"): "crh_b",
    ("kirkpatrick1999", "feh_a"): "feh_a",
    ("kirkpatrick1999", "feh_b"): "feh_b",
    ("kirkpatrick1999", "color_a"): "color_a_k99",
    ("kirkpatrick1999", "color_b"): "color_b_k99",
    ("kirkpatrick1999", "color_c"): "color_c_k99",
    ("kirkpatrick1999", "color_d"): "color_d_k99",
    ("mclean2003", "h2o_a"): "h2o_a",
    ("mclean2003", "h2o_b"): "h2o_b",
    ("mclean2003", "h2o_c"): "h2o_c",
    ("mclean2003", "h2o_d"): "h2o_d",
    ("mclean2003", "ch4_a"): "ch4_a",
    ("mclean2003", "ch4_b"): "ch4_b",
    ("mclean2003", "co"): "co_mcl03",
    ("mclean2003", "j_feh"): "feh_j_mcl03",
    ("mclean2003", "z_feh"): "feh_z_mcl03",
    ("burgasser2006", "h2o_j"): "h2o_j",
    ("burgasser2006", "ch4_j"): "ch4_j",
    ("burgasser2006", "h2o_h"): "h2o_h",
    ("burgasser2006", "ch4_h"): "ch4_h",
    ("burgasser2006", "h2o_k"): "h2o_k",
    ("burgasser2006", "ch4_k"): "ch4_k",
    ("burgasser2006", "k_j"): "k_j",
    ("burgasser2010", "h_dip"): "h_dip",
    ("cruz2009", "k_a"): "k_a",
    ("cruz2009", "k_b"): "k_b",
    ("allers2013", "feh_z"): "feh_z",
    ("allers2013", "vo_z"): "vo_z",
    ("allers2013", "feh_j"): "feh_j",
    ("allers2013", "ki_j"): "ki_j",
    ("allers2013", "hcont"): "hcont",
    ("allers2013", "h2o"): "h2o_1_555",
    ("allers2013", "h2od"): "h2o_d",
    ("allers2013", "h2o_1"): "h2o_1",
    ("allers2013", "h2o_2"): "h2o_2",
    ("canty2013", "h2k"): "h2k",
    ("bardalezgagliuffi2014", "k_slope"): "k_slope",
    ("bardalezgagliuffi2014", "j_slope"): "j_slope",
    ("bardalezgagliuffi2014", "j_curve"): "j_curve",
    ("bardalezgagliuffi2014", "h_bump"): "h_bump",
    ("bardalezgagliuffi2014", "h2o_y"): "h2o_y",
    ("schneider2023", "h_slope"): "h_slope",
}

SPECIES_ID_BY_SOURCE_AND_NAME = {
    ("mclean2003", "ki_1"): "ki_1169",
    ("mclean2003", "ki_2"): "ki_1177",
    ("mclean2003", "ki_3"): "ki_1244",
    ("mclean2003", "ki_4"): "ki_1253",
    ("allers2013", "nai"): "nai_1138",
    ("allers2013", "ki_1"): "ki_1169",
    ("allers2013", "ki_2"): "ki_1177",
    ("allers2013", "ki_3"): "ki_1244",
    ("allers2013", "ki_4"): "ki_1253",
    ("rojasayala2012", "nai"): "nai_2208",
    ("newton2013", "na_221"): "nai_2208",
}


@dataclass
class DefinitionRow:
    definition_uid: str
    observable_type: str
    moca_siid: str | None
    moca_spid: str | None
    moca_pid: str | None
    source_key: str
    source_label: str
    legacy_observable_name: str
    display_name: str
    calculation_family: str
    value_unit: str | None
    wavelength_unit: str
    band_statistic: str | None
    continuum_method: str | None
    continuum_polynomial_degree: int | None
    combination_method: str
    formula_expression: str | None
    min_spectral_resolution: float | None
    min_spt: float | None
    max_spt: float | None
    min_wavelength: float | None
    max_wavelength: float | None
    legacy_source_path: str
    legacy_line_start: int
    legacy_line_end: int
    quality_status: str
    comments: str | None


@dataclass
class BandRow:
    definition_uid: str
    band_order: int
    band_role: str
    band_label: str
    wavelength_start: float | None
    wavelength_end: float | None
    band_statistic: str | None
    comments: str | None


@dataclass
class LinkRow:
    parent_definition_uid: str
    child_definition_uid: str
    link_order: int
    relationship: str
    coefficient: float | None
    comments: str | None


def _slug(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.lower())).strip("_")


def _source_key(section: str) -> str:
    return _slug(section)


def _lookup_source_key(source_key: str) -> str:
    return source_key.replace("_", "")


def _source_alias_to_key(alias: str) -> str:
    compact = _slug(alias).replace("_", "")
    match = re.fullmatch(r"([a-z]+)([0-9]{4}[a-z]?)", compact)
    if match:
        return f"{match.group(1)}_{match.group(2)}"
    return _slug(alias)


def _safe_float(text: str) -> float | None:
    try:
        return float(re.sub(r"(?i)d", "e", text))
    except ValueError:
        return None


def _display_name(name: str) -> str:
    return name.replace("_", " ")


def _strip_comment(line: str) -> str:
    out: list[str] = []
    in_quote = False
    for char in line:
        if char == "'":
            in_quote = not in_quote
        if char == ";" and not in_quote:
            break
        out.append(char)
    return "".join(out).rstrip()


def _logical_lines(text: str) -> Iterable[tuple[int, int, str, str]]:
    current = ""
    start_line: int | None = None
    section = "global"
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        section_match = re.match(r"\s*;\s*-{2,}\s*(.*?)\s*-{2,}", raw_line)
        if section_match:
            section = section_match.group(1).strip()

        line = _strip_comment(raw_line)
        if not line.strip():
            continue
        if current == "":
            start_line = lineno
        if line.rstrip().endswith("$"):
            current += line.rstrip()[:-1] + " "
            continue
        current += line
        yield int(start_line or lineno), lineno, section, current.strip()
        current = ""
        start_line = None


def _split_args(text: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    paren_depth = 0
    bracket_depth = 0
    in_quote = False
    for char in text:
        if char == "'":
            in_quote = not in_quote
        if not in_quote:
            if char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth -= 1
            elif char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth -= 1
            elif char == "," and paren_depth == 0 and bracket_depth == 0:
                args.append("".join(current).strip())
                current = []
                continue
        current.append(char)
    if current or text.strip():
        args.append("".join(current).strip())
    return args


def _transform_brackets(expr: str) -> str:
    out: list[str] = []
    stack: list[str] = []
    for index, char in enumerate(expr):
        if char == "[":
            prev_index = index - 1
            while prev_index >= 0 and expr[prev_index].isspace():
                prev_index -= 1
            prev = expr[prev_index] if prev_index >= 0 else ""
            is_index = prev.isalnum() or prev in {"_", ")", "]"}
            out.append("[" if is_index else "arr(")
            stack.append("index" if is_index else "array")
        elif char == "]":
            bracket_type = stack.pop() if stack else "array"
            out.append("]" if bracket_type == "index" else ")")
        else:
            out.append(char)
    return "".join(out)


def _idl_to_python_expr(expr: str) -> str:
    out = expr.strip()
    out = re.sub(
        r"(?i)(\d+(?:\.\d*)?|\.\d+)[dDeE]([+-]?\d+)",
        lambda match: match.group(1) + "e" + match.group(2),
        out,
    )
    out = re.sub(
        r"(?i)(\d+(?:\.\d*)?|\.\d+)[lLuUbB]",
        lambda match: match.group(1),
        out,
    )
    out = out.replace("^", "**")
    out = re.sub(r"!values\.[fd]_nan", "nan", out, flags=re.I)
    return _transform_brackets(out.lower())


def _arr(*items: Any) -> np.ndarray:
    values: list[Any] = []
    for item in items:
        values.extend(np.atleast_1d(item).tolist())
    array = np.asarray(values)
    as_float = array.astype(float)
    if as_float.size and np.all(np.isfinite(as_float)) and np.allclose(as_float, np.rint(as_float)):
        return as_float.astype(int)
    return as_float


def _evaluate(expr: str, env: dict[str, Any]) -> Any:
    local_env = {
        "arr": _arr,
        "nan": math.nan,
        "mean": lambda x: float(np.nanmean(x)),
        "sqrt": np.sqrt,
        "alog10": np.log10,
        "alog": np.log,
        "abs": np.abs,
        "reverse": lambda x: np.asarray(x)[::-1],
        "sort": lambda x: np.argsort(x),
    }
    local_env.update(env)
    return eval(_idl_to_python_expr(expr), {"__builtins__": {}}, local_env)


def _can_try_eval(expr: str) -> bool:
    skip_words = (
        "where",
        "if ",
        "then",
        "message",
        "file_",
        "plot(",
        "strjoin",
        "numtospectral",
        "spectraltonum",
        "keyword_set",
        "allers13_index",
        "readfits",
        "read_spectrum",
        "cm(",
        "robust",
        "combine",
        "poly",
        "stddev",
        "gauss",
        "random",
        "total",
        "min(",
        "max(",
        "interlace",
        "match_unsorted",
        "mpfitfun",
        "window(",
    )
    low = expr.lower()
    if any(word in low for word in skip_words):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_.,+\-*/()\[\]\s!^]+", expr))


def _keyword_statistic(call_text: str, method: str) -> str | None:
    upper = call_text.upper()
    if "/WEIGHTED_MEAN" in upper:
        return "weighted_mean"
    if "/AVERAGE" in upper:
        return "average"
    if "/MEDIAN" in upper:
        return "median"
    if "/FORCETOTAL" in upper or "/TOTAL" in upper:
        return "total"
    if method == "spectral_index":
        return "median"
    if method in {"sp_ew", "ew2"}:
        return "integral"
    return None


def _parse_kw_float(call_text: str, key: str) -> float | None:
    match = re.search(rf"\b{re.escape(key)}\s*=\s*([0-9.+\-dDeE]+)", call_text, flags=re.I)
    if not match:
        return None
    raw = re.sub(r"(?i)d", "e", match.group(1))
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_kw_int(call_text: str, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        match = re.search(rf"\b{re.escape(key)}\s*=\s*([0-9]+)", call_text, flags=re.I)
        if match:
            return int(match.group(1))
    return None


def _to_angstrom(values: Any, force_microns: bool) -> np.ndarray:
    array = np.asarray(values, dtype=float).ravel()
    if array.size == 0:
        return array
    if np.nanmax(np.abs(array)) < 100.0:
        return array * 1.0e4
    return array


def _clean_float(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(float(value)):
        return None
    rounded = round(float(value), 8)
    if abs(rounded - round(rounded)) < 1e-8:
        return float(round(rounded))
    return rounded


def _bands_for_call(
    method: str,
    args: list[str],
    env: dict[str, Any],
    call_text: str,
) -> tuple[list[BandRow], str | None, int | None, float | None, float | None]:
    lambda_arg = args[0].strip().lower() if args else ""
    force_microns = lambda_arg == "lamu" or "/MICRONS" in call_text.upper()
    statistic = _keyword_statistic(call_text, method)
    range_name = args[2].strip().lower()
    ranges = _to_angstrom(env[range_name], force_microns)
    bands: list[BandRow] = []
    continuum_method: str | None = None
    poly_degree: int | None = None

    if method == "spectral_index":
        if len(ranges) != 4:
            raise ValueError(f"spectral_index range {range_name} has {len(ranges)} values")
        bands.extend([
            BandRow("", 1, "numerator", "Numerator band", ranges[0], ranges[1], statistic, None),
            BandRow("", 2, "denominator", "Denominator band", ranges[2], ranges[3], statistic, None),
        ])
    elif method == "sp_ew":
        if len(ranges) != 6:
            raise ValueError(f"sp_ew range {range_name} has {len(ranges)} values")
        continuum_method = "two_band_linear"
        poly_degree = 1
        bands.extend([
            BandRow("", 1, "blue_continuum", "Blue continuum", ranges[0], ranges[1], None, None),
            BandRow("", 2, "feature", "Feature band", ranges[2], ranges[3], None, None),
            BandRow("", 3, "red_continuum", "Red continuum", ranges[4], ranges[5], None, None),
        ])
    elif method == "ew2":
        if len(ranges) != 2:
            raise ValueError(f"EW2 range {range_name} has {len(ranges)} values")
        continuum_method = "polynomial_windows"
        poly_degree = _parse_kw_int(call_text, ("NDEG", "NDEGREE")) or 1
        bands.append(BandRow("", 1, "feature", "Feature band", ranges[0], ranges[1], None, None))
        raw_centers = np.asarray(env[args[3].strip().lower()], dtype=float).ravel()
        raw_widths = np.asarray(env[args[4].strip().lower()], dtype=float).ravel()
        center_scale = 1.0e4 if force_microns or np.nanmax(np.abs(raw_centers)) < 100.0 else 1.0
        centers = raw_centers * center_scale
        widths = raw_widths * center_scale
        if len(widths) == 1 and len(centers) > 1:
            widths = np.repeat(widths[0], len(centers))
        for idx, (center, full_width) in enumerate(zip(centers, widths, strict=False), 1):
            half_width = full_width / 2.0
            bands.append(BandRow("", idx + 1, "continuum", f"Continuum {idx}", center - half_width, center + half_width, None, None))
    else:
        raise ValueError(f"Unsupported method {method}")

    finite_values = [
        value
        for band in bands
        for value in (band.wavelength_start, band.wavelength_end)
        if value is not None and math.isfinite(float(value))
    ]
    min_wave = min(finite_values) if finite_values else None
    max_wave = max(finite_values) if finite_values else None
    return bands, continuum_method, poly_degree, min_wave, max_wave


def _allers13_static_rows(allers13_path: Path) -> tuple[list[DefinitionRow], list[BandRow]]:
    if not allers13_path.exists():
        return [], []

    rows = [
        ("feh_z", "FeH_Z", 1.022, 0.980, 0.998, 75.0, 129),
        ("feh_j", "FeH_J", 1.208, 1.192, 1.200, 500.0, 136),
        ("vo_z", "VO_Z", 1.087, 1.035, 1.058, 75.0, 143),
        ("ki_j", "KI_J", 1.270, 1.220, 1.244, 75.0, 150),
        ("hcont", "H-cont", 1.670, 1.470, 1.560, 75.0, 157),
    ]
    source_key = "allers_2013"
    definitions: list[DefinitionRow] = []
    bands: list[BandRow] = []

    for name_key, display_name, red_center, blue_center, feature_center, resolution, line_number in rows:
        half_width = (feature_center / resolution) / 2.0
        uid = f"legacy:allers13_index.pro:{source_key}:{name_key}"
        windows = [
            ("blue_continuum", "Blue continuum", blue_center - half_width, blue_center + half_width),
            ("feature", "Feature band", feature_center - half_width, feature_center + half_width),
            ("red_continuum", "Red continuum", red_center - half_width, red_center + half_width),
        ]
        min_wave = min(value for _, _, start, end in windows for value in (start, end)) * 1.0e4
        max_wave = max(value for _, _, start, end in windows for value in (start, end)) * 1.0e4
        definitions.append(DefinitionRow(
            definition_uid=uid,
            observable_type="spectral_index",
            moca_siid=_lookup_index_id(source_key, name_key),
            moca_spid=None,
            moca_pid=_lookup_publication_id(source_key),
            source_key=source_key,
            source_label="Allers 2013",
            legacy_observable_name=name_key,
            display_name=display_name,
            calculation_family="continuum_normalized_ratio",
            value_unit=None,
            wavelength_unit="angstrom",
            band_statistic="average",
            continuum_method="two_point_linear",
            continuum_polynomial_degree=1,
            combination_method="continuum_divided_by_feature",
            formula_expression="linear_continuum_at_feature / mean(feature_band_flux)",
            min_spectral_resolution=resolution,
            min_spt=None,
            max_spt=None,
            min_wavelength=_clean_float(min_wave),
            max_wavelength=_clean_float(max_wave),
            legacy_source_path=str(allers13_path),
            legacy_line_start=line_number,
            legacy_line_end=line_number + 43,
            quality_status="review",
            comments="Parsed from allers13_index.pro helper called by spectra_index.pro. Confirm exact resolution-mode handling before marking ready.",
        ))
        for order, (role, label, start, end) in enumerate(windows, 1):
            bands.append(BandRow(
                definition_uid=uid,
                band_order=order,
                band_role=role,
                band_label=label,
                wavelength_start=_clean_float(start * 1.0e4),
                wavelength_end=_clean_float(end * 1.0e4),
                band_statistic="average" if role != "feature" else "average",
                comments=None,
            ))

    return definitions, bands


def _suggest_index_id(source_key: str, name: str) -> str:
    base = _slug(name)
    lookup_key = _lookup_source_key(source_key)
    suffix = {
        "kirkpatrick1991": "k91",
        "kirkpatrick1995": "k95",
        "kirkpatrick1999": "k99",
        "mclean2003": "mcl03",
        "burgasser2006": "burg06",
        "bardalezgagliuffi2014": "bard14",
    }.get(lookup_key, re.sub(r"[^0-9]", "", lookup_key)[-2:] or lookup_key[:4])
    candidate = f"{base}_{suffix}" if suffix and not base.endswith(suffix) else base
    return candidate[:20]


def _suggest_species_id(name: str, source_key: str) -> str:
    base = _slug(name).replace("_i_", "i_")
    lookup_key = _lookup_source_key(source_key)
    suffix = {
        "gorlova2003": "gor03",
        "rojasayala2010": "ra10",
        "rojasayala2012": "ra12",
    }.get(lookup_key)
    if suffix and len(base) <= 4:
        return f"{base}_{suffix}"[:12]
    return base[:12]


def _lookup_index_id(source_key: str, name_key: str) -> str | None:
    return INDEX_ID_BY_SOURCE_AND_NAME.get((_lookup_source_key(source_key), name_key))


def _lookup_species_id(source_key: str, name_key: str) -> str | None:
    return SPECIES_ID_BY_SOURCE_AND_NAME.get((_lookup_source_key(source_key), name_key))


def _lookup_publication_id(source_key: str) -> str | None:
    return SOURCE_PID_BY_KEY.get(_lookup_source_key(source_key))


def _relationship_for_ref(expr: str, ref_token: str) -> str:
    if re.search(r"/\s*2\.?\s*$", expr.strip()):
        return "component"
    slash_index = expr.find("/")
    if slash_index == -1:
        return "component"
    token_index = expr.find(ref_token)
    if token_index == -1:
        return "component"
    return "denominator_component" if token_index > slash_index else "numerator_component"


def _coefficient_for_ref(expr: str, ref_token: str) -> float | None:
    pattern = rf"([+-]?\s*(?:\d+(?:\.\d*)?|\.\d+)(?:[dDeE][+-]?\d+)?)\s*\*\s*{re.escape(ref_token)}"
    match = re.search(pattern, expr, flags=re.I)
    if not match:
        return None
    return _safe_float(match.group(1).replace(" ", ""))


def _formula_components(
    expr: str,
    section_var_uid: dict[str, str],
    uid_by_source_name: dict[tuple[str, str], str],
    current_source_key: str,
) -> list[tuple[str, str, str, float | None]]:
    components: list[tuple[str, str, str, float | None]] = []
    seen: set[str] = set()

    for match in re.finditer(r"\bv_([A-Za-z0-9_]+)\b", expr):
        name_key = _slug(match.group(1))
        child_uid = section_var_uid.get(name_key) or uid_by_source_name.get((current_source_key, name_key))
        if not child_uid or child_uid in seen:
            continue
        ref_token = match.group(0)
        components.append((
            child_uid,
            _relationship_for_ref(expr, ref_token),
            ref_token,
            _coefficient_for_ref(expr, ref_token),
        ))
        seen.add(child_uid)

    for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)\b", expr):
        source_key = _source_alias_to_key(match.group(1))
        name_key = _slug(match.group(2))
        child_uid = uid_by_source_name.get((source_key, name_key))
        if not child_uid or child_uid in seen:
            continue
        ref_token = match.group(0)
        components.append((
            child_uid,
            _relationship_for_ref(expr, ref_token),
            ref_token,
            _coefficient_for_ref(expr, ref_token),
        ))
        seen.add(child_uid)

    return components


def _formula_combination_method(expr: str, component_count: int) -> str:
    low = expr.lower().replace(" ", "")
    if component_count == 1 and re.fullmatch(r"\(?\s*(?:v_[a-z0-9_]+|[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)\s*\)?", expr.strip(), flags=re.I):
        return "copied_from"
    if "alog10" in low:
        return "log10_weighted_sum" if component_count > 1 else "log10"
    if component_count == 1 and "/" in low:
        return "harmonic_transform"
    if component_count > 1 and "/" in low and "1./" in low:
        return "harmonic"
    if component_count > 1 and ("0.5*" in low or "/2." in low or "/2" in low):
        return "arithmetic_mean"
    if component_count > 1 and "/" in low and low.count("/") <= 1:
        return "ratio"
    if component_count > 1 and "*" in low and "+" in low:
        return "weighted_sum"
    if component_count > 1 and "+" in low:
        return "sum"
    return "formula"


def _component_type_and_wavelengths(
    components: list[tuple[str, str, str, float | None]],
    definition_by_uid: dict[str, DefinitionRow],
) -> tuple[str, str | None, float | None, float | None]:
    child_defs = [definition_by_uid[uid] for uid, *_ in components if uid in definition_by_uid]
    if child_defs and all(row.observable_type == "equivalent_width" for row in child_defs):
        observable_type = "equivalent_width"
        value_unit = "angstrom"
    else:
        observable_type = "spectral_index"
        value_unit = None

    min_values = [row.min_wavelength for row in child_defs if row.min_wavelength is not None]
    max_values = [row.max_wavelength for row in child_defs if row.max_wavelength is not None]
    min_wave = min(min_values) if min_values else None
    max_wave = max(max_values) if max_values else None
    return observable_type, value_unit, min_wave, max_wave


def _merge_min_max(existing: dict[str, Any], row: DefinitionRow) -> None:
    for key, value in (("min_wavelength", row.min_wavelength), ("max_wavelength", row.max_wavelength)):
        if value is None:
            continue
        if existing.get(key) is None:
            existing[key] = _clean_float(value)
        elif key == "min_wavelength":
            existing[key] = _clean_float(min(float(existing[key]), float(value)))
        else:
            existing[key] = _clean_float(max(float(existing[key]), float(value)))


def assign_missing_base_ids(
    definitions: list[DefinitionRow],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    index_rows_by_id: dict[str, dict[str, Any]] = {}
    species_rows_by_id: dict[str, dict[str, Any]] = {}
    candidate_rows_out: list[dict[str, Any]] = []

    for row in definitions:
        if row.observable_type == "spectral_index" and not row.moca_siid:
            suggested_id = _suggest_index_id(row.source_key, row.legacy_observable_name)
            row.moca_siid = suggested_id
            description = f"{row.display_name} spectral index from {row.source_label}"
            candidate_rows_out.append({
                "observable_type": row.observable_type,
                "suggested_id": suggested_id,
                "definition_uid": row.definition_uid,
                "source_label": row.source_label,
                "legacy_observable_name": row.legacy_observable_name,
                "moca_pid": row.moca_pid,
                "description": description,
            })
            if suggested_id not in index_rows_by_id:
                index_rows_by_id[suggested_id] = {
                    "moca_siid": suggested_id,
                    "latex_description": description[:255],
                    "description": description[:255],
                    "moca_pid": row.moca_pid,
                    "min_spectral_resolution": row.min_spectral_resolution,
                    "min_spt": row.min_spt,
                    "max_spt": row.max_spt,
                    "min_wavelength": _clean_float(row.min_wavelength),
                    "max_wavelength": _clean_float(row.max_wavelength),
                    "comments": (
                        "Added from legacy spectral-index definition metadata for "
                        f"{row.definition_uid}. Definition quality_status remains review."
                    ),
                    "is_public": 1,
                }
            else:
                _merge_min_max(index_rows_by_id[suggested_id], row)

        if row.observable_type == "equivalent_width" and not row.moca_spid:
            suggested_id = _suggest_species_id(row.legacy_observable_name, row.source_key)
            row.moca_spid = suggested_id
            description = f"{row.display_name} equivalent width from {row.source_label}"
            candidate_rows_out.append({
                "observable_type": row.observable_type,
                "suggested_id": suggested_id,
                "definition_uid": row.definition_uid,
                "source_label": row.source_label,
                "legacy_observable_name": row.legacy_observable_name,
                "moca_pid": row.moca_pid,
                "description": description,
            })
            if suggested_id not in species_rows_by_id:
                species_rows_by_id[suggested_id] = {
                    "moca_spid": suggested_id,
                    "description": description[:255],
                    "moca_pid": row.moca_pid,
                    "min_spectral_resolution": row.min_spectral_resolution,
                    "min_spt": row.min_spt,
                    "max_spt": row.max_spt,
                    "min_wavelength": _clean_float(row.min_wavelength),
                    "max_wavelength": _clean_float(row.max_wavelength),
                    "comments": (
                        "Added from legacy equivalent-width definition metadata for "
                        f"{row.definition_uid}. Definition quality_status remains review."
                    ),
                    "is_public": 1,
                }
            else:
                _merge_min_max(species_rows_by_id[suggested_id], row)

    return list(index_rows_by_id.values()), list(species_rows_by_id.values()), candidate_rows_out


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, float):
        clean = _clean_float(value)
        return "NULL" if clean is None else repr(clean)
    if isinstance(value, int):
        return str(value)
    text = str(value)
    return "'" + text.replace("\\", "\\\\").replace("'", "''") + "'"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _insert_sql(table: str, columns: list[str], rows: list[dict[str, Any]], update_columns: list[str]) -> str:
    if not rows:
        return ""
    lines = [f"INSERT INTO `{table}` (", "  " + ", ".join(f"`{col}`" for col in columns), ") VALUES"]
    value_lines = []
    for row in rows:
        values = ", ".join(_sql_literal(row.get(col)) for col in columns)
        value_lines.append(f"  ({values})")
    lines.append(",\n".join(value_lines))
    updates = ", ".join(f"`{col}` = VALUES(`{col}`)" for col in update_columns)
    lines.append(f"ON DUPLICATE KEY UPDATE {updates};")
    return "\n".join(lines)


def _insert_if_missing_sql(
    table: str,
    key_column: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> str:
    statements: list[str] = []
    for row in rows:
        select_values = ", ".join(_sql_literal(row.get(col)) for col in columns)
        statement = [
            f"INSERT INTO `{table}` (",
            "  " + ", ".join(f"`{col}`" for col in columns),
            ")",
            f"SELECT {select_values}",
            "FROM DUAL",
            "WHERE NOT EXISTS (",
            f"  SELECT 1 FROM `{table}` WHERE `{key_column}` = {_sql_literal(row.get(key_column))} LIMIT 1",
            ")",
            ";",
        ]
        statements.append("\n".join(statement))
    return "\n\n".join(statements)


def write_base_seed_sql(
    path: Path,
    index_rows: list[dict[str, Any]],
    species_rows: list[dict[str, Any]],
) -> None:
    index_columns = [
        "moca_siid",
        "latex_description",
        "description",
        "moca_pid",
        "min_spectral_resolution",
        "min_spt",
        "max_spt",
        "min_wavelength",
        "max_wavelength",
        "comments",
        "is_public",
    ]
    species_columns = [
        "moca_spid",
        "description",
        "moca_pid",
        "min_spectral_resolution",
        "min_spt",
        "max_spt",
        "min_wavelength",
        "max_wavelength",
        "comments",
        "is_public",
    ]
    sql = [
        "-- Missing base metadata rows for spectral-observable definitions.",
        "-- Run before seed_legacy_spectral_observable_definitions.sql.",
        "-- Uses insert-if-missing because these legacy metadata tables do not declare unique keys on moca_siid/moca_spid.",
        "",
        _insert_if_missing_sql("moca_spectral_indices", "moca_siid", index_columns, index_rows),
        "",
        _insert_if_missing_sql("moca_chemical_species", "moca_spid", species_columns, species_rows),
        "",
    ]
    path.write_text("\n".join(part for part in sql if part), encoding="utf-8")


def parse_legacy_definitions(source_path: Path) -> tuple[list[DefinitionRow], list[BandRow], list[LinkRow], list[dict[str, Any]]]:
    text = source_path.read_text(errors="replace")
    env: dict[str, Any] = {}
    definitions: list[DefinitionRow] = []
    bands: list[BandRow] = []
    links: list[LinkRow] = []
    unresolved: list[dict[str, Any]] = []
    definition_by_uid: dict[str, DefinitionRow] = {}
    uid_by_source_name: dict[tuple[str, str], str] = {}
    section_var_uid: dict[str, str] = {}
    current_source_key = ""
    call_re = re.compile(r"^v_([A-Za-z0-9_]+)\s*=\s*(spectral_index|sp_ew|EW2)\s*\((.*)\)", re.I)
    scale_re = re.compile(r"^v_([A-Za-z0-9_]+)\s*/=\s*(.+)$", re.I)
    assign_re = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$")

    for start_line, end_line, section, line in _logical_lines(text):
        source_key = _source_key(section)
        if source_key != current_source_key:
            section_var_uid = {}
            current_source_key = source_key

        low = line.lower()
        if low.startswith("sortmultiple"):
            parts = _split_args(line.split(",", 1)[1])
            try:
                permutation = np.asarray(_evaluate(parts[0], env), dtype=int)
                for var_name in parts[1:]:
                    key = var_name.strip().lower()
                    if key in env:
                        env[key] = np.asarray(env[key])[permutation]
            except Exception as exc:
                unresolved.append({
                    "line": start_line,
                    "section": section,
                    "kind": "sortmultiple",
                    "name": "",
                    "reason": str(exc),
                    "source": line,
                })
            continue

        call_match = call_re.match(line)
        if call_match:
            legacy_name = call_match.group(1)
            method = call_match.group(2).lower()
            args = _split_args(call_match.group(3))
            uid = f"legacy:spectra_index.pro:{source_key}:{_slug(legacy_name)}"
            try:
                call_bands, continuum_method, poly_degree, min_wave, max_wave = _bands_for_call(method, args, env, line)
            except Exception as exc:
                unresolved.append({
                    "line": start_line,
                    "section": section,
                    "kind": method,
                    "name": legacy_name,
                    "reason": str(exc),
                    "source": line,
                })
                continue

            observable_type = "spectral_index" if method == "spectral_index" else "equivalent_width"
            name_key = _slug(legacy_name)
            moca_siid = _lookup_index_id(source_key, name_key) if observable_type == "spectral_index" else None
            moca_spid = _lookup_species_id(source_key, name_key) if observable_type == "equivalent_width" else None
            definition = DefinitionRow(
                definition_uid=uid,
                observable_type=observable_type,
                moca_siid=moca_siid,
                moca_spid=moca_spid,
                moca_pid=_lookup_publication_id(source_key),
                source_key=source_key,
                source_label=section,
                legacy_observable_name=legacy_name,
                display_name=_display_name(legacy_name),
                calculation_family="flux_ratio" if observable_type == "spectral_index" else "equivalent_width",
                value_unit=None if observable_type == "spectral_index" else "angstrom",
                wavelength_unit="angstrom",
                band_statistic=_keyword_statistic(line, method),
                continuum_method=continuum_method,
                continuum_polynomial_degree=poly_degree,
                combination_method="direct",
                formula_expression=None,
                min_spectral_resolution=_parse_kw_float(line, "RESOLUTION"),
                min_spt=None,
                max_spt=None,
                min_wavelength=min_wave,
                max_wavelength=max_wave,
                legacy_source_path=str(source_path),
                legacy_line_start=start_line,
                legacy_line_end=end_line,
                quality_status="review",
                comments=f"Parsed from IDL {method} call. Confirm publication and MOCAdb ID mapping before applying broadly.",
            )
            definitions.append(definition)
            definition_by_uid[uid] = definition
            section_var_uid[name_key] = uid
            uid_by_source_name[(source_key, name_key)] = uid
            for band in call_bands:
                band.definition_uid = uid
                band.wavelength_start = _clean_float(band.wavelength_start)
                band.wavelength_end = _clean_float(band.wavelength_end)
                bands.append(band)
            continue

        scale_match = scale_re.match(line)
        if scale_match:
            legacy_name = scale_match.group(1)
            name_key = _slug(legacy_name)
            uid = section_var_uid.get(name_key) or uid_by_source_name.get((source_key, name_key))
            if uid and uid in definition_by_uid:
                definition = definition_by_uid[uid]
                definition.combination_method = "scaled"
                definition.formula_expression = f"raw_value / ({scale_match.group(2).strip()})"
                definition.comments = (definition.comments or "") + f" IDL post-processing expression at line {start_line}: {line}."
            else:
                unresolved.append({
                    "line": start_line,
                    "section": section,
                    "kind": "post_scale",
                    "name": legacy_name,
                    "reason": "No parsed direct definition to attach scaling expression",
                    "source": line,
                })
            continue

        formula_match = assign_re.match(line)
        if formula_match and formula_match.group(1).lower().startswith("v_"):
            legacy_name = formula_match.group(1)[2:]
            expr = formula_match.group(2).strip()
            name_key = _slug(legacy_name)
            components = _formula_components(expr, section_var_uid, uid_by_source_name, source_key)
            if components:
                existing_uid = section_var_uid.get(name_key) or uid_by_source_name.get((source_key, name_key))
                if existing_uid and existing_uid in definition_by_uid:
                    component_uids = {uid for uid, *_ in components}
                    if component_uids == {existing_uid} and "reform" in expr.lower():
                        continue
                    definition = definition_by_uid[existing_uid]
                    definition.combination_method = _formula_combination_method(expr, len(components))
                    definition.formula_expression = expr
                    definition.comments = (definition.comments or "") + f" IDL post-processing expression at line {start_line}: {line}."
                    continue

                uid = f"legacy:spectra_index.pro:{source_key}:{name_key}"
                observable_type, value_unit, min_wave, max_wave = _component_type_and_wavelengths(components, definition_by_uid)
                combination_method = _formula_combination_method(expr, len(components))
                copied_child = definition_by_uid.get(components[0][0]) if combination_method == "copied_from" else None
                definition = DefinitionRow(
                    definition_uid=uid,
                    observable_type=observable_type,
                    moca_siid=(
                        copied_child.moca_siid if copied_child and observable_type == "spectral_index"
                        else _lookup_index_id(source_key, name_key) if observable_type == "spectral_index"
                        else None
                    ),
                    moca_spid=(
                        copied_child.moca_spid if copied_child and observable_type == "equivalent_width"
                        else _lookup_species_id(source_key, name_key) if observable_type == "equivalent_width"
                        else None
                    ),
                    moca_pid=_lookup_publication_id(source_key),
                    source_key=source_key,
                    source_label=section,
                    legacy_observable_name=legacy_name,
                    display_name=_display_name(legacy_name),
                    calculation_family="compound",
                    value_unit=value_unit,
                    wavelength_unit="angstrom",
                    band_statistic=None,
                    continuum_method=None,
                    continuum_polynomial_degree=None,
                    combination_method=combination_method,
                    formula_expression=expr,
                    min_spectral_resolution=None,
                    min_spt=None,
                    max_spt=None,
                    min_wavelength=_clean_float(min_wave),
                    max_wavelength=_clean_float(max_wave),
                    legacy_source_path=str(source_path),
                    legacy_line_start=start_line,
                    legacy_line_end=end_line,
                    quality_status="review",
                    comments="Parsed from IDL formula assignment. Component bands are linked separately; confirm formula semantics before marking ready.",
                )
                definitions.append(definition)
                definition_by_uid[uid] = definition
                section_var_uid[name_key] = uid
                uid_by_source_name[(source_key, name_key)] = uid
                for link_order, (child_uid, relationship, ref_token, coefficient) in enumerate(components, 1):
                    if child_uid == uid:
                        continue
                    links.append(LinkRow(
                        parent_definition_uid=uid,
                        child_definition_uid=child_uid,
                        link_order=link_order,
                        relationship=relationship,
                        coefficient=coefficient,
                        comments=f"Linked from IDL token {ref_token}.",
                    ))
                continue

        assign_match = assign_re.match(line)
        if assign_match and _can_try_eval(assign_match.group(2)):
            var_name, expr = assign_match.group(1), assign_match.group(2)
            try:
                value = _evaluate(expr, env)
                if np.isscalar(value) or len(np.atleast_1d(value)) <= 200:
                    env[var_name.lower()] = value
            except Exception:
                pass

    return definitions, bands, links, unresolved


def rows_for_output(
    definitions: list[DefinitionRow],
    bands: list[BandRow],
    links: list[LinkRow],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    definition_rows = []
    for row in definitions:
        definition_rows.append({
            "definition_uid": row.definition_uid,
            "observable_type": row.observable_type,
            "moca_siid": row.moca_siid,
            "moca_spid": row.moca_spid,
            "moca_pid": row.moca_pid,
            "source_key": row.source_key,
            "source_label": row.source_label,
            "legacy_observable_name": row.legacy_observable_name,
            "display_name": row.display_name,
            "calculation_family": row.calculation_family,
            "value_unit": row.value_unit,
            "wavelength_unit": row.wavelength_unit,
            "band_statistic": row.band_statistic,
            "continuum_method": row.continuum_method,
            "continuum_polynomial_degree": row.continuum_polynomial_degree,
            "combination_method": row.combination_method,
            "formula_expression": row.formula_expression,
            "min_spectral_resolution": row.min_spectral_resolution,
            "min_spt": row.min_spt,
            "max_spt": row.max_spt,
            "min_wavelength": _clean_float(row.min_wavelength),
            "max_wavelength": _clean_float(row.max_wavelength),
            "legacy_source_path": row.legacy_source_path,
            "legacy_line_start": row.legacy_line_start,
            "legacy_line_end": row.legacy_line_end,
            "quality_status": row.quality_status,
            "comments": row.comments,
            "is_public": 1,
        })

    band_rows = []
    for row in bands:
        band_rows.append({
            "definition_uid": row.definition_uid,
            "band_order": row.band_order,
            "band_role": row.band_role,
            "band_label": row.band_label,
            "wavelength_start": row.wavelength_start,
            "wavelength_end": row.wavelength_end,
            "band_statistic": row.band_statistic,
            "comments": row.comments,
        })

    link_rows = []
    for row in links:
        link_rows.append({
            "parent_definition_uid": row.parent_definition_uid,
            "child_definition_uid": row.child_definition_uid,
            "link_order": row.link_order,
            "relationship": row.relationship,
            "coefficient": row.coefficient,
            "comments": row.comments,
        })

    return definition_rows, band_rows, link_rows


def candidate_rows(definitions: list[DefinitionRow]) -> list[dict[str, Any]]:
    rows = []
    for row in definitions:
        if row.observable_type == "spectral_index" and not row.moca_siid:
            rows.append({
                "observable_type": row.observable_type,
                "suggested_id": _suggest_index_id(row.source_key, row.legacy_observable_name),
                "definition_uid": row.definition_uid,
                "source_label": row.source_label,
                "legacy_observable_name": row.legacy_observable_name,
                "moca_pid": row.moca_pid,
                "description": f"{row.display_name} spectral index from {row.source_label}",
            })
        if row.observable_type == "equivalent_width" and not row.moca_spid:
            rows.append({
                "observable_type": row.observable_type,
                "suggested_id": _suggest_species_id(row.legacy_observable_name, row.source_key),
                "definition_uid": row.definition_uid,
                "source_label": row.source_label,
                "legacy_observable_name": row.legacy_observable_name,
                "moca_pid": row.moca_pid,
                "description": f"{row.display_name} equivalent width from {row.source_label}",
            })
    return rows


def write_seed_sql(
    path: Path,
    definition_rows: list[dict[str, Any]],
    band_rows: list[dict[str, Any]],
    link_rows: list[dict[str, Any]],
) -> None:
    definition_columns = [
        "definition_uid",
        "observable_type",
        "moca_siid",
        "moca_spid",
        "moca_pid",
        "source_key",
        "source_label",
        "legacy_observable_name",
        "display_name",
        "calculation_family",
        "value_unit",
        "wavelength_unit",
        "band_statistic",
        "continuum_method",
        "continuum_polynomial_degree",
        "combination_method",
        "formula_expression",
        "min_spectral_resolution",
        "min_spt",
        "max_spt",
        "min_wavelength",
        "max_wavelength",
        "legacy_source_path",
        "legacy_line_start",
        "legacy_line_end",
        "quality_status",
        "comments",
        "is_public",
    ]
    band_columns = [
        "definition_uid",
        "band_order",
        "band_role",
        "band_label",
        "wavelength_start",
        "wavelength_end",
        "band_statistic",
        "comments",
    ]
    link_columns = [
        "parent_definition_uid",
        "child_definition_uid",
        "link_order",
        "relationship",
        "coefficient",
        "comments",
    ]
    sql = [
        "-- Seed metadata parsed from spectra_index.pro.",
        "-- Apply recommended_spectral_observable_definitions_schema.sql first.",
        "-- Rows are marked quality_status='review' until publication/id mappings are audited.",
        "",
        _insert_sql(
            "moca_spectral_observable_definitions",
            definition_columns,
            definition_rows,
            [col for col in definition_columns if col != "definition_uid"],
        ),
        "",
        _insert_sql(
            "moca_spectral_observable_bands",
            band_columns,
            band_rows,
            [col for col in band_columns if col not in {"definition_uid", "band_role", "band_order"}],
        ),
        "",
        _insert_sql(
            "moca_spectral_observable_definition_links",
            link_columns,
            link_rows,
            [col for col in link_columns if col not in {"parent_definition_uid", "child_definition_uid"}],
        ),
        "",
    ]
    path.write_text("\n".join(part for part in sql if part), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build review seed files for MOCAdb spectral observable definitions.")
    parser.add_argument("--source-idl", type=Path, default=DEFAULT_SOURCE_IDL)
    parser.add_argument("--allers13-idl", type=Path, default=DEFAULT_ALLERS13_IDL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    definitions, bands, links, unresolved = parse_legacy_definitions(args.source_idl)
    allers_definitions, allers_bands = _allers13_static_rows(args.allers13_idl)
    definitions.extend(allers_definitions)
    bands.extend(allers_bands)
    index_base_rows, species_base_rows, candidates = assign_missing_base_ids(definitions)
    definition_rows, band_rows, link_rows = rows_for_output(definitions, bands, links)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.out_dir / "legacy_observable_definitions.csv", definition_rows)
    _write_csv(args.out_dir / "legacy_observable_bands.csv", band_rows)
    _write_csv(args.out_dir / "legacy_observable_definition_links.csv", link_rows or [{
        "parent_definition_uid": "",
        "child_definition_uid": "",
        "link_order": "",
        "relationship": "",
        "coefficient": "",
        "comments": "",
    }])
    _write_csv(args.out_dir / "missing_base_observable_candidates.csv", candidates)
    _write_csv(args.out_dir / "legacy_observable_parse_unresolved.csv", unresolved or [{
        "line": "",
        "section": "",
        "kind": "",
        "name": "",
        "reason": "",
        "source": "",
    }])
    write_base_seed_sql(args.out_dir / "seed_missing_spectral_observable_base_rows.sql", index_base_rows, species_base_rows)
    write_seed_sql(args.out_dir / "seed_legacy_spectral_observable_definitions.sql", definition_rows, band_rows, link_rows)

    mapped_indices = sum(1 for row in definitions if row.moca_siid)
    mapped_species = sum(1 for row in definitions if row.moca_spid)
    print(f"definitions={len(definitions)}")
    print(f"bands={len(bands)}")
    print(f"definition_links={len(links)}")
    print(f"mapped_spectral_indices={mapped_indices}")
    print(f"mapped_equivalent_width_species={mapped_species}")
    print(f"new_spectral_index_base_rows={len(index_base_rows)}")
    print(f"new_equivalent_width_species_rows={len(species_base_rows)}")
    print(f"candidate_missing_base_observables={len(candidates)}")
    print(f"unresolved_parse_items={len(unresolved)}")
    print(f"out_dir={args.out_dir}")


if __name__ == "__main__":
    main()
