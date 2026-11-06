"""Headless review helpers ported from the maintained SPHEREx pipeline.

Only browser-runtime dependencies are included; no desktop GUI or workers.
"""
from __future__ import annotations




DEFAULT_VISUAL_VETTING_TABLE = "pcat_spherex_visual_vetting"


STACKER_VISUAL_VETTING_TABLE = "pcat_spherex_spiffstacker_visual_vetting"


SUBLIMEAPERTURE_VISUAL_VETTING_TABLE = "pcat_spherex_sublimeaperture_visual_vetting"


DEFAULT_AUTOTYPE_QUEUE_TABLE = "pcat_spherex_spiff_queue"


STACKER_AUTOTYPE_QUEUE_TABLE = "pcat_spherex_spiff_stacker_queue"


AUTOTYPE_USABLE_VETTING_CLASSIFICATIONS = frozenset(
    {
        "good",
        "good_candidate",
        "late_M",
        "incomplete_but_promising",
        "good_plus_star",
        "contaminated_ucd",
        "good_reddened",
        "weird",
        "risky_andromeda",
        "giant",
        "peculiar_ucd",
    }
)


class AutotypeStorageError(RuntimeError):
    """Raised when the requested autotype artifact storage is unavailable."""




def default_visual_vetting_table(*, stacker: bool, sublimeaperture: bool = False) -> str:
    if sublimeaperture:
        return SUBLIMEAPERTURE_VISUAL_VETTING_TABLE
    return STACKER_VISUAL_VETTING_TABLE if stacker else DEFAULT_VISUAL_VETTING_TABLE


def default_autotype_queue_table(*, stacker: bool, sublimeaperture: bool = False) -> str:
    if sublimeaperture:
        return DEFAULT_AUTOTYPE_QUEUE_TABLE
    return STACKER_AUTOTYPE_QUEUE_TABLE if stacker else DEFAULT_AUTOTYPE_QUEUE_TABLE


def default_spiffviz_vetting_tables(*, stacker: bool, sublimeaperture: bool = False) -> tuple[str, ...]:
    visual_vetting_table = default_visual_vetting_table(
        stacker=stacker,
        sublimeaperture=sublimeaperture,
    )
    if sublimeaperture and visual_vetting_table != DEFAULT_VISUAL_VETTING_TABLE:
        return (visual_vetting_table, DEFAULT_VISUAL_VETTING_TABLE)
    return (visual_vetting_table,)
