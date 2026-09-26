(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SpectrumIndex = api;
})(typeof globalThis === 'undefined' ? this : globalThis, function () {
  'use strict';

  function matchesFilter(row, query) {
    const normalized = String(query || '').trim().toLowerCase();
    if (!normalized) return true;
    return [
      row.object_name,
      row.spectrum_name,
      row.moca_specid,
      row.moca_oid,
      row.data_reduction_pipeline_version,
      row.modification_date,
      row.observing_night,
      row.moca_specpackid,
      row.moca_instid,
      row.instrument_mode_name,
    ].join(' ').toLowerCase().includes(normalized);
  }

  function specid(row) {
    const value = Number(row.moca_specid);
    return Number.isFinite(value) ? value : Number.MAX_SAFE_INTEGER;
  }

  function modificationTime(row) {
    const value = Date.parse(row.modification_date);
    return Number.isFinite(value) ? value : null;
  }

  function sortRows(rows, mode) {
    if (mode === 'observing-night') return [...rows];
    const direction = mode === 'modified-asc' ? 1 : -1;
    return [...rows].sort((left, right) => {
      const leftTime = modificationTime(left);
      const rightTime = modificationTime(right);
      if (leftTime === null && rightTime === null) return specid(left) - specid(right);
      if (leftTime === null) return 1;
      if (rightTime === null) return -1;
      const dateOrder = direction * (leftTime - rightTime);
      return dateOrder || specid(left) - specid(right);
    });
  }

  function filterAndSort(rows, query, requireLegacy, mode) {
    const filtered = rows.filter(row =>
      (!requireLegacy || Number(row.legacy_count) > 0) && matchesFilter(row, query)
    );
    return sortRows(filtered, mode);
  }

  function navigationDelta(key) {
    if (key === 'ArrowLeft' || key === 'ArrowUp') return -1;
    if (key === 'ArrowRight' || key === 'ArrowDown') return 1;
    return 0;
  }

  function spectrumDrawMode(scatterPoints) {
    return scatterPoints ? 'scatter' : 'line';
  }

  // Meanings come from the managed pipelines' FITS writers, not from a guess
  // about this particular observation. Keep summary QA distinct from its cause.
  const QA_WARNING_DESCRIPTIONS = Object.freeze({
    TCSHQA: 'Checks the residual wavelength alignment between the science spectrum and its telluric standard.',
    TCSELQA: 'The selected telluric standard has metadata or selection caveats, such as uncertain stellar type, airmass, or saturation assessment.',
    TCHQA: 'Flags caveats in removing the standard star’s hydrogen lines, including fallback or interpolated corrections.',
    TELLURICQA: 'Checks the quality of the correction for absorption by Earth’s atmosphere.',
    TELCQA: 'Checks how much science wavelength coverage is lost through the telluric correction and final masks.',
    CALSTQA: 'A calibration STOP/Open mismatch was retained; spectral slopes and absolute flux may be a few percent off.',
    EXSCQA: 'Flags unusually large or inconsistent exposure flux scales, or an exposure excluded from the coadd because it had no usable samples.',
    F2RSPQA: 'Flags low standard-star S/N, extreme or rapidly varying response, or disagreement between standards; these quality warnings do not add pixel masks.',
    SCIQA: 'Summarizes the automated quality checks on the science exposures and final spectrum.',
    RVWCSQA: 'Checks whether wavelength-calibration accuracy is adequate for precise radial velocities.',
    RVWCPQA: 'Checks agreement between combined wavelength-calibration products.',
    RVSCIQA: 'Checks whether the spectrum is suitable for scientific radial-velocity measurements.',
    RVLMPQA: 'Checks wavelength-calibration repeatability between independent lamp exposures.',
    RVOHQA: 'Checks the wavelength calibration against atmospheric OH emission lines in the science data.',
    OHQA: 'Checks the wavelength calibration against atmospheric OH emission lines in the science data.',
    OHFXQA: 'Checks the flexure correction measured from atmospheric OH emission lines.',
    RVSLTQA: 'Checks the radial-velocity correction for the source’s position within the slit.',
    SLTRVQA: 'Checks the radial-velocity correction for the source’s position within the slit.',
    SEEINGQA: 'Checks the seeing or spatial-profile measurement; a warning does not necessarily mean the seeing is unavailable.',
    SEEQA: 'Checks the seeing or spatial-profile measurement; a warning does not necessarily mean the seeing is unavailable.',
    SPPQA: 'Checks the spatial-profile diagnostic used to assess the extraction.',
    SECTRCQA: 'Checks for an additional positive spatial trace that could contaminate the extraction.',
    SECONDARYTRACEQA: 'Checks for an additional positive spatial trace that could contaminate the extraction.',
    ORDCOVQA: 'Checks usable wavelength coverage and contiguous gaps within individual spectral orders.',
    TELLURICSHIFTSEARCHBOUNDARY: 'The science/standard shift search reached its boundary; the native zero-shift fallback was retained.',
    TELLURICSHIFTSEARCHQAUNAVAILABLE: 'The saved PySpextool state was insufficient to evaluate the science/standard shift search.',
    MISSINGINDIVIDUALEXTRACTIONS: 'Some planned science exposures are missing from the final coadd.',
    SECONDARYTRACEDETECTED: 'An additional positive spatial trace was detected and may contaminate the extracted spectrum.',
    DROPPEDINVALIDECHELLEORDERS: 'Orders with invalid slit geometry or failed arc-tilt calibration were masked; other orders were retained.',
    DROPPEDTELLURICMODELORDERS: 'Some orders lacked a supported telluric response model and were masked before coaddition.',
  });

  function qaWarningExplanation(warning) {
    const text = String(warning ?? '').trim();
    const [rawKey, ...parts] = text.split('=');
    const key = rawKey.trim().toUpperCase().replace(/_/g, '');
    const value = parts.join('=').trim().toUpperCase();
    if (key === 'TCSHQA' && /^(WARN|WARNING)$/.test(value)) {
      return 'The science/standard wavelength-shift search reached its boundary, or its quality check could not be evaluated.';
    }
    // A wrapper may carry a specific warning code as its value.
    const valueDescription = QA_WARNING_DESCRIPTIONS[value.replace(/_/g, '')];
    if (valueDescription) return valueDescription;
    if (QA_WARNING_DESCRIPTIONS[key]) return QA_WARNING_DESCRIPTIONS[key];
    return /^[A-Z][A-Z0-9_]*(?:\s*=.*)?$/i.test(text)
      ? 'No explanation is available for this pipeline flag yet.'
      : ''; // Already human-readable warnings need no invented interpretation.
  }

  function qaWarningText(warnings, emptyLabel = 'none') {
    const values = Array.isArray(warnings)
      ? [...new Set(warnings.map(value => String(value || '').trim()).filter(Boolean))]
      : [];
    if (!values.length) return `QA warnings: ${emptyLabel}`;
    return 'QA warnings:\n' + values.map(value => {
      const explanation = qaWarningExplanation(value);
      return explanation ? `${value} — ${explanation}` : value;
    }).join('\n');
  }

  function traceDrawOrder(traces) {
    return traces.map((trace, index) => ({ index, trace })).sort((left, right) => {
      const leftPriority = left.trace?.kind === 'new' ? 1 : 0;
      const rightPriority = right.trace?.kind === 'new' ? 1 : 0;
      return leftPriority - rightPriority || left.index - right.index;
    }).map(item => item.index);
  }

  function mocadbReportUrl(oid) {
    const value = String(oid ?? '').trim();
    if (!/^[1-9][0-9]*$/.test(value)) return null;
    return `https://mocadb.ca/search/results?search-query=oid%28${value}%29&search-type=star`;
  }

  function startSpectrumLoad(state, specid) {
    state.loadRequestId = Number(state.loadRequestId || 0) + 1;
    state.active = Number(specid);
    state.loading = true;
    state.traces = [];
    state.xFull = null;
    state.xView = null;
    return state.loadRequestId;
  }

  function isCurrentSpectrumLoad(state, requestId) {
    return state.loadRequestId === requestId;
  }

  return {
    filterAndSort,
    isCurrentSpectrumLoad,
    matchesFilter,
    mocadbReportUrl,
    navigationDelta,
    qaWarningExplanation,
    qaWarningText,
    sortRows,
    spectrumDrawMode,
    startSpectrumLoad,
    traceDrawOrder,
  };
});
