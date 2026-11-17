"""Read-only SUBLIME3C morphology, tied to the displayed native detection."""
import json

TABLE = "pcat_sublime_candidates_v3c"
PIPELINE = "SUBLIME3C native DR1 cube aperture extraction"
MODES = {"all", "pass", "fail", "undefined", "not_pass"}


def native_sql(alias="s"):
    return f"({alias}.moca_specpackid=76 AND {alias}.data_reduction_pipeline='{PIPELINE}')"


def join_sql():
    # Native spectra use their exact immutable source-key name. For a different
    # reduction, use the latest active native spectrum of the same object.
    # Never borrow a passing flag from another tile/detection of that object.
    return f"""LEFT JOIN {TABLE} s3c_psf ON s3c_psf.id=(
        SELECT candidate.id FROM {TABLE} candidate
        WHERE candidate.moca_oid=s.moca_oid AND
          CONCAT('SUBLIME3C_',REPLACE(candidate.source_key,':','_'),'_DR1_cube')=
          CASE WHEN {native_sql()} THEN s.spectrum_name ELSE (
              SELECT native.spectrum_name FROM moca_spectra native
              WHERE native.moca_oid=s.moca_oid AND {native_sql('native')}
                AND native.ignored=0 ORDER BY native.moca_specid DESC LIMIT 1
          ) END
        ORDER BY candidate.id DESC LIMIT 1)"""


def status_sql():
    # Missing, unmeasured, unrecognized and inconsistent flags fail closed.
    return """CASE
        WHEN s3c_psf.psf_morphology_status='pass' AND s3c_psf.psf_point_source_pass=1 THEN 'pass'
        WHEN s3c_psf.psf_morphology_status='fail' AND s3c_psf.psf_point_source_pass=0 THEN 'fail'
        ELSE 'undefined' END"""


def metadata(cur, specid, read):
    found = read(cur, f"""SELECT s3c_psf.id AS candidate_id,s3c_psf.source_key,
        s3c_psf.visual_nn_classification AS review_priority,s3c_psf.visual_nn_good_probability AS review_priority_score,
        s3c_psf.psf_morphology_status AS stored_status,s3c_psf.psf_morphology_version AS version,
        s3c_psf.psf_morphology_json AS details,{status_sql()} AS status,
        {native_sql()} AS exact_spectrum,
        ({native_sql()} OR EXISTS(SELECT 1 FROM {TABLE} member WHERE member.moca_oid=s.moca_oid)) AS member
        FROM moca_spectra s {join_sql()} WHERE s.moca_specid=%s""", (specid,))
    if not found or not found[0].get("member"):
        return None
    row = found[0]
    raw = row.pop("details", None)
    try:
        details = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        details = None
    bands = details.get("bands", {}) if isinstance(details, dict) else {}
    row["bands"] = {name: {key: band.get(key) for key in ("status", "reason")}
                    for name, band in bands.items() if isinstance(band, dict)} if isinstance(bands, dict) else {}
    row.pop("member", None)
    row["scope"] = "This native cube detection" if row.pop("exact_spectrum") else "Latest active native cube detection for this object"
    return row
