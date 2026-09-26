// Approximate L/T/Y brown-dwarf feature regions in vacuum wavelength (microns).
//
// Optical identifications follow Kirkpatrick et al. (1999, ApJ 519, 802) and
// Reid et al. (2000, AJ 119, 369). Near-IR bands follow Cushing et al. (2005,
// ApJ 623, 1115). Mid-IR bands follow Cushing et al. (2006, ApJ 648, 614),
// including the tentative/model-predicted LiCl band. The broad rotational and
// H2 CIA regions beyond 15 microns are Y-dwarf model opacity regions from
// Burrows et al. (2003, ApJ 596, 587), not discrete observed line complexes.

(() => {
  const palettes = {
    alkali: { fill: "rgba(139,100,0,0.10)", text: "rgba(139,100,0,0.72)" },
    ammonia: { fill: "rgba(20,120,120,0.10)", text: "rgba(20,110,110,0.72)" },
    atomic: { fill: "rgba(139,100,0,0.10)", text: "rgba(139,100,0,0.72)" },
    carbon: { fill: "rgba(80,80,80,0.08)", text: "rgba(55,55,55,0.70)" },
    cloud: { fill: "rgba(180,100,20,0.08)", text: "rgba(145,75,10,0.72)" },
    hydride: { fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.70)" },
    hydrogen: { fill: "rgba(0,105,135,0.06)", text: "rgba(0,85,115,0.70)" },
    methane: { fill: "rgba(139,69,139,0.10)", text: "rgba(139,69,139,0.72)" },
    oxide: { fill: "rgba(0,139,0,0.10)", text: "rgba(0,120,0,0.72)" },
    water: { fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.72)" },
  };

  function feature(formula, name, range, family, labelTier = 0, regime = "LTY") {
    return Object.freeze({
      formula,
      name,
      range: Object.freeze(range),
      labelTier,
      regime,
      ...palettes[family],
    });
  }

  const bands = [
    // Blue optical features detected in early/mid L dwarfs (Reid et al. 2000).
    feature("Ca I", "Ca I", [0.4215, 0.4240], "atomic", 0, "L"),
    feature("TiO", "TiO", [0.4745, 0.4775], "oxide", 1, "early L"),
    feature("MgH", "MgH", [0.4778, 0.4802], "hydride", 2, "L"),
    feature("TiO", "TiO", [0.4938, 0.4970], "oxide", 0, "early L"),
    feature("MgH", "MgH", [0.5150, 0.5250], "hydride", 1, "L"),
    feature("TiO", "TiO", [0.5425, 0.5465], "oxide", 2, "early L"),
    feature("CaOH", "CaOH", [0.5450, 0.5570], "oxide", 0, "early L"),
    feature("VO", "VO", [0.5715, 0.5755], "oxide", 1, "early L"),
    feature("Na I", "Na I", [0.5850, 0.5950], "alkali", 0, "LTY"),
    feature("TiO", "TiO", [0.6130, 0.6200], "oxide", 1, "early L"),
    feature("CaOH", "CaOH", [0.6180, 0.6280], "oxide", 2, "early L"),
    feature("Ca I", "Ca I", [0.6567, 0.6577], "atomic", 0, "early L"),
    feature("Li I", "Li I", [0.6703, 0.6713], "alkali", 1, "L"),
    feature("CaH", "CaH", [0.6750, 0.7050], "hydride", 2, "L"),
    feature("TiO", "TiO", [0.7020, 0.7150], "oxide", 0, "early L"),

    // Far-red L/T classification features (Kirkpatrick et al. 1999).
    feature("VO", "VO", [0.7330, 0.7550], "oxide", 1, "early L"),
    feature("K I", "K I", [0.7550, 0.7800], "alkali", 0, "LTY"),
    feature("Rb I", "Rb I", [0.7795, 0.7805], "alkali", 2, "L/T"),
    feature("VO", "VO", [0.7850, 0.8000], "oxide", 1, "early L"),
    feature("Rb I", "Rb I", [0.7943, 0.7953], "alkali", 2, "L/T"),
    feature("Na I", "Na I", [0.8175, 0.8202], "alkali", 0, "L/T"),
    feature("TiO", "TiO", [0.8400, 0.8460], "oxide", 1, "early L"),
    feature("Cs I", "Cs I", [0.8517, 0.8525], "alkali", 2, "L/T"),
    feature("CrH", "CrH", [0.8580, 0.8640], "hydride", 0, "L"),
    feature("FeH", "FeH", [0.8660, 0.8720], "hydride", 1, "L/T"),
    feature("CH4", "CH₄", [0.8800, 0.9100], "methane", 2, "late T/Y"),
    feature("Cs I", "Cs I", [0.8938, 0.8948], "alkali", 0, "L/T"),
    feature("H2O", "H₂O", [0.9200, 0.9800], "water", 1, "LTY"),

    // Near-IR molecular bands and atomic/hydride complexes (Cushing et al. 2005).
    feature("FeH", "FeH", [0.9850, 1.0070], "hydride", 0, "L/T"),
    feature("VO", "VO", [1.0450, 1.0800], "oxide", 1, "early L"),
    feature("H2O", "H₂O", [1.0900, 1.2000], "water", 0, "LTY"),
    feature("CH4", "CH₄", [1.1000, 1.2400], "methane", 2, "T/Y"),
    feature("Na I", "Na I", [1.1370, 1.1420], "alkali", 1, "L/T"),
    feature("K I", "K I", [1.1690, 1.1810], "alkali", 0, "L/T"),
    feature("FeH", "FeH", [1.1900, 1.2400], "hydride", 1, "L/T"),
    feature("K I", "K I", [1.2430, 1.2530], "alkali", 2, "L/T"),
    feature("H2O", "H₂O", [1.3000, 1.5100], "water", 0, "LTY"),
    feature("NH3", "NH₃", [1.4800, 1.5900], "ammonia", 2, "late T/Y"),
    feature("FeH", "FeH", [1.5800, 1.6300], "hydride", 1, "L/T"),
    feature("CH4", "CH₄", [1.6000, 1.8000], "methane", 0, "T/Y"),
    feature("H2O", "H₂O", [1.7500, 2.0500], "water", 1, "LTY"),
    feature("NH3", "NH₃", [1.9000, 2.0500], "ammonia", 2, "late T/Y"),
    feature("H2 CIA", "H₂ CIA", [2.0500, 2.4500], "hydrogen", 2, "T/Y"),
    feature("CH4", "CH₄", [2.1500, 2.5000], "methane", 0, "T/Y"),
    feature("Na I", "Na I", [2.1950, 2.2100], "alkali", 1, "L/T"),
    feature("CO", "CO", [2.2930, 2.4200], "carbon", 1, "L/T"),
    feature("H2O", "H₂O", [2.3000, 3.2000], "water", 0, "LTY"),
    feature("NH3", "NH₃", [2.8500, 3.0500], "ammonia", 2, "late T/Y"),
    feature("CH4", "CH₄", [3.0000, 3.8000], "methane", 1, "T/Y"),
    feature("OH", "OH", [3.4000, 4.2000], "oxide", 0, "M/early L"),
    feature("NH3", "NH₃", [3.9000, 4.5000], "ammonia", 2, "T/Y"),
    feature("CO2", "CO₂", [4.1500, 4.3500], "carbon", 0, "T/Y"),
    feature("PH3", "PH₃", [4.2000, 4.3500], "hydride", 1, "Y model"),
    feature("CO", "CO", [4.4000, 4.9500], "carbon", 0, "LTY"),

    // Spitzer/IRS bands and cloud signatures (Cushing et al. 2006).
    feature("H2O", "H₂O", [5.0000, 7.0000], "water", 0, "LTY"),
    feature("CH4", "CH₄", [7.0000, 9.2000], "methane", 1, "T/Y"),
    feature("silicates", "silicates", [8.0000, 12.0000], "cloud", 0, "L"),
    feature("NH3", "NH₃", [10.0000, 11.0000], "ammonia", 2, "T/Y"),
    feature("CO2", "CO₂", [14.7000, 15.3000], "carbon", 0, "T/Y"),
    feature("LiCl", "LiCl?", [15.6000, 16.0000], "alkali", 1, "model/tentative"),

    // Broad, model-predicted opacity regions for the coolest Y-like objects.
    feature("H2O rotational", "H₂O rot.", [15.0000, 30.0000], "water", 2, "Y model"),
    feature("CH4 rotational", "CH₄ rot.", [18.0000, 30.0000], "methane", 1, "Y model"),
    feature("H2 CIA far-IR", "H₂ CIA", [20.0000, 50.0000], "hydrogen", 0, "Y model"),
  ];

  const frozenBands = Object.freeze(bands);

  function bandsInRange(range) {
    const xmin = Number(range?.[0]);
    const xmax = Number(range?.[1]);
    if (!Number.isFinite(xmin) || !Number.isFinite(xmax)) return frozenBands;
    const low = Math.min(xmin, xmax);
    const high = Math.max(xmin, xmax);
    return frozenBands.filter((band) => band.range[1] >= low && band.range[0] <= high);
  }

  function clippedBandRange(band, range) {
    const xmin = Number(range?.[0]);
    const xmax = Number(range?.[1]);
    if (!Number.isFinite(xmin) || !Number.isFinite(xmax)) return band.range;
    const low = Math.min(xmin, xmax);
    const high = Math.max(xmin, xmax);
    return [Math.max(band.range[0], low), Math.min(band.range[1], high)];
  }

  globalThis.mocaBrownDwarfSpectralFeatureBands = frozenBands;
  globalThis.mocaBrownDwarfSpectralFeatureBandsInRange = bandsInRange;
  globalThis.mocaClippedSpectralFeatureBandRange = clippedBandRange;
})();
