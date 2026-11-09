"""Constant R.A.* and Decl. nuisance offsets for multi-survey astrometry."""
from collections import defaultdict

import numpy as np

MIN_SURVEY_GROUPS = 10


def survey_offset_basis(missions, groups):
    """Anchor the best sampled dataset and fit only well-sampled alternatives."""
    unique_groups = defaultdict(set)
    for mission, group in zip(missions, groups):
        if mission and mission != "No mission":
            unique_groups[mission].add(group)
    eligible = sorted(
        (mission for mission, values in unique_groups.items() if len(values) >= MIN_SURVEY_GROUPS),
        key=lambda mission: (-len(unique_groups[mission]), mission),
    )
    if len(eligible) < 2:
        return None, [], np.zeros((len(missions), 0))
    labels = np.asarray(missions)
    return eligible[0], eligible[1:], np.column_stack([labels == name for name in eligible[1:]]).astype(float)


def add_offset_columns(design, indicators):
    count = indicators.shape[1]
    if not count:
        return design
    blocks = np.zeros((2 * len(indicators), 2 * count))
    blocks[:len(indicators), :count] = indicators
    blocks[len(indicators):, count:] = indicators
    return np.column_stack((design, blocks))


def fitted_survey_offsets(anchor, labels, params):
    count = len(labels)
    return {
        "anchor": anchor,
        "minimumGroups": MIN_SURVEY_GROUPS,
        "values": {name: {"raMas": float(ra), "decMas": float(dec)}
                   for name, ra, dec in zip(labels, params[:count], params[count:])},
    }
