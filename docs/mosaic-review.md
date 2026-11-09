# MOSAIC proper-motion review

Start **MOSAIC Proper Motion Review** in Web Tools. It listens on
`http://127.0.0.1:8911/` and uses the launcher's management connection. It
uses the adjacent MOSAIC checkout and Python 3.11 or newer. Its sample,
astrometry, and literature reads go to MOCAdb. The reviewer is local and
does not appear on the dataviz home page.

- The public L0+ sample includes adopted public photometric estimates. For
  a SPHEREx type it requires `good` in the same SPIFF, SPIFFStacker, or
  SUBLIMEaperture lane, and the type must reference that lane's latest active
  spectrum because those vetting tables are keyed by object.
- The count starts with the catalog membership. The fitter checks epochs
  on demand, reports targets without a constrained solution separately,
  and samples up to 288 unreviewed targets for the comparison background.
  Visited fits with adopted comparators and all saved reviews with a
  comparison appear in the plot. Reviews retain the adopted PM that was
  used at review time.
- The browser starts the SciPy fit when a target appears. PM uses the
  adopted parallax when available. A second, independently fitted parallax
  appears when the seasonal coverage, independent-group count, parameter
  covariance, and resulting significance support it. The checkbox fits
  constant R.A.* and Decl. shifts for datasets with at least ten independent
  groups, anchored to the best sampled qualifying dataset. The same checkbox
  is available for SciPy in the Astrometric Explorer and defaults to off there.
- Recommended calibration applies the live checkout's production coordinate
  corrections and mission/band uncertainty floors. The scientific input
  policy remains in force with the calibration unchecked. The footer lists
  the rules and model versions. Airmass is retained in provenance, and no
  airmass correction is applied under the current production policy.

## Review controls

Use the left column to choose missions, their bands, calibration methods, and
fit inputs. The fit updates automatically. Display controls such as PM
subtraction, yearly phase, and binning change the plots without changing the
measurements used in the solution. Press **P** to toggle PM subtraction,
**A** or **1** to Adopt, and **R** or **0** to Reject.

Click a measurement or press **L** to lasso a set. The selected-row table
supports temporary fit exclusions and a separate MOCAdb ignore action.
MOCAdb updates require a selection preview and confirmation. Undo in the
review toolbar operates on Adopt and Reject decisions.

The literature panels show an adopted uncertainty band and dashed MOSAIC
uncertainty limits. The precision panel shows the ratio of the two reported
uncertainties. Click a point in the square PM-difference plot, then use
**Review selected target** or **J** to jump to it.

## Layout and diagnostics

Drag the dividers to resize the side columns, or hide either column with
the toolbar buttons. Widths and visibility are remembered in the browser.
The central plots set their display ranges from the fitted tracks and
measurements without large residuals. The outliers remain in the plot data
and in the signed and combined residual histograms.

The dashed MOSAIC envelopes use the fit covariance. The adopted trajectory
propagates the adopted reference coordinate, PM and parallax. Its shaded
envelope combines the reported uncertainty terms in quadrature.

The sample plots compare PM differences, epoch baselines, and PM
uncertainties. MOSAIC's baseline is the span from the earliest to the latest
epoch in the fit. Adopted baselines come from explicit measurement notes or
the nominal [Gaia DR2](https://doi.org/10.1051/0004-6361/201832727) and
[Gaia EDR3/DR3](https://doi.org/10.1051/0004-6361/202243940) release spans.
The precision panel plots the inverse baseline ratio so that longer MOSAIC
coverage appears on the same side as smaller MOSAIC uncertainties. Every
sample plot supports the **Review selected target** action.

## Enable decisions

Review and apply [the proposed table](../sql/schema/create_pcat_mosaic_pm_vetting.sql)
in `mocadb_private_tables`. Until it exists, the reviewer provides a read-only
preview. An Adopt saves the fitted PM in `data_proper_motions` with
`mission_name='MOSAIC'`, `origin='mocaviz_mosaic_pm_review'`, `is_public=0`,
and `rls='gagne'`, and records its foreign key in the review row. The
measurement bundle records the exact epochs, fit uncertainties and weights,
settings, and values. The tool updates only its own linked PM. Rejecting a
previous adoption marks that linked row ignored, and Undo restores the
previous decision and its PM state. MOCAdb applies its usual rules for
selecting the adopted PM. Review and PM changes share one transaction and
write to the MOCAdb changelog. A fitted parallax stays in the review bundle.
