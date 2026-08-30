(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.mocaSpectralLineOverlays = api;
})(typeof globalThis === 'undefined' ? this : globalThis, function () {
  'use strict';

  const OH_SOURCE = Object.freeze({
    name: "PypeIt OH_FIRE_Echelle_lines.dat strong-line selection",
    wavelengthMedium: 'vacuum',
    localSource: 'SpeX/src/spex_autoreduce/data/oh_sky_lines_strong.csv',
  });

  const OH_LINES = Object.freeze([
    Object.freeze({ wavelengthMicron:1.083425126, relativeAmplitude:138.540893 }),
    Object.freeze({ wavelengthMicron:1.092642996, relativeAmplitude:100.044271 }),
    Object.freeze({ wavelengthMicron:1.097533046, relativeAmplitude:106.463743 }),
    Object.freeze({ wavelengthMicron:1.143989940, relativeAmplitude:154.759374 }),
    Object.freeze({ wavelengthMicron:1.153879097, relativeAmplitude:111.576606 }),
    Object.freeze({ wavelengthMicron:1.159168446, relativeAmplitude:133.806366 }),
    Object.freeze({ wavelengthMicron:1.212259447, relativeAmplitude:183.386811 }),
    Object.freeze({ wavelengthMicron:1.222929396, relativeAmplitude:133.908751 }),
    Object.freeze({ wavelengthMicron:1.228698847, relativeAmplitude:150.782544 }),
    Object.freeze({ wavelengthMicron:1.235159691, relativeAmplitude:108.930451 }),
    Object.freeze({ wavelengthMicron:1.290566153, relativeAmplitude:201.503543 }),
    Object.freeze({ wavelengthMicron:1.302163496, relativeAmplitude:144.983061 }),
    Object.freeze({ wavelengthMicron:1.308526444, relativeAmplitude:167.348432 }),
    Object.freeze({ wavelengthMicron:1.315679282, relativeAmplitude:113.996352 }),
    Object.freeze({ wavelengthMicron:1.382367943, relativeAmplitude:208.466517 }),
    Object.freeze({ wavelengthMicron:1.395100943, relativeAmplitude:147.219136 }),
    Object.freeze({ wavelengthMicron:1.402222484, relativeAmplitude:157.048111 }),
    Object.freeze({ wavelengthMicron:1.408671099, relativeAmplitude:102.611257 }),
    Object.freeze({ wavelengthMicron:1.410270310, relativeAmplitude:128.095268 }),
    Object.freeze({ wavelengthMicron:1.413400193, relativeAmplitude:209.049268 }),
    Object.freeze({ wavelengthMicron:1.416303326, relativeAmplitude:130.110053 }),
    Object.freeze({ wavelengthMicron:1.418605646, relativeAmplitude:291.501782 }),
    Object.freeze({ wavelengthMicron:1.422720145, relativeAmplitude:114.261060 }),
    Object.freeze({ wavelengthMicron:1.434437764, relativeAmplitude:868.087399 }),
    Object.freeze({ wavelengthMicron:1.435671805, relativeAmplitude:289.606079 }),
    Object.freeze({ wavelengthMicron:1.446910945, relativeAmplitude:186.491757 }),
    Object.freeze({ wavelengthMicron:1.451896099, relativeAmplitude:605.690320 }),
    Object.freeze({ wavelengthMicron:1.456398245, relativeAmplitude:225.925322 }),
    Object.freeze({ wavelengthMicron:1.460483288, relativeAmplitude:604.263184 }),
    Object.freeze({ wavelengthMicron:1.466506847, relativeAmplitude:156.520079 }),
    Object.freeze({ wavelengthMicron:1.469844116, relativeAmplitude:339.583631 }),
    Object.freeze({ wavelengthMicron:1.478373648, relativeAmplitude:187.466967 }),
    Object.freeze({ wavelengthMicron:1.479982928, relativeAmplitude:143.180015 }),
    Object.freeze({ wavelengthMicron:1.483309346, relativeAmplitude:397.150081 }),
    Object.freeze({ wavelengthMicron:1.486439695, relativeAmplitude:167.120418 }),
    Object.freeze({ wavelengthMicron:1.488764888, relativeAmplitude:522.767577 }),
    Object.freeze({ wavelengthMicron:1.493188295, relativeAmplitude:183.578470 }),
    Object.freeze({ wavelengthMicron:1.505548582, relativeAmplitude:1370.805831 }),
    Object.freeze({ wavelengthMicron:1.506896749, relativeAmplitude:472.415323 }),
    Object.freeze({ wavelengthMicron:1.508827592, relativeAmplitude:154.214253 }),
    Object.freeze({ wavelengthMicron:1.518713887, relativeAmplitude:307.329953 }),
    Object.freeze({ wavelengthMicron:1.524095394, relativeAmplitude:1026.404123 }),
    Object.freeze({ wavelengthMicron:1.528778866, relativeAmplitude:382.901796 }),
    Object.freeze({ wavelengthMicron:1.533240255, relativeAmplitude:957.972904 }),
    Object.freeze({ wavelengthMicron:1.539533445, relativeAmplitude:289.227499 }),
    Object.freeze({ wavelengthMicron:1.543214960, relativeAmplitude:622.413722 }),
    Object.freeze({ wavelengthMicron:1.550976894, relativeAmplitude:148.346839 }),
    Object.freeze({ wavelengthMicron:1.554033107, relativeAmplitude:264.407944 }),
    Object.freeze({ wavelengthMicron:1.554613569, relativeAmplitude:226.879288 }),
    Object.freeze({ wavelengthMicron:1.557015945, relativeAmplitude:106.522189 }),
    Object.freeze({ wavelengthMicron:1.559763094, relativeAmplitude:422.867988 }),
    Object.freeze({ wavelengthMicron:1.563151015, relativeAmplitude:244.792022 }),
    Object.freeze({ wavelengthMicron:1.565510283, relativeAmplitude:579.499620 }),
    Object.freeze({ wavelengthMicron:1.570253894, relativeAmplitude:209.112421 }),
    Object.freeze({ wavelengthMicron:1.583321182, relativeAmplitude:1476.957529 }),
    Object.freeze({ wavelengthMicron:1.584806042, relativeAmplitude:521.081751 }),
    Object.freeze({ wavelengthMicron:1.586930694, relativeAmplitude:164.915485 }),
    Object.freeze({ wavelengthMicron:1.597260265, relativeAmplitude:323.173938 }),
    Object.freeze({ wavelengthMicron:1.603083145, relativeAmplitude:1105.677460 }),
    Object.freeze({ wavelengthMicron:1.607975294, relativeAmplitude:426.158569 }),
    Object.freeze({ wavelengthMicron:1.612860853, relativeAmplitude:1100.889913 }),
    Object.freeze({ wavelengthMicron:1.619461545, relativeAmplitude:306.663808 }),
    Object.freeze({ wavelengthMicron:1.623537684, relativeAmplitude:716.951172 }),
    Object.freeze({ wavelengthMicron:1.631708755, relativeAmplitude:167.348284 }),
    Object.freeze({ wavelengthMicron:1.635130144, relativeAmplitude:329.944221 }),
    Object.freeze({ wavelengthMicron:1.638849193, relativeAmplitude:226.658299 }),
    Object.freeze({ wavelengthMicron:1.641473744, relativeAmplitude:106.087846 }),
    Object.freeze({ wavelengthMicron:1.644215742, relativeAmplitude:439.246015 }),
    Object.freeze({ wavelengthMicron:1.647833686, relativeAmplitude:205.540714 }),
    Object.freeze({ wavelengthMicron:1.650236494, relativeAmplitude:524.710453 }),
    Object.freeze({ wavelengthMicron:1.655381445, relativeAmplitude:177.531775 }),
    Object.freeze({ wavelengthMicron:1.669232061, relativeAmplitude:1323.825298 }),
    Object.freeze({ wavelengthMicron:1.670885177, relativeAmplitude:504.938223 }),
    Object.freeze({ wavelengthMicron:1.673249981, relativeAmplitude:164.784252 }),
    Object.freeze({ wavelengthMicron:1.684048205, relativeAmplitude:303.456531 }),
    Object.freeze({ wavelengthMicron:1.690367970, relativeAmplitude:1031.880414 }),
    Object.freeze({ wavelengthMicron:1.695507845, relativeAmplitude:360.585728 }),
    Object.freeze({ wavelengthMicron:1.700875690, relativeAmplitude:1080.090838 }),
    Object.freeze({ wavelengthMicron:1.707836944, relativeAmplitude:314.965716 }),
    Object.freeze({ wavelengthMicron:1.712365856, relativeAmplitude:698.945246 }),
    Object.freeze({ wavelengthMicron:1.721035091, relativeAmplitude:163.687216 }),
    Object.freeze({ wavelengthMicron:1.724862012, relativeAmplitude:326.758210 }),
    Object.freeze({ wavelengthMicron:1.733086894, relativeAmplitude:200.142467 }),
    Object.freeze({ wavelengthMicron:1.738636267, relativeAmplitude:392.235799 }),
    Object.freeze({ wavelengthMicron:1.742704494, relativeAmplitude:153.714003 }),
    Object.freeze({ wavelengthMicron:1.744996694, relativeAmplitude:429.509926 }),
    Object.freeze({ wavelengthMicron:1.750588324, relativeAmplitude:153.281189 }),
    Object.freeze({ wavelengthMicron:1.765316088, relativeAmplitude:1097.863115 }),
    Object.freeze({ wavelengthMicron:1.767181188, relativeAmplitude:424.907724 }),
    Object.freeze({ wavelengthMicron:1.769844244, relativeAmplitude:142.189309 }),
    Object.freeze({ wavelengthMicron:1.781147494, relativeAmplitude:248.834440 }),
    Object.freeze({ wavelengthMicron:1.788029843, relativeAmplitude:840.331119 }),
    Object.freeze({ wavelengthMicron:1.793474395, relativeAmplitude:294.956566 }),
    Object.freeze({ wavelengthMicron:1.799396191, relativeAmplitude:909.159882 }),
    Object.freeze({ wavelengthMicron:1.806793445, relativeAmplitude:250.663577 }),
    Object.freeze({ wavelengthMicron:1.811849440, relativeAmplitude:596.203661 }),
    Object.freeze({ wavelengthMicron:1.821101393, relativeAmplitude:149.415675 }),
    Object.freeze({ wavelengthMicron:1.825421523, relativeAmplitude:297.036431 }),
    Object.freeze({ wavelengthMicron:1.840157849, relativeAmplitude:261.828522 }),
    Object.freeze({ wavelengthMicron:1.845958393, relativeAmplitude:285.885030 }),
    Object.freeze({ wavelengthMicron:1.850400493, relativeAmplitude:117.128160 }),
    Object.freeze({ wavelengthMicron:1.852614250, relativeAmplitude:335.393210 }),
    Object.freeze({ wavelengthMicron:1.858732894, relativeAmplitude:115.434404 }),
    Object.freeze({ wavelengthMicron:1.874446634, relativeAmplitude:767.244642 }),
    Object.freeze({ wavelengthMicron:1.876588194, relativeAmplitude:297.672179 }),
    Object.freeze({ wavelengthMicron:1.879641143, relativeAmplitude:116.301655 }),
    Object.freeze({ wavelengthMicron:1.891483118, relativeAmplitude:186.007784 }),
    Object.freeze({ wavelengthMicron:1.899008143, relativeAmplitude:582.500897 }),
    Object.freeze({ wavelengthMicron:1.904843444, relativeAmplitude:230.370517 }),
    Object.freeze({ wavelengthMicron:1.911408468, relativeAmplitude:689.376360 }),
    Object.freeze({ wavelengthMicron:1.919353694, relativeAmplitude:200.737055 }),
    Object.freeze({ wavelengthMicron:1.925030579, relativeAmplitude:460.007281 }),
    Object.freeze({ wavelengthMicron:1.935011894, relativeAmplitude:127.752973 }),
    Object.freeze({ wavelengthMicron:1.939917664, relativeAmplitude:246.429245 }),
    Object.freeze({ wavelengthMicron:1.964246642, relativeAmplitude:114.723795 }),
    Object.freeze({ wavelengthMicron:1.970197881, relativeAmplitude:193.161755 }),
    Object.freeze({ wavelengthMicron:1.977186194, relativeAmplitude:211.578411 }),
    Object.freeze({ wavelengthMicron:2.000805857, relativeAmplitude:533.356380 }),
    Object.freeze({ wavelengthMicron:2.003321092, relativeAmplitude:218.333262 }),
    Object.freeze({ wavelengthMicron:2.019322696, relativeAmplitude:114.203018 }),
    Object.freeze({ wavelengthMicron:2.027583943, relativeAmplitude:399.657220 }),
    Object.freeze({ wavelengthMicron:2.033949762, relativeAmplitude:160.713387 }),
    Object.freeze({ wavelengthMicron:2.041268004, relativeAmplitude:440.599573 }),
    Object.freeze({ wavelengthMicron:2.049936393, relativeAmplitude:150.124009 }),
    Object.freeze({ wavelengthMicron:2.056354765, relativeAmplitude:347.329219 }),
    Object.freeze({ wavelengthMicron:2.072901428, relativeAmplitude:185.457673 }),
    Object.freeze({ wavelengthMicron:2.117655695, relativeAmplitude:118.360668 }),
    Object.freeze({ wavelengthMicron:2.124959242, relativeAmplitude:128.886191 }),
    Object.freeze({ wavelengthMicron:2.150717151, relativeAmplitude:320.586834 }),
    Object.freeze({ wavelengthMicron:2.153752253, relativeAmplitude:122.766063 }),
    Object.freeze({ wavelengthMicron:2.180231239, relativeAmplitude:245.633535 }),
    Object.freeze({ wavelengthMicron:2.195563735, relativeAmplitude:293.021883 }),
    Object.freeze({ wavelengthMicron:2.212551802, relativeAmplitude:218.594394 }),
    Object.freeze({ wavelengthMicron:2.231272001, relativeAmplitude:119.614348 }),
    Object.freeze({ wavelengthMicron:2.416105597, relativeAmplitude:120.731906 }),
    Object.freeze({ wavelengthMicron:2.419179504, relativeAmplitude:107.762141 }),
    Object.freeze({ wavelengthMicron:2.435434653, relativeAmplitude:452.606280 }),
    Object.freeze({ wavelengthMicron:2.436222245, relativeAmplitude:141.748501 }),
    Object.freeze({ wavelengthMicron:2.446105025, relativeAmplitude:325.478448 }),
    Object.freeze({ wavelengthMicron:2.450234356, relativeAmplitude:124.082836 }),
    Object.freeze({ wavelengthMicron:2.451344219, relativeAmplitude:348.514721 }),
    Object.freeze({ wavelengthMicron:2.454676955, relativeAmplitude:133.732760 }),
    Object.freeze({ wavelengthMicron:2.462768002, relativeAmplitude:297.062797 }),
    Object.freeze({ wavelengthMicron:2.472271862, relativeAmplitude:1058.799203 }),
    Object.freeze({ wavelengthMicron:2.472655941, relativeAmplitude:363.600246 }),
    Object.freeze({ wavelengthMicron:2.480533875, relativeAmplitude:152.301812 }),
    Object.freeze({ wavelengthMicron:2.481519490, relativeAmplitude:204.210977 }),
    Object.freeze({ wavelengthMicron:2.484256399, relativeAmplitude:960.310062 }),
    Object.freeze({ wavelengthMicron:2.487893067, relativeAmplitude:645.595860 }),
    Object.freeze({ wavelengthMicron:2.489437179, relativeAmplitude:126.400659 }),
    Object.freeze({ wavelengthMicron:2.492094205, relativeAmplitude:356.762522 }),
    Object.freeze({ wavelengthMicron:2.494660138, relativeAmplitude:1404.930190 }),
    Object.freeze({ wavelengthMicron:2.496589298, relativeAmplitude:119.471287 }),
    Object.freeze({ wavelengthMicron:2.498093096, relativeAmplitude:118.170431 }),
  ]);
  const OH_MAX_RELATIVE_AMPLITUDE = Math.max(
    ...OH_LINES.map(line => line.relativeAmplitude),
  );

  function ohLineOpacity(relativeAmplitude) {
    const amplitude = Number(relativeAmplitude);
    if (!Number.isFinite(amplitude) || amplitude <= 0) return 0.025;
    const normalized = Math.max(0, Math.min(1, amplitude / OH_MAX_RELATIVE_AMPLITUDE));
    return 0.025 + 0.70 * (normalized ** 0.9);
  }

  const GREEK_SUFFIXES = Object.freeze(['α', 'β', 'γ', 'δ', 'ε', 'ζ', 'η']);
  const RYDBERG_HYDROGEN_PER_M = 10967758.340;

  function hydrogenSeries(lowerLevel, firstUpper, lastUpper, prefix, series) {
    const lines = [];
    for (let upperLevel = firstUpper; upperLevel <= lastUpper; upperLevel += 1) {
      const inverseWavelength = RYDBERG_HYDROGEN_PER_M * (
        1 / (lowerLevel ** 2) - 1 / (upperLevel ** 2)
      );
      const wavelengthMicron = 1e6 / inverseWavelength;
      const suffix = GREEK_SUFFIXES[upperLevel - firstUpper];
      lines.push(Object.freeze({
        series,
        lowerLevel,
        upperLevel,
        wavelengthMicron,
        label: suffix ? `${prefix}${suffix}` : `${prefix}${upperLevel}`,
        priority: upperLevel - firstUpper,
      }));
    }
    return lines;
  }

  const HYDROGEN_LINES = Object.freeze([
    ...hydrogenSeries(3, 4, 30, 'Pa', 'Paschen'),
    ...hydrogenSeries(4, 5, 30, 'Br', 'Brackett'),
  ].sort((left, right) => left.wavelengthMicron - right.wavelengthMicron));

  function itemsInMicronRange(items, range, wavelengthKey = 'wavelengthMicron') {
    const low = Math.min(Number(range?.[0]), Number(range?.[1]));
    const high = Math.max(Number(range?.[0]), Number(range?.[1]));
    if (!Number.isFinite(low) || !Number.isFinite(high)) return items;
    return items.filter(item => {
      const wavelength = Number(item?.[wavelengthKey]);
      return Number.isFinite(wavelength) && wavelength >= low && wavelength <= high;
    });
  }

  function pointsInMicronRange(points, range) {
    const low = Math.min(Number(range?.[0]), Number(range?.[1]));
    const high = Math.max(Number(range?.[0]), Number(range?.[1]));
    if (!Number.isFinite(low) || !Number.isFinite(high)) return points;
    const selected = points.filter(point => point[0] >= low && point[0] <= high);
    if (!selected.length) return selected;
    const first = points.indexOf(selected[0]);
    const last = points.indexOf(selected[selected.length - 1]);
    return [
      ...(first > 0 ? [points[first - 1]] : []),
      ...selected,
      ...(last + 1 < points.length ? [points[last + 1]] : []),
    ];
  }

  function plotlySpectralLineShapes(range, options = {}) {
    const shapes = [];
    if (options.showOh) {
      for (const line of itemsInMicronRange(OH_LINES, range)) {
        const opacity = ohLineOpacity(line.relativeAmplitude);
        shapes.push({
          type: 'line',
          xref: 'x',
          yref: 'paper',
          x0: line.wavelengthMicron,
          x1: line.wavelengthMicron,
          y0: 0,
          y1: 1,
          line: { color: `rgba(57, 197, 207, ${opacity.toFixed(3)})`, width: 1 },
          layer: 'below',
        });
      }
    }
    if (options.showHydrogen) {
      for (const line of itemsInMicronRange(HYDROGEN_LINES, range)) {
        const color = line.series === 'Paschen' ? '255, 166, 87' : '210, 168, 255';
        shapes.push({
          type: 'line',
          xref: 'x',
          yref: 'paper',
          x0: line.wavelengthMicron,
          x1: line.wavelengthMicron,
          y0: 0,
          y1: 1,
          line: { color: `rgba(${color}, 0.48)`, width: line.priority < 4 ? 1.25 : 0.75 },
          layer: 'below',
        });
      }
    }
    return shapes;
  }

  function plotlySpectralLineAnnotations(range, options = {}) {
    if (!options.showHydrogen) return [];
    const visible = itemsInMicronRange(HYDROGEN_LINES, range);
    return visible
      .filter(line => line.priority <= 6 || visible.length <= 18)
      .map(line => ({
        x: line.wavelengthMicron,
        xref: 'x',
        y: line.series === 'Paschen' ? 0.965 : 0.905,
        yref: 'paper',
        text: line.label,
        showarrow: false,
        font: {
          size: 10,
          color: line.series === 'Paschen' ? 'rgba(190, 103, 25, 0.94)' : 'rgba(117, 73, 180, 0.94)',
        },
        textangle: -90,
        yanchor: 'top',
        captureevents: false,
      }));
  }

  return Object.freeze({
    HYDROGEN_LINES,
    OH_LINES,
    OH_MAX_RELATIVE_AMPLITUDE,
    OH_SOURCE,
    hydrogenSeries,
    itemsInMicronRange,
    ohLineOpacity,
    plotlySpectralLineAnnotations,
    plotlySpectralLineShapes,
    pointsInMicronRange,
  });
});
