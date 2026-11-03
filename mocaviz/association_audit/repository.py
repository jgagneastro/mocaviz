"""Read-only MOCAdb queries used by the association audit."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any



SUMMARY_FIELDS = (
    "moca_aid, name, other_names, avg_x_pc, avg_y_pc, avg_z_pc, "
    "avg_u_kms, avg_v_kms, avg_w_kms, x_stddev, y_stddev, z_stddev, "
    "u_stddev, v_stddev, w_stddev, avg_ra, avg_dec, age_myr, "
    "nobj_for_stats, nfullkin, is_real, suboptimal_grouping, "
    "all_parents, all_children"
)


def _placeholders(values: Iterable[object]) -> str:
    return ",".join("%s" for _ in values)


class AssociationRepository:
    def __init__(self, database) -> None:
        self.database = database

    def summaries(self) -> list[dict[str, Any]]:
        return self.database.query(
            f"SELECT {SUMMARY_FIELDS} FROM summary_all_associations "
            "WHERE moca_aid IS NOT NULL ORDER BY moca_aid"
        )

    def direct_membership_sizes(self) -> dict[str, int]:
        rows = self.database.query(
            "SELECT moca_aid, COUNT(DISTINCT moca_oid) AS n_members "
            "FROM data_memberships "
            "WHERE ignored=0 AND moca_mtid <> 'R' AND moca_oid IS NOT NULL "
            "GROUP BY moca_aid"
        )
        return {str(row["moca_aid"]): int(row["n_members"]) for row in rows}

    def membership_overlaps(self, targets: list[str]) -> list[dict[str, Any]]:
        placeholders = _placeholders(targets)
        return self.database.query(
            "WITH target_members AS ("
            "  SELECT DISTINCT moca_aid AS target_aid, moca_oid "
            "  FROM data_memberships "
            f"  WHERE ignored=0 AND moca_mtid <> 'R' AND moca_oid IS NOT NULL "
            f"    AND moca_aid IN ({placeholders})"
            ") "
            "SELECT tm.target_aid, candidate.moca_aid AS candidate_aid, "
            "       COUNT(DISTINCT tm.moca_oid) AS overlap_n "
            "FROM target_members tm "
            "JOIN data_memberships candidate ON candidate.moca_oid=tm.moca_oid "
            "  AND candidate.ignored=0 AND candidate.moca_mtid <> 'R' "
            "  AND candidate.moca_aid <> tm.target_aid "
            "GROUP BY tm.target_aid, candidate.moca_aid "
            "HAVING COUNT(DISTINCT tm.moca_oid) >= 2",
            targets,
        )

    def relationships(self) -> list[dict[str, Any]]:
        direct = self.database.query(
            "SELECT id, moca_aid, parent_aid, moca_pid, "
            "       partial_subgroup_overlap, complete_parent_overlap, comments, bibcode, "
            "       1 AS hierarchical_level, 'direct' AS relationship_source "
            "FROM data_association_relationships "
            "WHERE ignored=0 AND parent_aid IS NOT NULL"
        )
        direct_pairs = {(row["moca_aid"], row["parent_aid"]) for row in direct}
        derived = self.database.query(
            "SELECT MIN(id) AS id, moca_aid, parent AS parent_aid, NULL AS moca_pid, "
            "       MAX(any_partial_subgroup_overlap) AS partial_subgroup_overlap, "
            "       MAX(only_complete_parent_overlap) AS complete_parent_overlap, "
            "       'Derived all-level hierarchy' AS comments, NULL AS bibcode, "
            "       MIN(hierarchical_level) AS hierarchical_level, "
            "       'derived' AS relationship_source "
            "FROM mechanics_all_association_relationships "
            "GROUP BY moca_aid, parent"
        )
        return direct + [
            row
            for row in derived
            if (row["moca_aid"], row["parent_aid"]) not in direct_pairs
        ]
