import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

const xuvThreeDualMode = document.body?.classList.contains("xyzuvw-three-dual-page");
const xuvThreeDualPanelDefs = [
  { key: "xyz", label: "XYZ", axes: ["x", "y", "z"] },
  { key: "uvw", label: "UVW", axes: ["u", "v", "w"] },
];

const xuvAxes = [
  { value: "x", label: "X", unit: "pc" },
  { value: "y", label: "Y", unit: "pc" },
  { value: "z", label: "Z", unit: "pc" },
  { value: "u", label: "U", unit: "km/s" },
  { value: "v", label: "V", unit: "km/s" },
  { value: "w", label: "W", unit: "km/s" },
];

const xuvDefaultAids = ["HYA", "TWA", "CBER", "PERI", "BL1", "BPMG"];
const xuvDefaultMtids = ["BF", "HM", "CM"];
const xuvDefaultAxes = ["x", "y", "z"];
const xuvCleanReferenceRadii = [10, 100, 1000];
const xuvCleanVelocityReferenceRadii = [10, 50, 100];
const xuvCleanSceneBackground = "#08090c";
const xuvCleanCircleColor = "#00a8ff";
const xuvCleanReferenceColor = "#00a8ff";
const xuvCleanPlaneColor = "#73c9ff";
const xuvMemberPointSize = 4.4;
const xuvOverlayPointRadius = 4.8;
const xuvDataPointOpacity = 0.7;
const xuvSelectionColor = "#ffd21a";
const xuvSunCrossRadius = 0.9;
const xuvVerticalReferenceAxisScale = 0.25;
const xuvRvRange = Array.from({ length: 50 }, (_value, index) => -50 + index * (100 / 49));
const xuvKappa = 0.004743717361;
const xuvTgal = [
  [-0.0548755604, -0.8734370902, -0.4838350155],
  [0.4941094279, -0.44482963, 0.7469822445],
  [-0.867666149, -0.1980763734, 0.4559837762],
];

const xuvPalette = [
  "#e52638", "#1ed46b", "#bc337d", "#9ee5a4", "#db2bee",
  "#167b2b", "#f2b0f6", "#bce333", "#710c9e", "#d9c771",
  "#5e3966", "#65e6f9", "#9e4302", "#389eaa", "#f19189",
  "#214a65", "#ded1d4", "#1b48bc", "#fd8f2f", "#4c93e9",
];

const xuvState = {
  options: { associations: [], mtids: [], versions: [] },
  selectedAids: [...xuvDefaultAids],
  selectedMtids: [...xuvDefaultMtids],
  selectedOids: [],
  payload: null,
  displayedRows: [],
  selectedRows: [],
  hiddenAids: new Set(),
  cValue: 8,
  loadToken: 0,
  searchTimer: null,
  aidSearchTimer: null,
  cameraInitialized: false,
  lastCameraAxes: "",
  pointerDown: null,
  selectionMarkerRadius: 7,
  threePanels: [],
  panelPayloads: {},
  three: {
    scene: null,
    camera: null,
    renderer: null,
    labelRenderer: null,
    controls: null,
    dataGroup: null,
    selectedGroup: null,
    cameraTargetGroup: null,
    galaxyMesh: null,
    pickObjects: [],
    raycaster: null,
    pointer: new THREE.Vector2(),
    pointTexture: null,
    resizeObserver: null,
  },
};

const xuvEl = {};

const xuvAppBaseUrl = new URL("../", import.meta.url).toString();

document.addEventListener("DOMContentLoaded", initXyzuvwThree);

function xuvAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), xuvAppBaseUrl).toString();
}

async function initXyzuvwThree() {
  collectXyzuvwElements();
  populateAxisSelects();
  readXyzuvwUrlState();
  setupThreeScene();
  bindXyzuvwControls();
  renderOidChips();
  await loadXyzuvwOptions();
  await loadXyzuvwData();
}

function collectXyzuvwElements() {
  [
    "xuv-status",
    "xuv-axis-1",
    "xuv-axis-2",
    "xuv-axis-3",
    "xuv-aids-default",
    "xuv-aids-clear",
    "xuv-aid-search",
    "xuv-aid-results",
    "xuv-selected-aids",
    "xuv-mtid-list",
    "xuv-object-search",
    "xuv-object-results",
    "xuv-oid-input",
    "xuv-selected-oids",
    "xuv-bsmdid",
    "xuv-models",
    "xuv-errors",
    "xuv-assmem",
    "xuv-hover",
    "xuv-show-axes",
    "xuv-galaxy-bg",
    "xuv-likely",
    "xuv-asscen",
    "xuv-load",
    "xuv-plot",
    "xuv-three-canvas",
    "xuv-three-legend",
    "xuv-three-tooltip",
    "xuv-plot-xyz",
    "xuv-three-canvas-xyz",
    "xuv-three-legend-xyz",
    "xuv-three-tooltip-xyz",
    "xuv-plot-uvw",
    "xuv-three-canvas-uvw",
    "xuv-three-legend-uvw",
    "xuv-three-tooltip-uvw",
    "xuv-plot-loader",
    "xuv-summary",
    "xuv-hint",
    "xuv-open-report",
    "xuv-export-csv",
    "xuv-export-tsv",
    "xuv-export-fits",
    "xuv-export-votable",
    "xuv-clear-cache-bottom",
    "xuv-clear-cache-status",
    "xuv-table-title",
    "xuv-table-subtitle",
    "xuv-table",
    "xuv-hint-text",
    "xuv-recenter-sun",
  ].forEach((id) => {
    xuvEl[id] = document.getElementById(id);
  });
}

function setupThreeScene() {
  const panelDefs = xuvThreeDualMode
    ? xuvThreeDualPanelDefs.map((panel) => ({
      ...panel,
      plotEl: xuvEl[`xuv-plot-${panel.key}`],
      container: xuvEl[`xuv-three-canvas-${panel.key}`],
      legendEl: xuvEl[`xuv-three-legend-${panel.key}`],
      tooltipEl: xuvEl[`xuv-three-tooltip-${panel.key}`],
    }))
    : [{
      key: "main",
      label: "",
      axes: null,
      plotEl: xuvEl["xuv-plot"],
      container: xuvEl["xuv-three-canvas"],
      legendEl: xuvEl["xuv-three-legend"],
      tooltipEl: xuvEl["xuv-three-tooltip"],
    }];
  xuvState.threePanels = panelDefs
    .filter((panel) => panel.container)
    .map((panel) => setupThreePanel(panel));
  xuvState.three = xuvState.threePanels[0] || xuvState.three;
  animateThree();
}

function setupThreePanel(panelDef) {
  const container = panelDef.container;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(xuvCleanSceneBackground);

  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 20000);
  camera.up.set(0, 0, 1);
  camera.position.set(265, -340, 250);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.domElement.className = "xuv-three-renderer";
  container.appendChild(renderer.domElement);

  const labelRenderer = new CSS2DRenderer();
  labelRenderer.domElement.className = "xuv-three-label-layer";
  container.appendChild(labelRenderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.075;
  controls.enablePan = true;
  controls.enableRotate = true;
  controls.enableZoom = true;
  controls.rotateSpeed = 0.48;
  controls.zoomSpeed = 1.08;
  controls.panSpeed = 0.62;
  controls.keyPanSpeed = 18;
  controls.screenSpacePanning = true;
  controls.mouseButtons = {
    LEFT: THREE.MOUSE.ROTATE,
    MIDDLE: THREE.MOUSE.DOLLY,
    RIGHT: THREE.MOUSE.PAN,
  };
  controls.touches = {
    ONE: THREE.TOUCH.ROTATE,
    TWO: THREE.TOUCH.DOLLY_PAN,
  };
  if ("zoomToCursor" in controls) controls.zoomToCursor = false;
  controls.target.set(0, 0, 0);

  const ambient = new THREE.AmbientLight(0xffffff, 0.62);
  const key = new THREE.DirectionalLight(0xffffff, 1.25);
  key.position.set(0.7, -1.2, 1.4);
  scene.add(ambient, key);

  const dataGroup = new THREE.Group();
  const selectedGroup = new THREE.Group();
  const cameraTargetGroup = new THREE.Group();
  cameraTargetGroup.visible = false;
  scene.add(dataGroup, selectedGroup, cameraTargetGroup);

  const panel = {
    ...xuvState.three,
    key: panelDef.key,
    label: panelDef.label,
    axes: panelDef.axes,
    plotEl: panelDef.plotEl,
    container,
    legendEl: panelDef.legendEl,
    tooltipEl: panelDef.tooltipEl,
    scene,
    camera,
    renderer,
    labelRenderer,
    controls,
    dataGroup,
    selectedGroup,
    cameraTargetGroup,
    pickObjects: [],
    raycaster: new THREE.Raycaster(),
    pointTexture: createPointTexture(),
    cameraInitialized: false,
    lastCameraAxes: "",
  };
  panel.raycaster.params.Points.threshold = 5;

  renderer.domElement.addEventListener("pointerdown", (event) => {
    withThreePanel(panel, () => {
      xuvState.pointerDown = { x: event.clientX, y: event.clientY, button: event.button, panelKey: panel.key };
    });
  });
  renderer.domElement.addEventListener("pointerup", (event) => withThreePanel(panel, () => onThreePointerUp(event)));
  renderer.domElement.addEventListener("pointermove", (event) => withThreePanel(panel, () => onThreePointerMove(event)));
  renderer.domElement.addEventListener("pointerleave", () => withThreePanel(panel, hideThreeTooltip));
  renderer.domElement.addEventListener("contextmenu", (event) => event.preventDefault());
  renderer.domElement.addEventListener("dblclick", () => {
    xuvState.selectedRows = [];
    renderSelectedMarkers();
    renderXyzuvwTable();
  });

  const resize = () => resizeThree(panel);
  panel.resizeObserver = new ResizeObserver(resize);
  panel.resizeObserver.observe(container);
  window.addEventListener("resize", debounce(resize, 100));
  resizeThree(panel);
  return panel;
}

function resizeThree(panel = xuvState.three) {
  const { camera, renderer, labelRenderer, container } = panel || {};
  if (!camera || !renderer || !container) return;
  const rect = container.getBoundingClientRect();
  const width = Math.max(1, Math.floor(rect.width));
  const height = Math.max(1, Math.floor(rect.height));
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
  labelRenderer.setSize(width, height);
}

function activeThreePanels() {
  return xuvState.threePanels.length ? xuvState.threePanels : [xuvState.three].filter((panel) => panel?.scene);
}

function withThreePanel(panel, callback) {
  const previousPanel = xuvState.three;
  xuvState.three = panel;
  try {
    return callback(panel);
  } finally {
    xuvState.three = previousPanel;
  }
}

function forEachThreePanel(callback) {
  activeThreePanels().forEach((panel) => withThreePanel(panel, callback));
}

function animateThree() {
  requestAnimationFrame(animateThree);
  for (const panel of activeThreePanels()) {
    withThreePanel(panel, () => {
      const { scene, camera, renderer, labelRenderer, controls } = panel;
      if (!scene || !camera || !renderer) return;
      controls.update();
      updateGalaxyBackground();
      updateCameraTargetMarker();
      renderer.render(scene, camera);
      labelRenderer.render(scene, camera);
    });
  }
}

function ensureGalaxyBackground() {
  if (xuvState.three.galaxyMesh || !xuvState.three.scene) return;
  const texture = createGalaxyTexture();
  const geometry = new THREE.SphereGeometry(1, 96, 48);
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    color: 0xaeb4c0,
    side: THREE.BackSide,
    depthTest: false,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.renderOrder = -10000;
  mesh.userData = { kind: "galaxy-background" };
  mesh.raycast = () => {};
  xuvState.three.scene.add(mesh);
  xuvState.three.galaxyMesh = mesh;
}

function updateGalaxyBackground() {
  const { camera, controls, galaxyMesh } = xuvState.three;
  if (!camera || !controls || !galaxyMesh) return;
  const visible = isGalaxyBackgroundActive();
  if (!visible) {
    galaxyMesh.visible = false;
    return;
  }

  const viewDistance = camera.position.distanceTo(controls.target);
  const radius = Math.min(camera.far * 0.42, Math.max(4500, viewDistance * 6));
  galaxyMesh.visible = true;
  galaxyMesh.position.copy(camera.position);
  galaxyMesh.rotation.set(Math.PI / 2, 0, 0);
  galaxyMesh.scale.setScalar(radius);
}

function syncGalaxyBackgroundControl() {
  const checkbox = xuvEl["xuv-galaxy-bg"];
  if (!checkbox) return;
  const showAxes = Boolean(xuvEl["xuv-show-axes"]?.checked);
  const xyzMode = isXyzMode();
  const disabled = showAxes || !xyzMode;
  checkbox.disabled = disabled;
  const label = checkbox.closest(".checkline");
  if (label) {
    label.classList.toggle("is-disabled", disabled);
    label.title = showAxes
      ? "Galaxy background is unavailable while Show axes is enabled."
      : (xyzMode ? "" : "Galaxy background is only available in XYZ mode.");
  }
}

function createGalaxyTexture() {
  const texture = new THREE.TextureLoader().load(
    xuvAppUrl("static/images/eso0932a.jpg"),
    (loadedTexture) => {
      loadedTexture.needsUpdate = true;
    },
  );
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = true;
  return texture;
}

function populateAxisSelects() {
  for (const id of ["xuv-axis-1", "xuv-axis-2", "xuv-axis-3"]) {
    xuvEl[id].innerHTML = xuvAxes.map((axis) => `<option value="${axis.value}">${axis.label}</option>`).join("");
  }
}

function readXyzuvwUrlState() {
  const params = new URLSearchParams(window.location.search);
  const axes = String(params.get("axes") || "xyz").toLowerCase().split("").filter((axis) => xuvAxes.some((row) => row.value === axis));
  const cleanAxes = axes.length === 3 && new Set(axes).size === 3 ? axes : xuvDefaultAxes;
  xuvEl["xuv-axis-1"].value = cleanAxes[0];
  xuvEl["xuv-axis-2"].value = cleanAxes[1];
  xuvEl["xuv-axis-3"].value = cleanAxes[2];
  xuvState.selectedAids = parseCsv(params.get("asso") || params.get("moca_aid") || params.get("aid"), xuvDefaultAids);
  xuvState.selectedMtids = parseCsv(params.get("mtid"), xuvDefaultMtids);
  xuvState.selectedOids = parseOids(params.get("oid") || params.get("moca_oid"));
  xuvEl["xuv-oid-input"].value = xuvState.selectedOids.join(",");
  const hasCheckboxParam = params.has("checkbox");
  const checkbox = new Set(parseCsv(params.get("checkbox"), []));
  for (const key of ["models", "errors", "assmem", "hover", "likely", "asscen"]) {
    if (asBool(params.get(key))) checkbox.add(key);
  }
  if (!hasCheckboxParam && !params.has("models")) checkbox.add("models");
  if (!hasCheckboxParam && !params.has("likely")) checkbox.add("likely");
  if (!hasCheckboxParam && !params.has("assmem")) checkbox.add("assmem");
  xuvEl["xuv-models"].checked = checkbox.has("models");
  xuvEl["xuv-errors"].checked = checkbox.has("errors");
  xuvEl["xuv-assmem"].checked = checkbox.has("assmem");
  xuvEl["xuv-hover"].checked = checkbox.has("hover");
  xuvEl["xuv-show-axes"].checked = params.has("showaxes") ? asBool(params.get("showaxes")) : false;
  xuvEl["xuv-galaxy-bg"].checked = params.has("galaxy") ? asBool(params.get("galaxy")) : true;
  xuvEl["xuv-likely"].checked = checkbox.has("likely");
  xuvEl["xuv-asscen"].checked = checkbox.has("asscen");
  syncGalaxyBackgroundControl();
}

function bindXyzuvwControls() {
  for (const id of ["xuv-axis-1", "xuv-axis-2", "xuv-axis-3"]) {
    xuvEl[id].addEventListener("change", () => {
      syncGalaxyBackgroundControl();
      loadXyzuvwData();
    });
  }
  xuvEl["xuv-aids-default"].addEventListener("click", () => {
    xuvState.selectedAids = [...xuvDefaultAids];
    xuvState.hiddenAids.clear();
    renderAssociationList();
    loadXyzuvwData();
  });
  xuvEl["xuv-aids-clear"].addEventListener("click", () => {
    xuvState.selectedAids = [];
    xuvState.hiddenAids.clear();
    renderAssociationList();
    renderEmptyXyzuvw("Select at least one association");
    updateXyzuvwUrl();
  });
  xuvEl["xuv-aid-search"].addEventListener("input", () => {
    const value = xuvEl["xuv-aid-search"].value.trim();
    clearTimeout(xuvState.aidSearchTimer);
    xuvState.aidSearchTimer = setTimeout(() => searchXyzuvwAssociations(value), 180);
  });
  xuvEl["xuv-aid-search"].addEventListener("focus", () => {
    const value = xuvEl["xuv-aid-search"].value.trim();
    if (value) searchXyzuvwAssociations(value);
  });
  xuvEl["xuv-oid-input"].addEventListener("change", () => {
    xuvState.selectedOids = parseOids(xuvEl["xuv-oid-input"].value);
    renderOidChips();
    loadXyzuvwData();
  });
  xuvEl["xuv-object-search"].addEventListener("input", () => {
    const value = xuvEl["xuv-object-search"].value.trim();
    clearTimeout(xuvState.searchTimer);
    xuvState.searchTimer = setTimeout(() => searchXyzuvwObjects(value), 250);
  });
  xuvEl["xuv-object-search"].addEventListener("focus", () => {
    const value = xuvEl["xuv-object-search"].value.trim();
    if (value) searchXyzuvwObjects(value);
  });
  document.addEventListener("click", (event) => {
    if (!xuvEl["xuv-object-results"].contains(event.target) && event.target !== xuvEl["xuv-object-search"]) {
      xuvEl["xuv-object-results"].hidden = true;
    }
    if (!xuvEl["xuv-aid-results"].contains(event.target) && event.target !== xuvEl["xuv-aid-search"]) {
      xuvEl["xuv-aid-results"].hidden = true;
    }
  });
  xuvEl["xuv-bsmdid"].addEventListener("change", loadXyzuvwData);
  for (const id of ["xuv-models", "xuv-errors", "xuv-likely", "xuv-asscen"]) {
    xuvEl[id].addEventListener("change", loadXyzuvwData);
  }
  for (const id of ["xuv-assmem", "xuv-hover", "xuv-show-axes", "xuv-galaxy-bg"]) {
    xuvEl[id].addEventListener("change", () => {
      if (id === "xuv-show-axes") syncGalaxyBackgroundControl();
      renderXyzuvwThree();
      updateXyzuvwUrl();
    });
  }
  xuvEl["xuv-load"].addEventListener("click", loadXyzuvwData);
  xuvEl["xuv-export-csv"].addEventListener("click", () => exportXyzuvw("csv"));
  xuvEl["xuv-export-tsv"].addEventListener("click", () => exportXyzuvw("tsv"));
  xuvEl["xuv-export-fits"].addEventListener("click", () => exportXyzuvw("fits"));
  xuvEl["xuv-export-votable"].addEventListener("click", () => exportXyzuvw("votable"));
  xuvEl["xuv-open-report"].addEventListener("click", openSelectedXyzuvwReport);
  xuvEl["xuv-recenter-sun"].addEventListener("click", recenterXyzuvwCameraOnSun);
  xuvEl["xuv-clear-cache-bottom"].addEventListener("click", clearXyzuvwCache);
}

async function loadXyzuvwOptions() {
  setXyzuvwStatus("Loading options", "loading");
  const params = apiParams();
  params.set("asso", xuvState.selectedAids.join(","));
  const payload = await fetchJsonUrl(xuvAppUrl(`api/xyzuvw/options?${params.toString()}`));
  if (!payload.ok) {
    setXyzuvwStatus(payload.error || "Could not load options", "error");
    xuvState.options = { associations: [], mtids: [], versions: [{ value: "latest", label: "Latest available" }] };
  } else {
    xuvState.options = {
      associations: payload.associations || [],
      mtids: payload.mtids || [],
      versions: payload.versions || [{ value: "latest", label: "Latest available" }],
    };
  }
  renderAssociationList();
  renderMtidList();
  renderBsmdidOptions();
}

async function loadXyzuvwData() {
  syncGalaxyBackgroundControl();
  if (!xuvState.selectedAids.length || !xuvState.selectedMtids.length) {
    renderEmptyXyzuvw("Select at least one association and membership type");
    return;
  }
  if (xuvThreeDualMode) {
    const token = ++xuvState.loadToken;
    setXyzuvwLoading(true);
    setXyzuvwStatus("Loading XYZ/UVW data", "loading");
    const fetches = xuvThreeDualPanelDefs.map(async (panel) => {
      const params = buildXyzuvwParams(panel.axes);
      const payload = await fetchJsonUrl(xuvAppUrl(`api/xyzuvw/data?${params.toString()}`));
      return [panel.key, payload];
    });
    const entries = await Promise.all(fetches);
    if (token !== xuvState.loadToken) return;
    xuvState.panelPayloads = Object.fromEntries(entries);
    const failed = entries.find(([, payload]) => !payload.ok);
    if (failed) {
      const [, payload] = failed;
      xuvState.payload = payload;
      setXyzuvwStatus(payload.error || "Could not load XYZ/UVW data", "error");
      renderEmptyXyzuvw(payload.error || "Could not load XYZ/UVW data");
      return;
    }
    xuvState.payload = xuvState.panelPayloads.xyz || entries[0]?.[1];
    xuvState.cValue = Number(xuvState.payload?.meta?.c_value || 8);
    xuvState.selectedRows = [];
    renderXyzuvwThree(true);
    updateXyzuvwUrl();
    return;
  }
  if (new Set(selectedAxes()).size !== 3) {
    renderEmptyXyzuvw("Please select distinct axes");
    return;
  }
  const token = ++xuvState.loadToken;
  setXyzuvwLoading(true);
  setXyzuvwStatus("Loading XYZUVW data", "loading");
  const params = buildXyzuvwParams();
  const payload = await fetchJsonUrl(xuvAppUrl(`api/xyzuvw/data?${params.toString()}`));
  if (token !== xuvState.loadToken) return;
  if (!payload.ok) {
    xuvState.payload = payload;
    setXyzuvwStatus(payload.error || "Could not load XYZUVW data", "error");
    renderEmptyXyzuvw(payload.error || "Could not load XYZUVW data");
    return;
  }
  xuvState.payload = payload;
  xuvState.cValue = Number(payload.meta?.c_value || 8);
  xuvState.selectedRows = [];
  renderXyzuvwThree(true);
  updateXyzuvwUrl();
}

function renderXyzuvwThree(forceCamera = false) {
  if (xuvThreeDualMode) {
    renderXyzuvwThreeDual(forceCamera);
    return;
  }
  if (!xuvState.payload || !xuvState.payload.ok) {
    renderEmptyXyzuvw("No data loaded");
    return;
  }
  const result = renderXyzuvwThreePanel(xuvState.payload, forceCamera);
  const rows = result?.rows || [];
  const overlayRows = result?.overlayRows || [];

  const cacheText = xuvState.payload.cache?.hit ? " from cache" : "";
  const truncatedText = xuvState.payload.meta?.truncated ? `, truncated at ${Number(xuvState.payload.meta.max_objects || 0).toLocaleString()}` : "";
  setXyzuvwStatus(`${rows.length.toLocaleString()} members loaded${cacheText}`, "");
  xuvEl["xuv-summary"].textContent = `${rows.length.toLocaleString()} members, ${(xuvState.payload.models || []).length.toLocaleString()} model components, ${overlayRows.length.toLocaleString()} highlighted objects${truncatedText}`;
  renderXyzuvwHint();
  setXyzuvwExportDisabled(xuvState.displayedRows.length === 0);
  renderXyzuvwTable();
  setXyzuvwLoading(false);
}

function renderXyzuvwThreeDual(forceCamera = false) {
  const entries = xuvThreeDualPanelDefs.map((panel) => [panel, xuvState.panelPayloads?.[panel.key]]);
  if (entries.some(([, payload]) => !payload?.ok)) {
    renderEmptyXyzuvw("No data loaded");
    return;
  }
  setXyzuvwLoading(true);
  const results = [];
  entries.forEach(([panelDef, payload]) => {
    const panel = xuvState.threePanels.find((candidate) => candidate.key === panelDef.key);
    if (!panel) return;
    const result = withThreePanel(panel, () => renderXyzuvwThreePanel(payload, forceCamera));
    if (result) results.push({ ...result, key: panelDef.key, payload });
  });
  const xyzResult = results.find((result) => result.key === "xyz") || results[0];
  xuvState.payload = xyzResult?.payload || null;
  xuvState.displayedRows = xyzResult?.displayedRows || [];
  const xyzRows = results.find((result) => result.key === "xyz")?.rows?.length || 0;
  const uvwRows = results.find((result) => result.key === "uvw")?.rows?.length || 0;
  const modelCount = Math.max(...results.map((result) => (result.payload?.models || []).length), 0);
  const overlayCount = Math.max(...results.map((result) => result.overlayRows?.length || 0), 0);
  const cacheHit = results.some((result) => result.payload?.cache?.hit);
  const truncated = results.some((result) => result.payload?.meta?.truncated);
  const cacheText = cacheHit ? " from cache" : "";
  const truncatedText = truncated ? ", truncated" : "";
  setXyzuvwStatus(`${xyzRows.toLocaleString()} XYZ / ${uvwRows.toLocaleString()} UVW members loaded${cacheText}`, "");
  xuvEl["xuv-summary"].textContent = `${xyzRows.toLocaleString()} XYZ members, ${uvwRows.toLocaleString()} UVW members, ${modelCount.toLocaleString()} model components, ${overlayCount.toLocaleString()} highlighted objects${truncatedText}`;
  renderXyzuvwHint();
  setXyzuvwExportDisabled(!xuvState.displayedRows.length);
  renderXyzuvwTable();
  setXyzuvwLoading(false);
}

function renderXyzuvwThreePanel(payload, forceCamera = false) {
  xuvState.payload = payload;
  const axes = selectedAxes();
  const showAxes = xuvEl["xuv-show-axes"].checked;
  clearThreeData();
  const rows = preparedMemberRows(axes);
  const overlayRows = preparedOverlayRows(axes);
  const displayedRows = [...rows, ...overlayRows];
  xuvState.displayedRows = displayedRows;
  xuvState.three.displayedRows = displayedRows;
  const colormap = associationColors(xuvState.selectedAids);
  const modelSurfaces = xuvEl["xuv-models"].checked ? (xuvState.payload.modelSurfaces || xuvState.payload.model_surfaces || []) : [];
  const bounds = sceneBounds(axes, displayedRows, modelSurfaces);
  const referenceContext = cleanReferenceContext(axes, displayedRows, modelSurfaces);
  xuvState.selectionMarkerRadius = Math.max(4, Math.min(14, bounds.radius * 0.012));

  xuvState.three.scene.background = new THREE.Color(showAxes ? "#eeeeef" : xuvCleanSceneBackground);
  ensureGalaxyBackground();
  addReferenceObjects(axes, showAxes, referenceContext, bounds);
  if (xuvEl["xuv-models"].checked) addModelObjects(modelSurfaces, colormap);
  if (xuvEl["xuv-errors"].checked) addErrorObjects(axes, rows, colormap);
  addMemberObjects(rows, colormap);
  addOverlayObjects(overlayRows);
  addAssociationCenterLabels(rows, colormap, bounds, showAxes);
  if (xuvEl["xuv-asscen"].checked) addAllAssociationLabels(axes, colormap, rows, showAxes);
  renderSelectedMarker();
  ensureCameraTargetMarker(bounds);
  updateCameraTargetMarker();
  renderThreeLegend(colormap, rows, modelSurfaces);
  fitThreeCamera(bounds, forceCamera);
  updateGalaxyBackground();
  applyLegendVisibility();
  return { rows, overlayRows, displayedRows, modelSurfaces, bounds };
}

function clearThreeData() {
  const { dataGroup, selectedGroup } = xuvState.three;
  dataGroup.children.slice().forEach((child) => {
    dataGroup.remove(child);
    disposeThreeObject(child);
  });
  selectedGroup.children.slice().forEach((child) => {
    selectedGroup.remove(child);
    disposeThreeObject(child);
  });
  xuvState.three.pickObjects = [];
}

function disposeThreeObject(object) {
  object.traverse((child) => {
    if (child.geometry) child.geometry.dispose();
    if (child.material) {
      const materials = Array.isArray(child.material) ? child.material : [child.material];
      materials.forEach((material) => material.dispose());
    }
  });
}

function addMemberObjects(rows, colormap) {
  const rowsByAid = new Map();
  rows.forEach((row) => {
    const aid = String(row.moca_aid || "Unassigned");
    if (!rowsByAid.has(aid)) rowsByAid.set(aid, []);
    rowsByAid.get(aid).push(row);
  });
  const orderedAids = [
    ...xuvState.selectedAids.filter((aid) => rowsByAid.has(String(aid))),
    ...[...rowsByAid.keys()].filter((aid) => !xuvState.selectedAids.includes(aid)),
  ];
  orderedAids.forEach((aid) => {
    const aidRows = rowsByAid.get(String(aid)) || [];
    if (!aidRows.length) return;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(aidRows.length * 3);
    aidRows.forEach((row, index) => {
      positions[index * 3] = Number(row.plot0);
      positions[index * 3 + 1] = Number(row.plot1);
      positions[index * 3 + 2] = Number(row.plot2);
    });
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({
      color: colormap[aid] || "#777777",
      size: xuvMemberPointSize,
      sizeAttenuation: false,
      map: xuvState.three.pointTexture,
      alphaTest: 0.28,
      transparent: true,
      opacity: xuvDataPointOpacity,
      depthWrite: false,
    });
    const points = new THREE.Points(geometry, material);
    points.userData = { aid, kind: "members", rows: aidRows };
    xuvState.three.dataGroup.add(points);
    xuvState.three.pickObjects.push(points);
  });
}

function addOverlayObjects(rows) {
  rows.forEach((row) => {
    if (row.rvLine) {
      const points = row.rvLine.x.map((value, index) => new THREE.Vector3(value, row.rvLine.y[index], row.rvLine.z[index]));
      const line = lineFromPoints(points, "#f8f8f8", 2.5, 0.9);
      line.userData = { aid: row.moca_aid || "Highlighted", kind: "highlight-line", row };
      xuvState.three.dataGroup.add(line);
      return;
    }
    const geometry = new THREE.SphereGeometry(xuvOverlayPointRadius, 18, 12);
    const material = new THREE.MeshBasicMaterial({
      color: "#050505",
      transparent: true,
      opacity: xuvDataPointOpacity,
      depthWrite: false,
    });
    const sphere = new THREE.Mesh(geometry, material);
    sphere.position.set(row.plot0, row.plot1, row.plot2);
    sphere.userData = { aid: row.moca_aid || "Highlighted", kind: "highlight", row };
    xuvState.three.dataGroup.add(sphere);
  });
}

function addModelObjects(surfaces, colormap) {
  (surfaces || []).forEach((surface) => {
    const x = surface.x || [];
    const y = surface.y || [];
    const z = surface.z || [];
    const count = Math.min(x.length, y.length, z.length);
    if (!count) return;
    const positions = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      positions[index * 3] = Number(x[index]);
      positions[index * 3 + 1] = Number(y[index]);
      positions[index * 3 + 2] = Number(z[index]);
    }
    const indices = [];
    const i = surface.i || [];
    const j = surface.j || [];
    const k = surface.k || [];
    const triCount = Math.min(i.length, j.length, k.length);
    for (let index = 0; index < triCount; index += 1) indices.push(Number(i[index]), Number(j[index]), Number(k[index]));
    if (!indices.length) return;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const aid = String(surface.moca_aid || "model");
    const material = new THREE.MeshLambertMaterial({
      color: colormap[aid] || "#888888",
      transparent: true,
      opacity: Math.max(0.04, Math.min(0.34, Number(surface.opacity || 0.16) * 1.1)),
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData = { aid, kind: "model" };
    xuvState.three.dataGroup.add(mesh);
  });
}

function addErrorObjects(axes, rows, colormap) {
  const byAid = new Map();
  const sourceRows = xuvState.selectedRows.length
    ? rows.filter((row) => xuvState.selectedRows.some((selected) => Number(selected.moca_oid) === Number(row.moca_oid)))
    : rows.slice(0, 1200);
  sourceRows.forEach((row) => {
    const segments = covarianceSegments(row, axes);
    if (!segments) return;
    const aid = String(row.moca_aid || "Unassigned");
    if (!byAid.has(aid)) byAid.set(aid, []);
    segments.forEach((segment) => {
      byAid.get(aid).push(new THREE.Vector3(...segment[0]), new THREE.Vector3(...segment[1]));
    });
  });
  byAid.forEach((points, aid) => {
    const line = lineSegmentsFromPoints(points, colormap[aid] || "#777777", 1.4, 0.32);
    line.userData = { aid, kind: "errors" };
    xuvState.three.dataGroup.add(line);
  });
}

function addReferenceObjects(axes, showAxes, context, bounds) {
  addSunObject(axes, showAxes, bounds, context);
  if (showAxes) {
    addAxisFrame(axes, bounds);
    return;
  }
  if (!context.plane) return;
  addReferencePlane(axes, context);
  addReferenceAxisGuides(axes, context);
  context.minorRadii.forEach((radius) => addReferenceCircle(axes, context.plane, radius, false));
  context.majorRadii.forEach((radius) => addReferenceCircle(axes, context.plane, radius, true));
}

function addSunObject(axes, showAxes, bounds, context) {
  const color = showAxes ? "#111111" : xuvCleanCircleColor;
  const extent = Math.max(6, Math.min(18, (context?.radius || bounds?.radius || 500) * 0.018));
  const tubeRadius = Math.max(0.35, Math.min(1.5, extent * xuvSunCrossRadius * 0.12));
  axes.forEach((_axis, axisIndex) => {
    const start = new THREE.Vector3(0, 0, 0);
    const end = new THREE.Vector3(0, 0, 0);
    start.setComponent(axisIndex, -extent);
    end.setComponent(axisIndex, extent);
    const crossArm = tubeFromPoints([start, end], color, tubeRadius, 1, false, 8);
    crossArm.userData = { kind: "reference" };
    xuvState.three.dataGroup.add(crossArm);
  });
  addTextLabel("Sun", new THREE.Vector3(0, 0, 0), {
    color,
    className: showAxes ? "xuv-three-label is-axis" : "xuv-three-label is-reference",
    yOffset: -12,
  });
}

function addAxisFrame(axes, bounds) {
  const ranges = bounds.ranges;
  const tubeRadius = Math.max(0.7, Math.min(4.2, (bounds.radius || 500) * 0.004));
  axes.forEach((axis, axisIndex) => {
    const range = normalizedAxisRange(ranges[axisIndex], bounds.radius || 500);
    const start = new THREE.Vector3(0, 0, 0);
    const end = new THREE.Vector3(0, 0, 0);
    start.setComponent(axisIndex, range[0]);
    end.setComponent(axisIndex, range[1]);
    const line = tubeFromPoints([start, end], "#111111", tubeRadius, 0.95, false, 8);
    line.userData = { kind: "axis" };
    xuvState.three.dataGroup.add(line);
    addAxisTicks(ranges, axisIndex, tubeRadius, bounds);
    const labelPosition = end.clone();
    labelPosition.setComponent(axisIndex, range[1] + (range[1] - range[0]) * 0.04);
    addTextLabel(`${axis.toUpperCase()} (${axisUnit(axis)})`, labelPosition, {
      color: "#111111",
      className: "xuv-three-label is-axis",
    });
  });
}

function addAxisTicks(ranges, axisIndex, axisTubeRadius, bounds) {
  const range = normalizedAxisRange(ranges[axisIndex], bounds.radius || 500);
  const span = range[1] - range[0];
  if (!finite(span) || span <= 0) return;
  const step = niceAxisTickStep(span / 5);
  const ticks = axisTickValues(range, step);
  if (!ticks.length) return;
  const spans = ranges
    .map((candidate) => {
      const cleanRange = normalizedAxisRange(candidate, bounds.radius || 500);
      return cleanRange[1] - cleanRange[0];
    })
    .filter((value) => finite(value) && value > 0);
  const smallestSpan = spans.length ? Math.min(...spans) : span;
  const tickLength = Math.max(2, Math.min(36, smallestSpan * 0.026));
  const perpendicularIndex = axisIndex === 0 ? 1 : 0;
  const tickRadius = Math.max(0.28, axisTubeRadius * 0.55);
  ticks.forEach((tick) => {
    const center = new THREE.Vector3(0, 0, 0);
    center.setComponent(axisIndex, tick);
    const start = center.clone();
    const end = center.clone();
    start.setComponent(perpendicularIndex, -tickLength * 0.5);
    end.setComponent(perpendicularIndex, tickLength * 0.5);
    const mark = tubeFromPoints([start, end], "#111111", tickRadius, 0.95, false, 6);
    mark.userData = { kind: "axis-tick" };
    xuvState.three.dataGroup.add(mark);
    const labelPosition = center.clone();
    labelPosition.setComponent(perpendicularIndex, tickLength * 1.45);
    addTextLabel(formatAxisTickLabel(tick, step), labelPosition, {
      color: "#111111",
      className: "xuv-three-label is-axis is-axis-tick",
    });
  });
}

function normalizedAxisRange(range, fallbackRadius) {
  const lower = finite(range?.[0]) ? Number(range[0]) : -fallbackRadius;
  const upper = finite(range?.[1]) ? Number(range[1]) : fallbackRadius;
  if (upper >= lower) return [lower, upper];
  return [upper, lower];
}

function niceAxisTickStep(rawStep) {
  if (!finite(rawStep) || rawStep <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const scaled = rawStep / magnitude;
  if (scaled <= 1) return magnitude;
  if (scaled <= 2) return 2 * magnitude;
  if (scaled <= 5) return 5 * magnitude;
  return 10 * magnitude;
}

function axisTickValues(range, step) {
  const start = Math.ceil(range[0] / step) * step;
  const stop = Math.floor(range[1] / step) * step;
  const values = [];
  for (let value = start; value <= stop + step * 1e-6; value += step) {
    const cleanValue = Math.abs(value) < step * 1e-8 ? 0 : value;
    values.push(cleanValue);
  }
  return values.slice(0, 9);
}

function formatAxisTickLabel(value, step) {
  const cleanValue = Math.abs(value) < step * 1e-8 ? 0 : value;
  if (cleanValue === 0) return "0";
  const decimals = step >= 1 ? 0 : Math.min(3, Math.ceil(-Math.log10(step)));
  const label = formatNumber(cleanValue, decimals);
  return label.includes(".") ? label.replace(/\.?0+$/, "") : label;
}

function addReferencePlane(axes, context) {
  const { plane, radius } = context;
  const segments = 144;
  const positions = [0, 0, 0];
  for (let index = 0; index < segments; index += 1) {
    const point = referenceVector(axes, plane, radius, 2 * Math.PI * index / segments);
    positions.push(point.x, point.y, point.z);
  }
  const indices = [];
  for (let index = 0; index < segments; index += 1) {
    indices.push(0, index + 1, index === segments - 1 ? 1 : index + 2);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  const material = new THREE.MeshBasicMaterial({
    color: xuvCleanPlaneColor,
    transparent: true,
    opacity: 0.12,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData = { kind: "reference-plane" };
  xuvState.three.dataGroup.add(mesh);
}

function addReferenceAxisGuides(axes, context) {
  const { plane, radius } = context;
  const tubeRadius = Math.max(0.75, Math.min(4.2, radius * 0.004));
  const guides = plane.axes.map((axis, index) => ({ axis, label: plane.labels[index] }));
  const verticalAxis = axes.find((axis) => !plane.axes.includes(axis));
  if (verticalAxis) guides.push({ axis: verticalAxis, label: verticalAxis.toUpperCase(), isVertical: true });
  guides.forEach((guide) => {
    const start = new THREE.Vector3(0, 0, 0);
    const end = new THREE.Vector3(0, 0, 0);
    const plotIndex = axes.indexOf(guide.axis);
    if (plotIndex < 0) return;
    end.setComponent(plotIndex, radius * (guide.isVertical ? xuvVerticalReferenceAxisScale : 1));
    const line = tubeFromPoints([start, end], xuvCleanReferenceColor, tubeRadius, 0.22, false, 10);
    line.userData = { kind: "reference-axis" };
    xuvState.three.dataGroup.add(line);
    addTextLabel(guide.label, end, {
      color: "rgba(0, 168, 255, .72)",
      className: "xuv-three-label is-reference",
    });
  });
}

function addReferenceCircle(axes, plane, radius, major) {
  const plotRadius = referencePlanePlotRadius(plane, radius);
  const tubeRadius = Math.max(0.45, Math.min(3.4, plotRadius * (major ? 0.0042 : 0.0024)));
  const segments = 192;
  const points = [];
  for (let index = 0; index < segments; index += 1) {
    points.push(referenceVector(axes, plane, plotRadius, 2 * Math.PI * index / segments));
  }
  const line = tubeFromPoints(points, xuvCleanReferenceColor, tubeRadius, major ? 0.24 : 0.08, true, 8);
  line.userData = { kind: "reference-circle" };
  xuvState.three.dataGroup.add(line);
  if (major) {
    const labelPosition = referenceVector(axes, plane, plotRadius, -Math.PI / 2);
    addTextLabel(`${radius} ${plane.unit}`, labelPosition, {
      color: "rgba(0, 168, 255, .72)",
      className: "xuv-three-label is-radius",
      yOffset: 12,
    });
  }
}

function addAssociationCenterLabels(rows, colormap, bounds, showAxes) {
  const rowsByAid = new Map();
  rows.forEach((row) => {
    const aid = String(row.moca_aid || "Unassigned");
    if (!rowsByAid.has(aid)) rowsByAid.set(aid, []);
    rowsByAid.get(aid).push(row);
  });
  const verticalOffset = Math.max(0, bounds.ranges[2][1] - bounds.ranges[2][0]) * 0.035;
  rowsByAid.forEach((aidRows, aid) => {
    const center = [0, 1, 2].map((index) => robustMedian(aidRows.map((row) => row[`plot${index}`]).filter(finite).map(Number)));
    if (center.some((value) => !finite(value))) return;
    const position = new THREE.Vector3(center[0], center[1], center[2] + verticalOffset);
    addTextLabel(aid, position, {
      color: colormap[aid] || "#ffffff",
      className: showAxes ? "xuv-three-label is-association is-axis" : "xuv-three-label is-association",
      aid,
    });
  });
}

function addAllAssociationLabels(axes, colormap, rows, showAxes) {
  const memberAids = new Set(rows.map((row) => String(row.moca_aid || "Unassigned")));
  (xuvState.payload.labels || []).forEach((row) => {
    const aid = String(row.moca_aid || "");
    if (!aid || memberAids.has(aid)) return;
    const values = axes.map((axis) => Number(row[axis]));
    if (values.some((value) => !finite(value))) return;
    addTextLabel(aid, new THREE.Vector3(values[0], values[1], values[2]), {
      color: colormap[aid] || "#ffffff",
      className: showAxes ? "xuv-three-label is-association is-axis is-muted" : "xuv-three-label is-association is-muted",
      aid,
    });
  });
}

function addTextLabel(text, position, options = {}) {
  const div = document.createElement("div");
  div.className = options.className || "xuv-three-label";
  div.textContent = text;
  if (options.color) div.style.color = options.color;
  if (options.yOffset) div.style.transform = `translate(-50%, ${Number(options.yOffset)}px)`;
  const label = new CSS2DObject(div);
  label.position.copy(position);
  label.userData = { aid: options.aid, kind: "label" };
  xuvState.three.dataGroup.add(label);
  return label;
}

function renderSelectedMarker() {
  const { selectedGroup } = xuvState.three;
  selectedGroup.children.slice().forEach((child) => {
    selectedGroup.remove(child);
    disposeThreeObject(child);
  });
  if (xuvState.selectedRows.length !== 1) return;
  const axes = selectedAxes();
  const row = withPlotValues(xuvState.selectedRows[0], axes, xuvEl["xuv-assmem"].checked, xuvState.selectedRows[0]?.kind);
  if (![row.plot0, row.plot1, row.plot2].every(finite)) return;
  const radius = xuvState.selectionMarkerRadius * 0.7;
  const geometry = new THREE.TorusGeometry(radius, Math.max(0.28, radius * 0.075), 8, 72);
  const material = new THREE.MeshBasicMaterial({
    color: xuvSelectionColor,
    transparent: true,
    opacity: 0.3,
    depthTest: false,
  });
  const rotations = [
    [0, 0, 0],
    [Math.PI / 2, 0, 0],
    [0, Math.PI / 2, 0],
  ];
  rotations.forEach((rotation) => {
    const ring = new THREE.Mesh(
      geometry.clone(),
      material.clone(),
    );
    ring.rotation.set(rotation[0], rotation[1], rotation[2]);
    ring.position.set(row.plot0, row.plot1, row.plot2);
    ring.renderOrder = 1000;
    selectedGroup.add(ring);
  });
}

function renderSelectedMarkers() {
  forEachThreePanel(() => renderSelectedMarker());
}

function ensureCameraTargetMarker(bounds) {
  const { cameraTargetGroup } = xuvState.three;
  if (!cameraTargetGroup) return;
  cameraTargetGroup.children.slice().forEach((child) => {
    cameraTargetGroup.remove(child);
    disposeThreeObject(child);
  });
  const armLength = 1;
  const tubeRadius = 0.075;
  const axes = [
    [new THREE.Vector3(-armLength, 0, 0), new THREE.Vector3(armLength, 0, 0)],
    [new THREE.Vector3(0, -armLength, 0), new THREE.Vector3(0, armLength, 0)],
    [new THREE.Vector3(0, 0, -armLength), new THREE.Vector3(0, 0, armLength)],
  ];
  axes.forEach((points) => {
    const arm = tubeFromPoints(points, "#e12626", tubeRadius, 1, false, 8);
    arm.userData = { kind: "camera-target-marker" };
    cameraTargetGroup.add(arm);
  });
  const label = createThreeTextLabel("Camera", new THREE.Vector3(0, 0, 1.55), {
    color: "#e12626",
    className: "xuv-three-label is-camera-target",
  });
  cameraTargetGroup.add(label);
  const scale = Math.max(4, Math.min(18, (bounds?.radius || 500) * 0.018));
  cameraTargetGroup.scale.setScalar(scale);
  updateCameraTargetMarker();
}

function updateCameraTargetMarker() {
  const { controls, cameraTargetGroup } = xuvState.three;
  if (!controls || !cameraTargetGroup) return;
  const target = controls.target;
  const awayFromSun = target.lengthSq() > 1e-8;
  cameraTargetGroup.visible = true;
  cameraTargetGroup.traverse((child) => {
    if (child !== cameraTargetGroup) child.visible = awayFromSun;
    if (child.element) child.element.style.display = awayFromSun ? "" : "none";
  });
  if (awayFromSun) cameraTargetGroup.position.copy(target);
}

function createThreeTextLabel(text, position, options = {}) {
  const div = document.createElement("div");
  div.className = options.className || "xuv-three-label";
  div.textContent = text;
  if (options.color) div.style.color = options.color;
  if (options.yOffset) div.style.transform = `translate(-50%, ${Number(options.yOffset)}px)`;
  const label = new CSS2DObject(div);
  label.position.copy(position);
  label.userData = { aid: options.aid, kind: "label" };
  return label;
}

function tubeFromPoints(points, color, radius, opacity = 1, closed = false, radialSegments = 8) {
  const cleanPoints = points.filter((point) => point && finite(point.x) && finite(point.y) && finite(point.z));
  if (cleanPoints.length < 2) return new THREE.Group();
  const curve = cleanPoints.length === 2
    ? new THREE.LineCurve3(cleanPoints[0], cleanPoints[1])
    : new THREE.CatmullRomCurve3(cleanPoints, closed, "catmullrom", 0.5);
  const geometry = new THREE.TubeGeometry(
    curve,
    Math.max(1, closed ? cleanPoints.length : cleanPoints.length - 1),
    radius,
    radialSegments,
    closed,
  );
  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: opacity < 1,
    opacity,
    depthWrite: opacity >= 1,
  });
  return new THREE.Mesh(geometry, material);
}

function lineFromPoints(points, color, width = 1, opacity = 1) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({
    color,
    linewidth: width,
    transparent: opacity < 1,
    opacity,
  });
  return new THREE.Line(geometry, material);
}

function lineSegmentsFromPoints(points, color, width = 1, opacity = 1) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({
    color,
    linewidth: width,
    transparent: opacity < 1,
    opacity,
  });
  return new THREE.LineSegments(geometry, material);
}

function renderThreeLegend(colormap, rows, surfaces) {
  const legendEl = xuvState.three.legendEl || xuvEl["xuv-three-legend"];
  if (!legendEl) return;
  const counts = new Map();
  rows.forEach((row) => {
    const aid = String(row.moca_aid || "Unassigned");
    counts.set(aid, (counts.get(aid) || 0) + 1);
  });
  (surfaces || []).forEach((surface) => {
    const aid = String(surface.moca_aid || "model");
    if (!counts.has(aid)) counts.set(aid, 0);
  });
  const aids = [
    ...xuvState.selectedAids.filter((aid) => counts.has(aid)),
    ...[...counts.keys()].filter((aid) => !xuvState.selectedAids.includes(aid)),
  ];
  legendEl.innerHTML = aids.map((aid) => {
    const hidden = xuvState.hiddenAids.has(aid);
    const count = counts.get(aid) || 0;
    return `
      <button type="button" class="${hidden ? "is-muted" : ""}" data-aid="${escapeHtml(aid)}" title="Toggle ${escapeHtml(aid)}">
        <span class="xuv-three-swatch" style="--swatch:${escapeHtml(colormap[aid] || "#777777")}"></span>
        <span>${escapeHtml(aid)}</span>
        <span class="xuv-three-count">${count.toLocaleString()}</span>
      </button>
    `;
  }).join("");
  legendEl.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const aid = button.dataset.aid;
      if (!aid) return;
      if (xuvState.hiddenAids.has(aid)) xuvState.hiddenAids.delete(aid);
      else xuvState.hiddenAids.add(aid);
      applyLegendVisibility();
    });
  });
}

function applyLegendVisibility() {
  const hidden = xuvState.hiddenAids;
  forEachThreePanel((panel) => {
    panel.dataGroup.traverse((object) => {
      const aid = object.userData?.aid;
      if (!aid) return;
      object.visible = !hidden.has(String(aid));
    });
    if (panel.legendEl) {
      panel.legendEl.querySelectorAll("button[data-aid]").forEach((button) => {
        button.classList.toggle("is-muted", hidden.has(String(button.dataset.aid)));
      });
    }
  });
}

function fitThreeCamera(bounds, force = false) {
  const axesKey = selectedAxes().join("");
  const panel = xuvState.three;
  if (!force && panel.cameraInitialized && panel.lastCameraAxes === axesKey) return;
  const { camera, controls } = panel;
  const center = bounds.center;
  const radius = Math.max(20, bounds.radius || 500);
  const distance = Math.max(500, radius * 1.65);
  const direction = new THREE.Vector3(1.25, -1.55, 0.9).normalize();
  camera.up.set(0, 0, 1);
  camera.position.copy(center.clone().add(direction.multiplyScalar(distance)));
  camera.near = Math.max(0.1, distance / 10000);
  camera.far = Math.max(20000, distance * 12);
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
  panel.cameraInitialized = true;
  panel.lastCameraAxes = axesKey;
}

function onThreePointerUp(event) {
  if (!xuvState.pointerDown) return;
  const pointerDown = xuvState.pointerDown;
  const dx = event.clientX - xuvState.pointerDown.x;
  const dy = event.clientY - xuvState.pointerDown.y;
  xuvState.pointerDown = null;
  if (pointerDown.button !== 0 || event.button !== 0) return;
  if (Math.hypot(dx, dy) > 4) return;
  const hit = pickThreePoint(event);
  if (!hit) {
    xuvState.selectedRows = [];
  } else {
    const rows = hit.object.userData?.rows || [];
    const row = rows[hit.index];
    xuvState.selectedRows = row ? [row] : [];
  }
  renderSelectedMarkers();
  renderXyzuvwTable();
}

function onThreePointerMove(event) {
  if (!xuvEl["xuv-hover"].checked) {
    hideThreeTooltip();
    return;
  }
  const hit = pickThreePoint(event);
  if (!hit) {
    hideThreeTooltip();
    return;
  }
  const row = (hit.object.userData?.rows || [])[hit.index];
  if (!row) {
    hideThreeTooltip();
    return;
  }
  const tooltip = xuvState.three.tooltipEl || xuvEl["xuv-three-tooltip"];
  if (!tooltip) return;
  tooltip.innerHTML = hoverTextForRow(row);
  tooltip.hidden = false;
  const rect = (xuvState.three.plotEl || xuvEl["xuv-plot"]).getBoundingClientRect();
  tooltip.style.left = `${Math.min(rect.width - 280, Math.max(10, event.clientX - rect.left + 14))}px`;
  tooltip.style.top = `${Math.min(rect.height - 150, Math.max(10, event.clientY - rect.top + 14))}px`;
}

function hideThreeTooltip() {
  const tooltip = xuvState.three?.tooltipEl || xuvEl["xuv-three-tooltip"];
  if (tooltip) tooltip.hidden = true;
}

function pickThreePoint(event) {
  const { camera, raycaster, pointer, pickObjects } = xuvState.three;
  const rect = xuvState.three.renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const intersections = raycaster.intersectObjects(pickObjects.filter((object) => object.visible), false);
  return intersections.length ? intersections[0] : null;
}

function createPointTexture() {
  const size = 160;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  const center = size / 2;
  const gradient = ctx.createRadialGradient(center, center, 1, center, center, center - 2);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.58, "rgba(255,255,255,1)");
  gradient.addColorStop(0.76, "rgba(255,255,255,.82)");
  gradient.addColorStop(0.9, "rgba(255,255,255,.24)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = true;
  return texture;
}

function renderXyzuvwHint() {
  const lines = [
    xuvEl["xuv-assmem"].checked
      ? "Assumed-membership coordinates are used when available."
      : "Empirical XYZUVW coordinates are used.",
  ];
  if (xuvEl["xuv-models"].checked) {
    lines.push("BANYAN Σ models are displayed as 68%, 95% and 99% probability isodensity surfaces.");
  }
  if (isGalaxyBackgroundActive()) {
    lines.push("Galaxy background image: ESO/S. Brunier.");
  }
  lines.push("Legend toggles are handled in Three.js without resetting the camera.");
  xuvEl["xuv-hint-text"].innerHTML = lines.map(escapeHtml).join("<br>");
}

function isGalaxyBackgroundActive() {
  return Boolean(xuvEl["xuv-galaxy-bg"]?.checked) && isXyzMode() && !xuvEl["xuv-show-axes"]?.checked;
}

function recenterXyzuvwCameraOnSun() {
  if (xuvThreeDualMode) {
    forEachThreePanel(() => recenterCurrentThreePanelOnSun());
    return;
  }
  recenterCurrentThreePanelOnSun();
}

function recenterCurrentThreePanelOnSun() {
  const { camera, controls } = xuvState.three;
  if (!camera || !controls) return;
  const sun = new THREE.Vector3(0, 0, 0);
  let offset = camera.position.clone().sub(controls.target);
  if (offset.lengthSq() <= 0) {
    offset = new THREE.Vector3(1.25, -1.55, 0.9).normalize().multiplyScalar(500);
  }
  const dampingEnabled = controls.enableDamping;
  controls.enableDamping = false;
  controls.update();
  controls.target.copy(sun);
  camera.position.copy(sun).add(offset);
  controls.update();
  controls.enableDamping = dampingEnabled;
  updateGalaxyBackground();
  updateCameraTargetMarker();
}

function preparedMemberRows(axes, payload = xuvState.payload) {
  const assume = xuvEl["xuv-assmem"].checked;
  return plottedRowsForAxes(payload?.members || [], axes, assume, "member");
}

function preparedOverlayRows(axes, payload = xuvState.payload) {
  return (payload?.objects || []).map((row) => {
    const out = withPlotValues(row, axes, false, "highlight");
    out.rvLine = axes.some((axis, index) => !finite(out[`plot${index}`]) && ["u", "v", "w"].includes(axis))
      ? rvLineForObject(row, axes)
      : null;
    return out;
  }).filter((row) => axes.every((_axis, index) => finite(row[`plot${index}`])) || row.rvLine);
}

function plottedRowsForAxes(rows, axes, assumeMembership, kind = null) {
  return (rows || []).map((row) => withPlotValues(row, axes, assumeMembership, kind))
    .filter((row) => axes.every((_axis, index) => finite(row[`plot${index}`])));
}

function withPlotValues(row, axes, assumeMembership, kind = null) {
  const out = {
    ...row,
    kind: kind || row.kind,
    label: row.label || row.designation || `oid${row.moca_oid}`,
    plotAxesKey: axes.join(""),
  };
  axes.forEach((axis, index) => {
    out[`plot${index}`] = rowValue(row, axis, assumeMembership);
  });
  return out;
}

function rowValue(row, axis, assumeMembership) {
  const optKey = `${axis}_opt`;
  if (assumeMembership && finite(row[optKey])) return Number(row[optKey]);
  return finite(row[axis]) ? Number(row[axis]) : null;
}

function tableAxisValue(row, axis, plotIndex) {
  if (row.plotAxesKey === selectedAxes().join("") && finite(row[`plot${plotIndex}`])) {
    return Number(row[`plot${plotIndex}`]);
  }
  return rowValue(row, axis, xuvEl["xuv-assmem"].checked);
}

function cleanReferenceContext(axes, rows, modelSurfaces) {
  const plane = cleanReferencePlaneSpec(axes);
  if (!plane) return { plane: null, radius: 0, majorRadii: [], minorRadii: [] };
  const radius = cleanReferenceRadius(axes, rows, modelSurfaces, plane);
  return {
    plane,
    radius,
    majorRadii: plane.majorRadii.filter((value) => referencePlanePlotRadius(plane, value) <= radius + 1e-9),
    minorRadii: cleanMinorReferenceRadii(plane, radius),
  };
}

function cleanReferencePlaneSpec(axes) {
  if (axes.includes("x") && axes.includes("y")) {
    return {
      kind: "spatial",
      axes: ["x", "y"],
      labels: ["X", "Y"],
      unit: "pc",
      radiusScale: 1,
      majorRadii: xuvCleanReferenceRadii,
      fallbackRadius: Math.max(...xuvCleanReferenceRadii),
    };
  }
  if (axes.includes("u") && axes.includes("v")) {
    return {
      kind: "velocity",
      axes: ["u", "v"],
      labels: ["U", "V"],
      unit: "km/s",
      radiusScale: velocityReferenceScale(),
      majorRadii: xuvCleanVelocityReferenceRadii,
      fallbackRadius: Math.max(...xuvCleanVelocityReferenceRadii) * velocityReferenceScale(),
    };
  }
  return null;
}

function cleanReferenceRadius(axes, rows, modelSurfaces, plane) {
  let radius = 0;
  rows.forEach((row) => {
    const values = plane.axes.map((axis) => {
      const plotIndex = axes.indexOf(axis);
      if (plotIndex >= 0) return row[`plot${plotIndex}`];
      return row[axis];
    }).filter(finite).map(Number);
    if (values.length) radius = Math.max(radius, Math.hypot(...values));
  });
  (modelSurfaces || []).forEach((surface) => {
    const arrays = [surface.x || [], surface.y || [], surface.z || []];
    const length = Math.min(arrays[0].length, arrays[1].length, arrays[2].length);
    for (let index = 0; index < length; index += 1) {
      const values = [];
      axes.forEach((axis, axisIndex) => {
        if (plane.axes.includes(axis) && finite(arrays[axisIndex][index])) values.push(Number(arrays[axisIndex][index]));
      });
      if (values.length) radius = Math.max(radius, Math.hypot(...values));
    }
  });
  if (!finite(radius) || radius <= 0) return plane.fallbackRadius;
  const minRadius = referencePlanePlotRadius(plane, plane.majorRadii[0] || 10);
  if (plane.kind === "velocity") {
    const scale = referencePlanePlotRadius(plane, 1);
    const velocityRadius = Math.ceil((radius / scale) / 10) * 10;
    return Math.max(minRadius, velocityRadius * scale);
  }
  if (radius <= 100) return Math.max(minRadius, Math.ceil(radius / 10) * 10);
  return Math.max(minRadius, Math.ceil(radius / 100) * 100);
}

function cleanMinorReferenceRadii(plane, radius) {
  if (!plane) return [];
  if (plane.kind === "velocity") return cleanVelocityMinorReferenceRadii(plane, radius);
  const majorRadii = new Set(plane.majorRadii);
  const maxMinor = Math.floor((Number(radius) + 1e-9) / 100) * 100;
  const radii = [];
  for (let value = 200; value <= maxMinor; value += 100) {
    if (!majorRadii.has(value)) radii.push(value);
  }
  return radii;
}

function cleanVelocityMinorReferenceRadii(plane, radius) {
  const majorRadii = new Set(plane.majorRadii);
  const maxVelocity = Math.floor((Number(radius) / referencePlanePlotRadius(plane, 1) + 1e-9) / 10) * 10;
  const radii = [];
  for (let value = 10; value <= maxVelocity; value += 10) {
    if (!majorRadii.has(value)) radii.push(value);
  }
  return radii;
}

function referencePlanePlotRadius(plane, radius) {
  const scale = finite(plane?.radiusScale) ? Number(plane.radiusScale) : 1;
  return Number(radius) * scale;
}

function velocityReferenceScale() {
  const scale = Number(xuvState.cValue);
  return finite(scale) && scale > 0 ? Number(scale) : 1;
}

function referenceVector(axes, plane, radius, angle) {
  const vector = new THREE.Vector3(0, 0, 0);
  const firstIndex = axes.indexOf(plane.axes[0]);
  const secondIndex = axes.indexOf(plane.axes[1]);
  if (firstIndex >= 0) vector.setComponent(firstIndex, radius * Math.cos(angle));
  if (secondIndex >= 0) vector.setComponent(secondIndex, radius * Math.sin(angle));
  return vector;
}

function sceneBounds(axes, rows, modelSurfaces) {
  const values = [[], [], []];
  rows.forEach((row) => {
    [0, 1, 2].forEach((index) => {
      if (finite(row[`plot${index}`])) values[index].push(Number(row[`plot${index}`]));
    });
  });
  (modelSurfaces || []).forEach((surface) => {
    [surface.x || [], surface.y || [], surface.z || []].forEach((array, axisIndex) => {
      array.forEach((value) => {
        if (finite(value)) values[axisIndex].push(Number(value));
      });
    });
  });
  if (values.every((axisValues) => !axisValues.length)) {
    return {
      ranges: [[-500, 500], [-500, 500], [-500, 500]],
      center: new THREE.Vector3(0, 0, 0),
      radius: 500,
    };
  }
  const medians = values.map((axisValues) => axisValues.length ? robustMedian(axisValues) : 0);
  const centerArray = medians.some((value) => Math.abs(value) > 2000 / 3) ? medians : [0, 0, 0];
  let extent = 500;
  values.forEach((axisValues, index) => {
    axisValues.forEach((value) => {
      extent = Math.max(extent, Math.abs(value - centerArray[index]));
    });
  });
  extent = Math.min(Math.max(extent * 1.08, 20), 2200);
  const ranges = centerArray.map((value) => [value - extent, value + extent]);
  return {
    ranges,
    center: new THREE.Vector3(centerArray[0], centerArray[1], centerArray[2]),
    radius: extent,
  };
}

function covarianceSegments(row, axes) {
  const matrix = axes.map((axis1) => axes.map((axis2) => scaledCovariance(row, axis1, axis2)));
  if (matrix.flat().some((value) => !finite(value))) return null;
  const eig = jacobiEigen3(matrix);
  if (!eig) return null;
  const center = [row.plot0, row.plot1, row.plot2].map(Number);
  const segments = [];
  for (let component = 0; component < 3; component += 1) {
    const sigma = Math.sqrt(Math.max(0, eig.values[component]));
    if (!finite(sigma) || sigma <= 0) continue;
    const vector = [eig.vectors[0][component], eig.vectors[1][component], eig.vectors[2][component]];
    segments.push([
      center.map((value, axisIndex) => value - vector[axisIndex] * sigma),
      center.map((value, axisIndex) => value + vector[axisIndex] * sigma),
    ]);
  }
  return segments;
}

function scaledCovariance(row, axis1, axis2) {
  return scaleCovariance(axis1, axis2, row[covarianceKey(axis1, axis2)]);
}

function scaleCovariance(axis1, axis2, value) {
  if (!finite(value)) return 0;
  const kin1 = ["u", "v", "w"].includes(axis1);
  const kin2 = ["u", "v", "w"].includes(axis2);
  if (kin1 && kin2) return Number(value) * xuvState.cValue * xuvState.cValue;
  if (kin1 || kin2) return Number(value) * xuvState.cValue;
  return Number(value);
}

function covarianceKey(axis1, axis2) {
  const order = ["x", "y", "z", "u", "v", "w"];
  const sorted = [axis1, axis2].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  return `${sorted[0]}${sorted[1]}_covar`;
}

function jacobiEigen3(input) {
  const a = input.map((row) => row.map(Number));
  const v = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let iter = 0; iter < 50; iter += 1) {
    let p = 0;
    let q = 1;
    let max = Math.abs(a[0][1]);
    for (const pair of [[0, 2], [1, 2]]) {
      const value = Math.abs(a[pair[0]][pair[1]]);
      if (value > max) {
        max = value;
        p = pair[0];
        q = pair[1];
      }
    }
    if (max < 1e-10) break;
    const theta = 0.5 * Math.atan2(2 * a[p][q], a[q][q] - a[p][p]);
    const c = Math.cos(theta);
    const s = Math.sin(theta);
    const app = c * c * a[p][p] - 2 * s * c * a[p][q] + s * s * a[q][q];
    const aqq = s * s * a[p][p] + 2 * s * c * a[p][q] + c * c * a[q][q];
    a[p][q] = 0;
    a[q][p] = 0;
    a[p][p] = app;
    a[q][q] = aqq;
    for (let r = 0; r < 3; r += 1) {
      if (r === p || r === q) continue;
      const arp = a[r][p];
      const arq = a[r][q];
      a[r][p] = c * arp - s * arq;
      a[p][r] = a[r][p];
      a[r][q] = s * arp + c * arq;
      a[q][r] = a[r][q];
    }
    for (let r = 0; r < 3; r += 1) {
      const vrp = v[r][p];
      const vrq = v[r][q];
      v[r][p] = c * vrp - s * vrq;
      v[r][q] = s * vrp + c * vrq;
    }
  }
  const values = [a[0][0], a[1][1], a[2][2]];
  if (values.some((value) => !finite(value))) return null;
  return { values, vectors: v };
}

function rvLineForObject(row, axes) {
  if (!finite(row.ra) || !finite(row.dec) || !finite(row.pmra_masyr) || !finite(row.pmdec_masyr) || !finite(row.distance_pc)) return null;
  const uvw = equatorialUVW(Number(row.ra), Number(row.dec), Number(row.pmra_masyr), Number(row.pmdec_masyr), xuvRvRange, Number(row.distance_pc));
  const output = { x: [], y: [], z: [] };
  xuvRvRange.forEach((_rv, index) => {
    const point = axes.map((axis) => {
      if (axis === "u") return uvw.u[index] * xuvState.cValue;
      if (axis === "v") return uvw.v[index] * xuvState.cValue;
      if (axis === "w") return uvw.w[index] * xuvState.cValue;
      return rowValue(row, axis, false);
    });
    if (point.every(finite)) {
      output.x.push(point[0]);
      output.y.push(point[1]);
      output.z.push(point[2]);
    }
  });
  return output.x.length ? output : null;
}

function equatorialUVW(ra, dec, pmra, pmdec, rvArray, dist) {
  const cosRa = Math.cos(rad(ra));
  const cosDec = Math.cos(rad(dec));
  const sinRa = Math.sin(rad(ra));
  const sinDec = Math.sin(rad(dec));
  const t1 = xuvTgal[0][0] * cosRa * cosDec + xuvTgal[0][1] * sinRa * cosDec + xuvTgal[0][2] * sinDec;
  const t2 = -xuvTgal[0][0] * sinRa + xuvTgal[0][1] * cosRa;
  const t3 = -xuvTgal[0][0] * cosRa * sinDec - xuvTgal[0][1] * sinRa * sinDec + xuvTgal[0][2] * cosDec;
  const t4 = xuvTgal[1][0] * cosRa * cosDec + xuvTgal[1][1] * sinRa * cosDec + xuvTgal[1][2] * sinDec;
  const t5 = -xuvTgal[1][0] * sinRa + xuvTgal[1][1] * cosRa;
  const t6 = -xuvTgal[1][0] * cosRa * sinDec - xuvTgal[1][1] * sinRa * sinDec + xuvTgal[1][2] * cosDec;
  const t7 = xuvTgal[2][0] * cosRa * cosDec + xuvTgal[2][1] * sinRa * cosDec + xuvTgal[2][2] * sinDec;
  const t8 = -xuvTgal[2][0] * sinRa + xuvTgal[2][1] * cosRa;
  const t9 = -xuvTgal[2][0] * cosRa * sinDec - xuvTgal[2][1] * sinRa * sinDec + xuvTgal[2][2] * cosDec;
  const reducedDist = xuvKappa * dist;
  return {
    u: rvArray.map((rv) => t1 * rv + t2 * pmra * reducedDist + t3 * pmdec * reducedDist),
    v: rvArray.map((rv) => t4 * rv + t5 * pmra * reducedDist + t6 * pmdec * reducedDist),
    w: rvArray.map((rv) => t7 * rv + t8 * pmra * reducedDist + t9 * pmdec * reducedDist),
  };
}

function renderAssociationList() {
  const selected = xuvState.selectedAids;
  if (!selected.length) {
    xuvEl["xuv-selected-aids"].innerHTML = `<div class="designation-result-note">No associations selected</div>`;
    return;
  }
  xuvEl["xuv-selected-aids"].innerHTML = selected.map((aid) => `
    <span class="designation-chip association-chip">
      <span title="${escapeHtml(associationLabel(aid))}">${escapeHtml(associationLabel(aid))}</span>
      <button type="button" data-aid="${escapeHtml(aid)}" aria-label="Remove ${escapeHtml(aid)}">x</button>
    </span>
  `).join("");
  xuvEl["xuv-selected-aids"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const aid = button.dataset.aid;
      xuvState.selectedAids = xuvState.selectedAids.filter((value) => value !== aid);
      xuvState.hiddenAids.delete(aid);
      renderAssociationList();
      if (xuvState.selectedAids.length) loadXyzuvwData();
      else {
        renderEmptyXyzuvw("Select at least one association");
        updateXyzuvwUrl();
      }
    });
  });
}

async function searchXyzuvwAssociations(query) {
  query = String(query || "").trim();
  if (!query) {
    xuvEl["xuv-aid-results"].hidden = true;
    return;
  }
  const params = apiParams();
  params.set("q", query);
  const payload = await fetchJsonUrl(xuvAppUrl(`api/xyzuvw/associations/search?${params.toString()}`));
  if (!payload.ok) {
    xuvEl["xuv-aid-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
    showAssociationPopup();
    return;
  }
  const results = (payload.options || []).filter((result) => result.value);
  if (!results.length) {
    xuvEl["xuv-aid-results"].innerHTML = `<div class="designation-result-note">No associations found</div>`;
    showAssociationPopup();
    return;
  }
  results.forEach(upsertAssociationOption);
  xuvEl["xuv-aid-results"].innerHTML = results.map((result, index) => {
    const value = String(result.value);
    const selected = xuvState.selectedAids.includes(value);
    const label = result.label || value;
    return `
      <button class="designation-result association-result" type="button" data-index="${index}" ${selected ? "disabled" : ""}>
        <span>${selected ? "Selected: " : ""}${escapeHtml(label)}</span>
      </button>
    `;
  }).join("");
  xuvEl["xuv-aid-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const result = results[Number(button.dataset.index)];
      const aid = String(result.value || "").trim();
      if (aid && !xuvState.selectedAids.includes(aid)) {
        upsertAssociationOption(result);
        xuvState.selectedAids.push(aid);
        renderAssociationList();
        loadXyzuvwData();
      }
      xuvEl["xuv-aid-search"].value = "";
      xuvEl["xuv-aid-results"].hidden = true;
    });
  });
  showAssociationPopup();
}

function showAssociationPopup() {
  positionPopup(xuvEl["xuv-aid-search"], xuvEl["xuv-aid-results"], 620);
  xuvEl["xuv-aid-results"].hidden = false;
}

function associationLabel(aid) {
  const option = xuvState.options.associations.find((row) => String(row.value) === String(aid));
  return option?.label || String(aid);
}

function upsertAssociationOption(option) {
  if (!option?.value) return;
  const value = String(option.value);
  const label = option.label || value;
  const existing = xuvState.options.associations.find((row) => String(row.value) === value);
  if (existing) existing.label = label;
  else xuvState.options.associations.push({ value, label });
}

function renderMtidList() {
  const options = xuvState.options.mtids.length
    ? xuvState.options.mtids
    : xuvDefaultMtids.map((mtid) => ({ value: mtid, label: mtid }));
  xuvEl["xuv-mtid-list"].innerHTML = options.map((option) => `
    <label class="checkline xyzuvw-check">
      <input type="checkbox" value="${escapeHtml(option.value)}" ${xuvState.selectedMtids.includes(option.value) ? "checked" : ""}>
      <span title="${escapeHtml(option.description || option.label || option.value)}">${escapeHtml(option.label || option.value)}</span>
    </label>
  `).join("");
  xuvEl["xuv-mtid-list"].querySelectorAll("input").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked && !xuvState.selectedMtids.includes(input.value)) xuvState.selectedMtids.push(input.value);
      if (!input.checked) xuvState.selectedMtids = xuvState.selectedMtids.filter((mtid) => mtid !== input.value);
      loadXyzuvwData();
    });
  });
}

function renderBsmdidOptions() {
  const versions = xuvState.options.versions.length ? xuvState.options.versions : [{ value: "latest", label: "Latest available" }];
  const params = new URLSearchParams(window.location.search);
  const selected = params.get("bsmdid") || "latest";
  xuvEl["xuv-bsmdid"].innerHTML = versions.map((version) => `<option value="${escapeHtml(version.value)}">${escapeHtml(version.label)}</option>`).join("");
  xuvEl["xuv-bsmdid"].value = versions.some((version) => String(version.value) === selected) ? selected : "latest";
}

async function searchXyzuvwObjects(query) {
  if (!query) {
    xuvEl["xuv-object-results"].hidden = true;
    return;
  }
  if (query.length < 2 && !/^\d+$/.test(query)) {
    xuvEl["xuv-object-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    showObjectPopup();
    return;
  }
  const params = apiParams();
  params.set("q", query);
  const payload = await fetchJsonUrl(xuvAppUrl(`api/xyzuvw/search?${params.toString()}`));
  if (!payload.ok) {
    xuvEl["xuv-object-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
    showObjectPopup();
    return;
  }
  const results = payload.options || [];
  if (!results.length) {
    xuvEl["xuv-object-results"].innerHTML = `<div class="designation-result-note">No objects found</div>`;
    showObjectPopup();
    return;
  }
  xuvEl["xuv-object-results"].innerHTML = results.map((result, index) => (
    `<button class="designation-result" type="button" data-index="${index}"><span>${escapeHtml(result.label || `oid${result.value}`)}</span></button>`
  )).join("");
  xuvEl["xuv-object-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const result = results[Number(button.dataset.index)];
      const oid = parseInteger(result.value ?? result.moca_oid);
      if (oid !== null && !xuvState.selectedOids.includes(oid)) {
        xuvState.selectedOids.push(oid);
        syncOidInput();
        renderOidChips();
        loadXyzuvwData();
      }
      xuvEl["xuv-object-search"].value = "";
      xuvEl["xuv-object-results"].hidden = true;
    });
  });
  showObjectPopup();
}

function showObjectPopup() {
  positionPopup(xuvEl["xuv-object-search"], xuvEl["xuv-object-results"], 780);
  xuvEl["xuv-object-results"].hidden = false;
}

function positionPopup(input, popup, maxWidth) {
  if (!input || !popup) return;
  const rect = input.getBoundingClientRect();
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - 340));
  const available = Math.max(300, window.innerWidth - left - 16);
  const width = Math.min(maxWidth, available);
  popup.style.position = "fixed";
  popup.style.left = `${left}px`;
  popup.style.top = `${rect.bottom + 4}px`;
  popup.style.width = `${Math.max(rect.width, width)}px`;
}

function renderOidChips() {
  if (!xuvState.selectedOids.length) {
    xuvEl["xuv-selected-oids"].innerHTML = "";
    return;
  }
  xuvEl["xuv-selected-oids"].innerHTML = xuvState.selectedOids.map((oid) => `
    <span class="designation-chip">
      <span>oid${oid}</span>
      <button type="button" data-oid="${oid}" aria-label="Remove oid ${oid}">x</button>
    </span>
  `).join("");
  xuvEl["xuv-selected-oids"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const oid = Number(button.dataset.oid);
      xuvState.selectedOids = xuvState.selectedOids.filter((value) => value !== oid);
      syncOidInput();
      renderOidChips();
      loadXyzuvwData();
    });
  });
}

function renderXyzuvwTable() {
  const rows = xuvState.selectedRows.length ? xuvState.selectedRows : xuvState.displayedRows.slice(0, 500);
  xuvEl["xuv-table-title"].textContent = xuvState.selectedRows.length ? `${xuvState.selectedRows.length} selected objects` : "Displayed objects";
  xuvEl["xuv-table-subtitle"].textContent = xuvState.selectedRows.length ? "Click Open selected report for a single selected object." : "Showing the first 500 displayed rows.";
  xuvEl["xuv-open-report"].disabled = xuvState.selectedRows.length !== 1 || !mocaReportUrl(xuvState.selectedRows[0]?.moca_oid);
  if (!rows.length) {
    xuvEl["xuv-table"].innerHTML = `<div class="selection-table">No objects to display.</div>`;
    return;
  }
  const axes = selectedAxes();
  const columns = ["moca_oid", "designation", "moca_aid", "moca_mtid", "spt", ...axes, "ya_prob", "report"];
  const tableRows = rows.map((row) => {
    const reportUrl = mocaReportUrl(row.moca_oid);
    const out = {
      moca_oid: normalizedMocaOid(row.moca_oid),
      designation: row.designation || "",
      moca_aid: row.moca_aid || "",
      moca_mtid: row.moca_mtid || "",
      spt: row.spt || "",
      ya_prob: finite(row.ya_prob) ? formatNumber(row.ya_prob, 1) : "",
      report: reportUrl ? `<a class="report-link" href="${reportUrl}" target="_blank" rel="noopener">Report</a>` : "",
    };
    axes.forEach((axis, index) => {
      out[axis] = formatNumber(tableAxisValue(row, axis, index), 2);
    });
    return out;
  });
  xuvEl["xuv-table"].innerHTML = tableHtml(columns, tableRows, { htmlColumns: new Set(["report"]) });
}

function renderEmptyXyzuvw(message) {
  forEachThreePanel((panel) => {
    clearThreeData();
    if (panel.galaxyMesh) panel.galaxyMesh.visible = false;
    if (panel.legendEl) panel.legendEl.innerHTML = "";
  });
  xuvEl["xuv-summary"].textContent = message;
  xuvEl["xuv-table"].innerHTML = "";
  if (xuvEl["xuv-three-legend"]) xuvEl["xuv-three-legend"].innerHTML = "";
  setXyzuvwExportDisabled(true);
  setXyzuvwLoading(false);
}

function hoverTextForRow(row) {
  return [
    `<b>${escapeHtml(row.designation || `oid${row.moca_oid}`)}</b>`,
    `MOCA OID: ${escapeHtml(row.moca_oid)}`,
    `Association: ${escapeHtml(row.moca_aid || "")}`,
    `Membership: ${escapeHtml(row.moca_mtid || "")}`,
    `SPT: ${escapeHtml(row.spt || "")}`,
    `RUWE: ${finite(row.dr3_ruwe) ? formatNumber(row.dr3_ruwe, 2) : "N/A"}`,
    `YA prob: ${finite(row.ya_prob) ? `${formatNumber(row.ya_prob, 1)}%` : "N/A"}`,
  ].join("<br>");
}

function selectedAxes() {
  if (xuvState.three?.axes) return xuvState.three.axes;
  if (xuvThreeDualMode) return xuvThreeDualPanelDefs[0].axes;
  return [xuvEl["xuv-axis-1"].value, xuvEl["xuv-axis-2"].value, xuvEl["xuv-axis-3"].value];
}

function isXyzMode(axes = selectedAxes()) {
  return axes.join("") === "xyz";
}

function axisUnit(axis) {
  return ["u", "v", "w"].includes(axis) ? "km/s" : "pc";
}

function associationColors(aids) {
  const out = {};
  aids.forEach((aid, index) => {
    out[aid] = xuvPalette[index % xuvPalette.length];
  });
  return out;
}

function buildXyzuvwParams(axes = selectedAxes()) {
  const params = apiParams();
  params.set("axes", axes.join(""));
  params.set("asso", xuvState.selectedAids.join(","));
  params.set("mtid", xuvState.selectedMtids.join(","));
  if (xuvState.selectedOids.length) params.set("oid", xuvState.selectedOids.join(","));
  params.set("bsmdid", xuvEl["xuv-bsmdid"].value || "latest");
  const checkbox = checkboxValues();
  if (checkbox.length) params.set("checkbox", checkbox.join(","));
  if (!xuvEl["xuv-likely"].checked) params.set("likely", "0");
  return params;
}

function checkboxValues() {
  const out = [];
  if (xuvEl["xuv-models"].checked) out.push("models");
  if (xuvEl["xuv-errors"].checked) out.push("errors");
  if (xuvEl["xuv-assmem"].checked) out.push("assmem");
  if (xuvEl["xuv-hover"].checked) out.push("hover");
  if (xuvEl["xuv-likely"].checked) out.push("likely");
  if (xuvEl["xuv-asscen"].checked) out.push("asscen");
  return out;
}

function updateXyzuvwUrl() {
  const params = new URLSearchParams(window.location.search);
  if (xuvThreeDualMode) params.delete("axes");
  else params.set("axes", selectedAxes().join(""));
  if (xuvState.selectedAids.length) params.set("asso", xuvState.selectedAids.join(","));
  else params.delete("asso");
  params.delete("moca_aid");
  params.delete("aid");
  if (xuvState.selectedMtids.length) params.set("mtid", xuvState.selectedMtids.join(","));
  else params.delete("mtid");
  if (xuvState.selectedOids.length) params.set("oid", xuvState.selectedOids.join(","));
  else params.delete("oid");
  params.delete("moca_oid");
  if (xuvEl["xuv-bsmdid"].value && xuvEl["xuv-bsmdid"].value !== "latest") params.set("bsmdid", xuvEl["xuv-bsmdid"].value);
  else params.delete("bsmdid");
  if (xuvEl["xuv-show-axes"].checked) params.set("showaxes", "1");
  else params.delete("showaxes");
  if (xuvEl["xuv-galaxy-bg"].checked) params.delete("galaxy");
  else params.set("galaxy", "0");
  const checkbox = checkboxValues();
  if (checkbox.length) params.set("checkbox", checkbox.join(","));
  else params.delete("checkbox");
  for (const key of ["models", "errors", "assmem", "hover", "asscen"]) params.delete(key);
  if (xuvEl["xuv-likely"].checked) params.delete("likely");
  else params.set("likely", "0");
  window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
}

const xyzuvwNumericExportColumns = new Set(["moca_oid", "x", "y", "z", "u", "v", "w", "ya_prob", "dr3_ruwe"]);

function exportXyzuvw(format) {
  const rows = xuvState.selectedRows.length ? xuvState.selectedRows : xuvState.displayedRows;
  if (!rows.length) return;
  const axes = selectedAxes();
  const columns = ["moca_oid", "designation", "moca_aid", "moca_mtid", "spt", ...axes, "ya_prob", "dr3_ruwe"];
  const exportRows = rows.map((row) => {
    const out = {
      moca_oid: normalizedMocaOid(row.moca_oid),
      designation: row.designation || "",
      moca_aid: row.moca_aid || "",
      moca_mtid: row.moca_mtid || "",
      spt: row.spt || "",
      ya_prob: row.ya_prob ?? "",
      dr3_ruwe: row.dr3_ruwe ?? "",
    };
    axes.forEach((axis, index) => {
      out[axis] = tableAxisValue(row, axis, index);
    });
    return out;
  });
  MocaExport.saveTable(format, {
    rows: exportRows,
    columns,
    numericColumns: xyzuvwNumericExportColumns,
    filenameBase: "mocadb_xyzuvw_three",
    tableName: "mocadb_xyzuvw_three",
    resourceName: "MOCAdb Three.js Spatial-Kinematic Explorer",
    extName: "XYZUVW",
  });
}

function setXyzuvwExportDisabled(disabled) {
  for (const id of ["xuv-export-csv", "xuv-export-tsv", "xuv-export-fits", "xuv-export-votable"]) {
    if (xuvEl[id]) xuvEl[id].disabled = disabled;
  }
}

function openSelectedXyzuvwReport() {
  if (xuvState.selectedRows.length !== 1) return;
  const url = mocaReportUrl(xuvState.selectedRows[0].moca_oid);
  if (url) window.open(url, "_blank", "noopener");
}

async function clearXyzuvwCache() {
  xuvEl["xuv-clear-cache-bottom"].disabled = true;
  xuvEl["xuv-clear-cache-status"].textContent = "Clearing...";
  xuvEl["xuv-clear-cache-status"].classList.remove("error");
  try {
    const payload = await postXyzuvwJson("api/xyzuvw/cache/clear", {});
    if (!payload.ok) throw new Error(payload.error || "Cache clear failed");
    const cleared = payload.cleared?.xyzuvw || 0;
    xuvEl["xuv-clear-cache-status"].textContent = `Cleared ${cleared} cached payload${cleared === 1 ? "" : "s"}.`;
    await loadXyzuvwOptions();
    await loadXyzuvwData();
  } catch (error) {
    xuvEl["xuv-clear-cache-status"].textContent = error.message;
    xuvEl["xuv-clear-cache-status"].classList.add("error");
  } finally {
    xuvEl["xuv-clear-cache-bottom"].disabled = false;
  }
}

function setXyzuvwStatus(text, mode = "") {
  xuvEl["xuv-status"].textContent = text;
  xuvEl["xuv-status"].className = `status${mode ? ` ${mode}` : ""}`;
}

function setXyzuvwLoading(loading) {
  xuvEl["xuv-plot-loader"].classList.toggle("is-visible", Boolean(loading));
}

function syncOidInput() {
  xuvEl["xuv-oid-input"].value = xuvState.selectedOids.join(",");
}

function parseCsv(raw, fallback = []) {
  if (!raw) return [...fallback];
  return String(raw).split(",").map((item) => item.trim()).filter(Boolean);
}

function parseOids(raw) {
  const seen = new Set();
  const out = [];
  String(raw || "").split(",").forEach((item) => {
    const oid = parseInteger(item.trim());
    if (oid !== null && !seen.has(oid)) {
      seen.add(oid);
      out.push(oid);
    }
  });
  return out;
}

function apiParams() {
  const source = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "user", "pwd", "dbase", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
  }
  return params;
}

async function fetchJsonUrl(url) {
  const response = await fetch(url);
  return response.json();
}

async function postXyzuvwJson(path, body) {
  const params = apiParams();
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(xuvAppUrl(`${path}${params.toString() ? `${separator}${params.toString()}` : ""}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return response.json();
}

function tableHtml(columns, rows, options = {}) {
  const htmlColumns = options.htmlColumns || new Set();
  return `
    <div class="selection-table">
      <table>
        <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>${columns.map((column) => `<td>${htmlColumns.has(column) ? (row[column] || "") : escapeHtml(row[column] ?? "")}</td>`).join("")}</tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function mocaReportUrl(oid) {
  const normalizedOid = normalizedMocaOid(oid);
  return normalizedOid ? `https://mocadb.ca/search/results?search-query=oid%28${encodeURIComponent(normalizedOid)}%29&search-type=star` : "";
}

function normalizedMocaOid(oid) {
  if (oid === null || oid === undefined) return "";
  const text = String(oid).trim();
  if (!text) return "";
  const number = Number(text);
  if (!Number.isFinite(number) || number <= 0) return "";
  return number.toFixed(0);
}

function robustMedian(values) {
  const clean = values.map(Number).filter(finite).sort((a, b) => a - b);
  if (!clean.length) return NaN;
  const mid = Math.floor(clean.length / 2);
  return clean.length % 2 ? clean[mid] : 0.5 * (clean[mid - 1] + clean[mid]);
}

function finite(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" && value.trim() === "") return false;
  return Number.isFinite(Number(value));
}

function parseInteger(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function asBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
}

function formatNumber(value, digits) {
  return finite(value) ? Number(value).toFixed(digits) : "";
}

function rad(value) {
  return Number(value) * Math.PI / 180;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
