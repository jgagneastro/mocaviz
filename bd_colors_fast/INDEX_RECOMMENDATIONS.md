# MOCAdb Index Recommendations

These are optional schema-change recommendations for the fast BD colors page.
They are not applied by this prototype.

I checked these against live MOCAdb metadata from
`information_schema.STATISTICS` and `information_schema.TABLES` on
2026-05-08, and cross-checked the same tables in the local schema dump:

```text
/Users/jonathan/Documents/AGENTS_material/schema/mocadb_private_tables_schema_20260504_121224.sql.gz
```

MOCAdb is MariaDB 10.3, so apply these manually after reviewing `EXPLAIN`
plans on the target database. The public `mocadb` database is largely views;
indexes belong on the underlying `mocadb_private_tables` base tables.

## Recommended Missing Indexes

For the fast XYZUVW page, `summary_all_members` resolves to the private base
table `summary_all_members_both`, which has about 7.6 million rows. The member
query filters by `moca_aid` and `moca_mtid`, implicitly filters
`is_public = 0` through the view, and orders by `moca_aid, moca_mtid,
moca_oid`. Live `EXPLAIN` on 2026-05-10 used only `idx_sam_moca_aid` and still
reported `Using index condition; Using where; Using filesort`.

```sql
ALTER TABLE `summary_all_members_both`
  ADD INDEX `idx_fastxyzuvw_aid_mtid_public_oid`
  (`moca_aid`, `moca_mtid`, `is_public`, `moca_oid`);
```

The app-side query strategy was also changed so the XYZUVW member query no
longer joins through every adopted-model row and now constrains
`calc_banyan_sigma` by `moca_aid`, adopted `moca_bsmdid`, `max_observables`,
and private/public visibility. That lets MariaDB use the existing
`ix_best_pairs_fast (moca_bsmdid, max_observables, moca_aid, is_public,
moca_oid)` access path. A read-only timing comparison on the default XYZUVW
selection dropped a simplified member query from about 4.2 s to about 0.8 s;
the local JSON endpoint dropped from about 27.1 s to about 7.0 s cold, then
about 0.06 s from the in-process cache.

`data_spectral_indices` has about 9.5 million rows. It currently has separate
indexes on `moca_oid` and `moca_siid`, but no composite index covering the
page lookup by selected object, spectral-index id, and `ignored = 0`.

```sql
ALTER TABLE `data_spectral_indices`
  ADD INDEX `idx_bdcol_sidx_oid_siid_ignored`
  (`moca_oid`, `moca_siid`, `ignored`);
```

`data_equivalent_widths` has about 1.6 million rows. It currently has separate
indexes on `moca_oid` and `moca_spid`, but no composite index covering the page
lookup by selected object, chemical species id, and `ignored = 0`.

```sql
ALTER TABLE `data_equivalent_widths`
  ADD INDEX `idx_bdcol_ew_oid_spid_ignored`
  (`moca_oid`, `moca_spid`, `ignored`);
```

`data_association_ages` has about 136k rows and only one adopted row per
association, but some associations have thousands of non-adopted calculation
rows. Existing indexes include `ix_assage_assid (moca_aid)` and
`unique_calculations (moca_aid, calculation_method)`, but no composite index
covering the age-coloring join by association id plus `adopted = 1`.

```sql
ALTER TABLE `data_association_ages`
  ADD INDEX `idx_bdcol_assoc_age_aid_adopted`
  (`moca_aid`, `adopted`, `age_myr`);
```

For the legacy radial-velocity diagnostics page, the main dataset query filters
`pcat_mcmc_rv_pipeline` by `target_name`, `template_name`, and
`pipeline_version`, then orders by order/window/segment/id. The existing
`unique_idx` starts with `target_name, template_name`, but has
`order_number, window_number, segment_number` before `pipeline_version`, so it
does not fully cover the three-field dataset lookup.

```sql
ALTER TABLE `pcat_mcmc_rv_pipeline`
  ADD INDEX `idx_fastrv_dataset`
  (`target_name`, `template_name`, `pipeline_version`, `order_number`, `window_number`, `segment_number`, `id`);
```

The same page resolves diagnostic image URLs through `mechanics_file_sets` by
file-set id and description before joining to `mechanics_files`. This optional
composite index makes those lookups more selective than the existing
single-column file-set index.

```sql
ALTER TABLE `mechanics_file_sets`
  ADD INDEX `idx_fastrv_fsid_description_fid`
  (`moca_fsid`, `description`, `moca_fid`);
```

## Compared And Not Recommended

I would not add new indexes for these without an `EXPLAIN` showing a specific
problem:

- `data_spectral_types`: already has `quicklook_adopted_sptn
  (adopted, spectral_type_number)`, `quicklook_adopted_sptn2
  (adopted, photometric_estimate, spectral_type_number)`, `idx_adopted_oid
  (adopted, moca_oid)`, and object-first adopted/public-adopted composites.
- `data_photometry`: already has `quickselect
  (moca_oid, moca_psid, adopted)`, `quickselect2 (moca_oid, adopted)`, plus
  simple-band composites such as `idx_phot_simple_scan`.
- `data_distances`: already has `adopted_phot_oid
  (adopted, photometric_estimate, moca_oid)`, `adopted_oid
  (adopted, moca_oid)`, and object-first adopted/public-adopted composites.
- `data_astro_sequences`: already has `moca_seqid`, which is the key lookup for
  sequence overlays.
- `calc_banyan_sigma`: the table is large, but the age-coloring query is already
  covered by similar composites: `idx_bsmdid_maxobs_yaprob
  (moca_bsmdid, max_observables, ya_prob)`, `ix_cbs_moid_aid
  (moca_oid, moca_aid)`, and `ix_best_pairs_fast
  (moca_bsmdid, max_observables, moca_aid, is_public, moca_oid)`. The earlier
  candidate index would mostly duplicate those access paths.
- `calc_banyan_sigma_details`: the XYZUVW join uses `(cbs_id, moca_aid)`, but
  live `EXPLAIN` estimated one row through the existing `cbs_id` index. I would
  not add a composite details index unless a broader selection shows that join
  becoming measurable.
- `moca_associations`: the XYZUVW options endpoint still spends several seconds
  fetching all association choices cold, but this table already has a unique
  `moca_aid` index. This is a call-strategy issue, not an obvious missing-index
  issue; the faster design would be to return defaults immediately and search
  associations lazily as the user types.
- `data_median_colors`: the current table has about 1k rows. A publication and
  photometric-band-pair composite is not covered by the existing unique index
  `uniq_spt_ps1_ps2_pid (spectral_type_number, moca_psid1, moca_psid2,
  moca_pid)`, but the table is too small for another index to matter for this
  page.
