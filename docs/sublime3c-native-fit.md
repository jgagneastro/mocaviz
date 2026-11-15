# SUBLIME3C native DR1 fitting

Native cube spectra now use the same `native_signed_student4_v1` numeric fitter as the SUBLIME3C campaign. Dispatch requires package 76 and the exact saved reduction pipeline `SUBLIME3C native DR1 cube aperture extraction`. Other SPHEREx products retain their existing fitter.

The shared source is copied verbatim from `sublime/sublime/native_spectral_fit.py`. It retains signed flux and saved ignored-pixel masks, compares every template over common wavelength coverage, and interpolates Fnu onto the observed grid. A Student-t objective with nu=4 fits a positive amplitude. The legacy dropped-point setting and empirical peculiarity calibration do not apply. Plotted model curves use the same interpolant as fitting. This fitter does not create automatic bad-pixel writes.

Selecting SUBLIME3C defaults the current-fit type minimum to L0 (10) and the native early/late score separation to 2. Both cuts use the fit displayed in the plot. The latter is best earlier-than-L0 score minus best L0+ score, not a probability or sigma significance. The score cut applies only to native DR1 spectra. Blank controls disable their cuts; direct spectrum-ID inspection bypasses queue cuts. No vetting is saved when a queue item is skipped. The header distinguishes current from adopted type and shows native-fit channel count and score separation.

Human classifications and adopted types are not changed by deployment. Explicit subsequent manual type upserts record the native fitter version and score separation. Native write receipts incorporate the fitter version, so an old cached fit cannot be submitted silently after this change. Reload the reviewer to discard old client-side fit caches.

The user explicitly accepted the documented human-good/type disagreement for SUBLIME3C 254 and authorized full-sky resumption on 2026-11-14. Campaign recovery is documented in the sibling sublime repository's `docs/sublime3c_fit_audit.md`; it does not establish native-cube purity.

Verification: existing reviewer transaction/API tests, native-only dispatch and source-parity tests, and `tests/spherex_review_native_fit_browser.mjs` cover K rejection, ambiguous L rejection, the exact L0/score-2 boundary, missing fits, paging, direct-ID inspection, and absence of vetting writes. Launch service and port are unchanged (8061); the existing Web Tools registration remains valid.

## Saved campaign selection filter

Choose **SUBLIME3C** and leave **Only updated-selection passes** checked, then reload the queue. This defaults on and limits both the database queue and total count to OIDs with at least one candidate carrying the exact current-version `AUTO_SELECTION_PASS[native_signed_student4_v1];` status prefix. Failed, absent, malformed or older-version statuses do not pass. Repeated detections do not duplicate objects. This includes the original promoted batch: 336 of 1,381 objects have a current pass; 1,045 are excluded, before the independent vetting, motion and current-fit cuts. Counts are from the 2026-11-14 selection audit.

The saved flag encodes the campaign's L0+, early/late separation, frozen CNN and channel-coverage selection. It is separate from human vetting and applies regardless of the reduction lane selected for inspection. Uncheck it to include previous candidates subject to the remaining queue filters. Clear the current-fit minimum and separation too when intentionally inspecting failures, or open a spectrum ID directly. Filtering only reads the catalog and never changes records.

Queue protocol version 15 prevents an older backend from silently ignoring the enabled filter. The checkbox also participates in saved datasets and can be set by `sublime3c_selection_pass_only=0` in a reviewer link.
