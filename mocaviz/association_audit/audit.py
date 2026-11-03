"""Candidate scoring and selection for association relationship audits."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from statistics import median
from typing import Any


POSITION_FIELDS = ("avg_x_pc", "avg_y_pc", "avg_z_pc")
POSITION_SIGMAS = ("x_stddev", "y_stddev", "z_stddev")
VELOCITY_FIELDS = ("avg_u_kms", "avg_v_kms", "avg_w_kms")
VELOCITY_SIGMAS = ("u_stddev", "v_stddev", "w_stddev")
POINT_POSITION_FIELDS = ("x_pc", "y_pc", "z_pc")
POINT_VELOCITY_FIELDS = ("u_kms", "v_kms", "w_kms")
POSITION_FLOOR_PC = 2.0
VELOCITY_FLOOR_KMS = 0.5
ABSOLUTE_POSITION_SCALE_PC = 20.0
ABSOLUTE_VELOCITY_SCALE_KMS = 3.0
DUPLICATE_NEAR_TIE_FACTOR = 1.10


def association_prefix(moca_aid: str) -> str | None:
    """Return the case-insensitive leading alphabetic catalog prefix."""
    match = re.match(r"^[A-Za-z]+", str(moca_aid))
    return match.group(0).upper() if match else None


def select_numbered_targets(
    summaries: list[dict[str, Any]], prefix: str, count: int = 50
) -> list[str]:
    target_re = re.compile(rf"^{re.escape(prefix)}(\d+)$", re.I)
    numbered: list[tuple[int, str]] = []
    for row in summaries:
        aid = str(row["moca_aid"])
        match = target_re.fullmatch(aid)
        if match:
            numbered.append((int(match.group(1)), aid))
    numbered.sort()
    targets = [aid for _, aid in numbered[:count]]
    if len(targets) != count:
        raise RuntimeError(
            f"Expected {count} integer {prefix.upper()} groups, found {len(targets)}"
        )
    return targets


def select_theia_targets(
    summaries: list[dict[str, Any]], count: int = 50
) -> list[str]:
    """Backward-compatible convenience wrapper for the initial THEIA batch."""
    return select_numbered_targets(summaries, "THEIA", count)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _distance(
    first: dict[str, Any], second: dict[str, Any], fields: tuple[str, ...]
) -> float | None:
    pairs = [(_float(first.get(key)), _float(second.get(key))) for key in fields]
    if any(left is None or right is None for left, right in pairs):
        return None
    return math.sqrt(sum((left - right) ** 2 for left, right in pairs))  # type: ignore[operator]


def _normalized_distance(
    first: dict[str, Any],
    second: dict[str, Any],
    fields: tuple[str, ...],
    sigmas: tuple[str, ...],
    floor: float,
    denominator_kind: str = "quadrature",
) -> float | None:
    components: list[float] = []
    for field, sigma in zip(fields, sigmas):
        left = _float(first.get(field))
        right = _float(second.get(field))
        if left is None or right is None:
            return None
        left_sigma = max(_float(first.get(sigma)) or floor, floor)
        right_sigma = max(_float(second.get(sigma)) or floor, floor)
        if denominator_kind == "target":
            denominator = left_sigma
        elif denominator_kind == "candidate":
            denominator = right_sigma
        elif denominator_kind == "narrower":
            denominator = min(left_sigma, right_sigma)
        else:
            denominator = math.sqrt(left_sigma**2 + right_sigma**2)
        components.append((left - right) / denominator)
    return math.sqrt(sum(value**2 for value in components) / len(components))


def _dispersion_mismatch(
    first: dict[str, Any],
    second: dict[str, Any],
    sigmas: tuple[str, ...],
    floor: float,
    one_sided: bool = False,
) -> float:
    components: list[float] = []
    for sigma in sigmas:
        left = max(_float(first.get(sigma)) or floor, floor)
        right = max(_float(second.get(sigma)) or floor, floor)
        mismatch = math.log(left / right)
        components.append(max(mismatch, 0.0) if one_sided else mismatch)
    return math.sqrt(sum(value**2 for value in components) / len(components))


def _combined_score(*components: float | None) -> float | None:
    if any(component is None for component in components):
        return None
    return math.sqrt(sum(float(component) ** 2 for component in components))


def preferred_relationship_hypothesis(
    metrics: dict[str, Any],
) -> tuple[str | None, float | None]:
    """Choose a relationship without over-interpreting subgroup score near-ties."""
    relationship_scores = {
        "duplicate/equivalent": metrics.get("duplicate_score"),
        "target-as-subgroup": metrics.get("target_subgroup_score"),
        "candidate-as-subgroup": metrics.get("candidate_subgroup_score"),
    }
    available_scores = {
        label: float(score)
        for label, score in relationship_scores.items()
        if score is not None
    }
    if not available_scores:
        return None, None
    best_hypothesis = min(available_scores, key=available_scores.get)
    best_score = available_scores[best_hypothesis]
    duplicate_score = available_scores.get("duplicate/equivalent")
    if (
        duplicate_score is not None
        and duplicate_score <= best_score * DUPLICATE_NEAR_TIE_FACTOR
    ):
        return "duplicate/equivalent", duplicate_score
    return best_hypothesis, best_score


def phase_space_metrics(
    target: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    position_pc = _distance(target, candidate, POSITION_FIELDS)
    velocity_kms = _distance(target, candidate, VELOCITY_FIELDS)
    position_target = _normalized_distance(
        target,
        candidate,
        POSITION_FIELDS,
        POSITION_SIGMAS,
        POSITION_FLOOR_PC,
        "target",
    )
    velocity_target = _normalized_distance(
        target,
        candidate,
        VELOCITY_FIELDS,
        VELOCITY_SIGMAS,
        VELOCITY_FLOOR_KMS,
        "target",
    )
    position_candidate = _normalized_distance(
        target,
        candidate,
        POSITION_FIELDS,
        POSITION_SIGMAS,
        POSITION_FLOOR_PC,
        "candidate",
    )
    velocity_candidate = _normalized_distance(
        target,
        candidate,
        VELOCITY_FIELDS,
        VELOCITY_SIGMAS,
        VELOCITY_FLOOR_KMS,
        "candidate",
    )
    position_narrow = _normalized_distance(
        target,
        candidate,
        POSITION_FIELDS,
        POSITION_SIGMAS,
        POSITION_FLOOR_PC,
        "narrower",
    )
    velocity_narrow = _normalized_distance(
        target,
        candidate,
        VELOCITY_FIELDS,
        VELOCITY_SIGMAS,
        VELOCITY_FLOOR_KMS,
        "narrower",
    )

    absolute_score = None
    if position_pc is not None and velocity_kms is not None:
        absolute_score = math.sqrt(
            (position_pc / ABSOLUTE_POSITION_SCALE_PC) ** 2
            + (velocity_kms / ABSOLUTE_VELOCITY_SCALE_KMS) ** 2
        )

    dispersion_mismatch = math.sqrt(
        (
            _dispersion_mismatch(
                target, candidate, POSITION_SIGMAS, POSITION_FLOOR_PC
            )
            ** 2
            + _dispersion_mismatch(
                target, candidate, VELOCITY_SIGMAS, VELOCITY_FLOOR_KMS
            )
            ** 2
        )
        / 2
    )
    target_extent_overflow = math.sqrt(
        (
            _dispersion_mismatch(
                target,
                candidate,
                POSITION_SIGMAS,
                POSITION_FLOOR_PC,
                one_sided=True,
            )
            ** 2
            + _dispersion_mismatch(
                target,
                candidate,
                VELOCITY_SIGMAS,
                VELOCITY_FLOOR_KMS,
                one_sided=True,
            )
            ** 2
        )
        / 2
    )
    candidate_extent_overflow = math.sqrt(
        (
            _dispersion_mismatch(
                candidate,
                target,
                POSITION_SIGMAS,
                POSITION_FLOOR_PC,
                one_sided=True,
            )
            ** 2
            + _dispersion_mismatch(
                candidate,
                target,
                VELOCITY_SIGMAS,
                VELOCITY_FLOOR_KMS,
                one_sided=True,
            )
            ** 2
        )
        / 2
    )

    duplicate_score = _combined_score(
        position_narrow,
        velocity_narrow,
        absolute_score,
        1.5 * dispersion_mismatch,
    )
    target_subgroup_score = _combined_score(
        position_candidate,
        velocity_candidate,
        absolute_score,
        1.5 * target_extent_overflow,
    )
    candidate_subgroup_score = _combined_score(
        position_target,
        velocity_target,
        absolute_score,
        1.5 * candidate_extent_overflow,
    )
    metrics = {
        "position_separation_pc": position_pc,
        "velocity_separation_kms": velocity_kms,
        "position_target_normalized": position_target,
        "velocity_target_normalized": velocity_target,
        "position_candidate_normalized": position_candidate,
        "velocity_candidate_normalized": velocity_candidate,
        "position_narrow_normalized": position_narrow,
        "velocity_narrow_normalized": velocity_narrow,
        "absolute_centroid_score": absolute_score,
        "dispersion_mismatch": dispersion_mismatch,
        "duplicate_score": duplicate_score,
        "target_subgroup_score": target_subgroup_score,
        "candidate_subgroup_score": candidate_subgroup_score,
    }
    best_hypothesis, best_score = preferred_relationship_hypothesis(metrics)
    metrics["best_relationship_score"] = best_score
    metrics["best_hypothesis"] = best_hypothesis
    # Compatibility alias: all current ranking uses the corrected best score.
    metrics["phase_score"] = best_score
    return metrics


def _robust_domain_summary(
    rows: list[dict[str, Any]],
    point_fields: tuple[str, ...],
    center_fields: tuple[str, ...],
    sigma_fields: tuple[str, ...],
) -> tuple[dict[str, float], int]:
    complete = [
        [_float(row.get(field)) for field in point_fields]
        for row in rows
        if all(_float(row.get(field)) is not None for field in point_fields)
    ]
    if len(complete) < 5:
        return {}, len(complete)
    result: dict[str, float] = {}
    for index, (center_field, sigma_field) in enumerate(
        zip(center_fields, sigma_fields)
    ):
        values = [float(row[index]) for row in complete if row[index] is not None]
        center = median(values)
        mad = median([abs(value - center) for value in values])
        result[center_field] = center
        result[sigma_field] = 1.4826 * mad
    return result, len(complete)


def robust_group_summary(
    rows: list[dict[str, Any]], fallback: dict[str, Any]
) -> dict[str, Any]:
    """Return member medians and MAD dispersions, falling back domain by domain."""
    result = dict(fallback)
    position, n_xyz = _robust_domain_summary(
        rows,
        POINT_POSITION_FIELDS,
        POSITION_FIELDS,
        POSITION_SIGMAS,
    )
    velocity, n_uvw = _robust_domain_summary(
        rows,
        POINT_VELOCITY_FIELDS,
        VELOCITY_FIELDS,
        VELOCITY_SIGMAS,
    )
    result.update(position)
    result.update(velocity)
    result["robust_n_xyz"] = n_xyz
    result["robust_n_uvw"] = n_uvw
    return result


def build_relationship_map(
    rows: list[dict[str, Any]], targets: set[str]
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    relationships: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        child = row.get("moca_aid")
        parent = row.get("parent_aid")
        if not child or not parent or child == parent:
            continue
        if child in targets:
            relationships[(str(child), str(parent))].append(
                {**row, "direction": "target_is_child"}
            )
        if parent in targets:
            relationships[(str(parent), str(child))].append(
                {**row, "direction": "candidate_is_child"}
            )
    return relationships


def _priority(candidate: dict[str, Any]) -> str:
    if candidate["known_relationships"]:
        return "known"
    overlap = candidate["membership_overlap"]
    overlap_n = overlap["overlap_n"]
    maximum_containment = max(
        overlap["target_containment"] or 0.0,
        overlap["candidate_containment"] or 0.0,
    )
    jaccard = overlap["jaccard"] or 0.0
    phase_score = candidate["phase_space"]["phase_score"]
    if (overlap_n >= 10 and maximum_containment >= 0.5) or (
        phase_score is not None and phase_score <= 3.5
    ):
        return "high"
    if (
        (overlap_n >= 10 and maximum_containment >= 0.1)
        or (overlap_n >= 5 and jaccard >= 0.05)
        or (phase_score is not None and phase_score <= 5.0)
    ):
        return "medium"
    return "context"


def _ordered_and_trimmed(
    candidates: list[dict[str, Any]],
    max_candidates: int,
) -> list[dict[str, Any]]:
    for row in candidates:
        row["priority"] = _priority(row)
    priority_order = {"known": 0, "high": 1, "medium": 2, "context": 3}
    ordered = sorted(
        candidates,
        key=lambda row: (
            priority_order[row["priority"]],
            -max(
                row["membership_overlap"]["target_containment"] or 0.0,
                row["membership_overlap"]["candidate_containment"] or 0.0,
            ),
            -row["membership_overlap"]["overlap_n"],
            row["phase_space"]["phase_score"]
            if row["phase_space"]["phase_score"] is not None
            else math.inf,
        ),
    )
    forced = [row for row in ordered if row["known_relationships"]]
    remaining = [row for row in ordered if not row["known_relationships"]]
    result = forced + remaining[: max(0, max_candidates - len(forced))]
    for rank, row in enumerate(result, start=1):
        row["rank"] = rank
    return result


def build_audits(
    summaries: list[dict[str, Any]],
    targets: list[str],
    sizes: dict[str, int],
    overlaps: list[dict[str, Any]],
    relationship_rows: list[dict[str, Any]],
    max_candidates: int = 14,
) -> list[dict[str, Any]]:
    summary_by_aid = {str(row["moca_aid"]): row for row in summaries}
    target_set = set(targets)
    relationship_map = build_relationship_map(relationship_rows, target_set)
    overlap_map = {
        (str(row["target_aid"]), str(row["candidate_aid"])): int(row["overlap_n"])
        for row in overlaps
    }
    audits: list[dict[str, Any]] = []

    for target_aid in targets:
        target = summary_by_aid[target_aid]
        target_prefix = association_prefix(target_aid)
        candidates: list[dict[str, Any]] = []
        for candidate_aid, candidate_summary in summary_by_aid.items():
            if candidate_aid == target_aid:
                continue
            if (
                target_prefix is not None
                and association_prefix(candidate_aid) == target_prefix
            ):
                continue
            metrics = phase_space_metrics(target, candidate_summary)
            overlap_n = overlap_map.get((target_aid, candidate_aid), 0)
            target_n = sizes.get(target_aid, 0)
            candidate_n = sizes.get(candidate_aid, 0)
            union_n = target_n + candidate_n - overlap_n
            overlap_info = {
                "overlap_n": overlap_n,
                "target_n": target_n,
                "candidate_n": candidate_n,
                "target_containment": overlap_n / target_n if target_n else None,
                "candidate_containment": overlap_n / candidate_n if candidate_n else None,
                "jaccard": overlap_n / union_n if union_n else None,
            }
            known = relationship_map.get((target_aid, candidate_aid), [])
            row = {
                "candidate_aid": candidate_aid,
                "candidate_name": candidate_summary.get("name"),
                "phase_space": metrics,
                "membership_overlap": overlap_info,
                "known_relationships": known,
                "summary": candidate_summary,
            }
            row["priority"] = _priority(row)
            candidates.append(row)

        phase_ranked = sorted(
            (row for row in candidates if row["phase_space"]["phase_score"] is not None),
            key=lambda row: row["phase_space"]["phase_score"],
        )
        significant_overlaps = sorted(
            (
                row
                for row in candidates
                if (
                    (
                        row["membership_overlap"]["overlap_n"] >= 10
                        and max(
                            row["membership_overlap"]["target_containment"] or 0.0,
                            row["membership_overlap"]["candidate_containment"] or 0.0,
                        )
                        >= 0.01
                    )
                    or (
                        row["membership_overlap"]["overlap_n"] >= 5
                        and (row["membership_overlap"]["jaccard"] or 0.0) >= 0.05
                    )
                    or (
                        row["membership_overlap"]["overlap_n"] >= 2
                        and row["phase_space"]["phase_score"] is not None
                        and row["phase_space"]["phase_score"] <= 5.0
                        and max(
                            row["membership_overlap"]["target_containment"] or 0.0,
                            row["membership_overlap"]["candidate_containment"] or 0.0,
                        )
                        >= 0.05
                    )
                )
            ),
            key=lambda row: (
                -max(
                    row["membership_overlap"]["target_containment"] or 0.0,
                    row["membership_overlap"]["candidate_containment"] or 0.0,
                ),
                -row["membership_overlap"]["overlap_n"],
            ),
        )
        known_rows = [row for row in candidates if row["known_relationships"]]

        selected: dict[str, dict[str, Any]] = {}
        for row in (
            known_rows
            + significant_overlaps[:max_candidates]
            + phase_ranked[:max_candidates]
        ):
            selected[row["candidate_aid"]] = row
        if len(selected) < 6:
            for row in phase_ranked:
                selected[row["candidate_aid"]] = row
                if len(selected) >= 6:
                    break

        ordered = _ordered_and_trimmed(list(selected.values()), max_candidates)

        audits.append(
            {
                "target_aid": target_aid,
                "target_name": target.get("name"),
                "target_summary": target,
                "target_direct_members": sizes.get(target_aid, 0),
                "candidates": ordered,
            }
        )
    return audits


def apply_robust_point_scores(
    audits: list[dict[str, Any]],
    points: dict[str, list[dict[str, Any]]],
    max_candidates: int,
) -> list[dict[str, Any]]:
    """Replace provisional summary scores with robust member-level scores."""
    for audit in audits:
        target_aid = str(audit["target_aid"])
        robust_target = robust_group_summary(
            points.get(target_aid, []), audit["target_summary"]
        )
        audit["target_robust_summary"] = robust_target
        for candidate in audit["candidates"]:
            candidate_aid = str(candidate["candidate_aid"])
            robust_candidate = robust_group_summary(
                points.get(candidate_aid, []), candidate["summary"]
            )
            candidate["summary_phase_space"] = candidate["phase_space"]
            candidate["robust_summary"] = robust_candidate
            metrics = phase_space_metrics(robust_target, robust_candidate)
            metrics["robust_n_target_xyz"] = robust_target["robust_n_xyz"]
            metrics["robust_n_target_uvw"] = robust_target["robust_n_uvw"]
            metrics["robust_n_candidate_xyz"] = robust_candidate["robust_n_xyz"]
            metrics["robust_n_candidate_uvw"] = robust_candidate["robust_n_uvw"]
            candidate["phase_space"] = metrics
        audit["candidates"] = _ordered_and_trimmed(
            audit["candidates"], max_candidates
        )
    return audits
