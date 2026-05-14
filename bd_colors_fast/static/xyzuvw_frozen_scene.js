import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

const sceneData = window.MOCAVIZ_FROZEN_XYZ_SCENE || {};
const frozenState = {
  panels: [],
  hiddenAids: new Set(sceneData.hiddenAids || []),
  selectedOid: sceneData.selectedOid || "",
};

const cleanSceneBackground = "#08090c";
const cleanCircleColor = "#00a8ff";
const cleanReferenceColor = "#00a8ff";
const cleanPlaneColor = "#73c9ff";
const dataPointOpacity = 0.7;
const memberPointSize = 4.4;
const overlayPointRadius = 4.8;
const selectionColor = "#ffd21a";
const highlightMarkerColor = "#ffea00";
const verticalReferenceAxisScale = 0.25;

document.addEventListener("DOMContentLoaded", initFrozenScene);

function initFrozenScene() {
  frozenState.panels = (sceneData.panels || []).map(setupFrozenPanel).filter(Boolean);
  renderSummary();
  renderFrozenTable();
  document.getElementById("xuv-recenter-sun")?.addEventListener("click", recenterAllPanelsOnSun);
  requestAnimationFrame(animateFrozenScene);
}

function setupFrozenPanel(panelData) {
  const container = document.querySelector(`[data-frozen-canvas="${cssEscape(panelData.key)}"]`);
  const legendEl = document.querySelector(`[data-frozen-legend="${cssEscape(panelData.key)}"]`);
  const tooltipEl = document.querySelector(`[data-frozen-tooltip="${cssEscape(panelData.key)}"]`);
  const plotEl = document.querySelector(`[data-frozen-panel="${cssEscape(panelData.key)}"]`);
  if (!container) return null;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(panelData.showAxes ? "#eeeeef" : cleanSceneBackground);
  const camera = new THREE.PerspectiveCamera(Number(panelData.camera?.fov || 42), 1, 0.1, 20000);
  camera.up.fromArray(panelData.camera?.up || [0, 0, 1]);
  camera.position.fromArray(panelData.camera?.position || [265, -340, 250]);
  camera.near = Number(panelData.camera?.near || 0.1);
  camera.far = Number(panelData.camera?.far || 20000);
  camera.updateProjectionMatrix();

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
  controls.rotateSpeed = 0.48;
  controls.zoomSpeed = 1.08;
  controls.panSpeed = 0.62;
  controls.screenSpacePanning = true;
  controls.mouseButtons = {
    LEFT: THREE.MOUSE.ROTATE,
    MIDDLE: THREE.MOUSE.DOLLY,
    RIGHT: THREE.MOUSE.PAN,
  };
  if ("zoomToCursor" in controls) controls.zoomToCursor = false;
  controls.target.fromArray(panelData.camera?.target || panelData.bounds?.center || [0, 0, 0]);

  const ambient = new THREE.AmbientLight(0xffffff, 0.62);
  const key = new THREE.DirectionalLight(0xffffff, 1.25);
  key.position.set(0.7, -1.2, 1.4);
  scene.add(ambient, key);

  const dataGroup = new THREE.Group();
  const selectedGroup = new THREE.Group();
  scene.add(dataGroup, selectedGroup);

  const panel = {
    data: panelData,
    scene,
    camera,
    renderer,
    labelRenderer,
    controls,
    container,
    plotEl,
    legendEl,
    tooltipEl,
    dataGroup,
    selectedGroup,
    pickObjects: [],
    raycaster: new THREE.Raycaster(),
    pointer: new THREE.Vector2(),
    pointTexture: createPointTexture(),
    galaxyMesh: null,
  };
  panel.raycaster.params.Points.threshold = 5;

  addReferenceObjects(panel);
  if (panelData.galaxyActive) addGalaxyBackground(panel);
  addModelObjects(panel);
  addErrorObjects(panel);
  addMemberObjects(panel);
  addOverlayObjects(panel);
  addAssociationCenterLabels(panel);
  renderSelectedMarker(panel);
  renderLegend(panel);
  applyLegendVisibility();

  renderer.domElement.addEventListener("pointerup", (event) => onPointerUp(panel, event));
  renderer.domElement.addEventListener("pointermove", (event) => onPointerMove(panel, event));
  renderer.domElement.addEventListener("pointerleave", () => hideTooltip(panel));
  renderer.domElement.addEventListener("contextmenu", (event) => event.preventDefault());
  renderer.domElement.addEventListener("dblclick", () => {
    frozenState.selectedOid = "";
    renderSelectedMarkers();
    renderFrozenTable();
  });

  const resize = () => resizePanel(panel);
  new ResizeObserver(resize).observe(container);
  window.addEventListener("resize", debounce(resize, 100));
  resize();
  return panel;
}

function resizePanel(panel) {
  const rect = panel.container.getBoundingClientRect();
  const width = Math.max(1, Math.floor(rect.width));
  const height = Math.max(1, Math.floor(rect.height));
  panel.camera.aspect = width / height;
  panel.camera.updateProjectionMatrix();
  panel.renderer.setSize(width, height, false);
  panel.labelRenderer.setSize(width, height);
}

function animateFrozenScene() {
  requestAnimationFrame(animateFrozenScene);
  frozenState.panels.forEach((panel) => {
    panel.controls.update();
    updateGalaxyBackground(panel);
    panel.renderer.render(panel.scene, panel.camera);
    panel.labelRenderer.render(panel.scene, panel.camera);
  });
}

function addGalaxyBackground(panel) {
  const texture = new THREE.TextureLoader().load(sceneData.galaxyAsset || "static/images/eso0932a.jpg");
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = true;
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
  mesh.raycast = () => {};
  panel.scene.add(mesh);
  panel.galaxyMesh = mesh;
}

function updateGalaxyBackground(panel) {
  if (!panel.galaxyMesh) return;
  const viewDistance = panel.camera.position.distanceTo(panel.controls.target);
  const radius = Math.min(panel.camera.far * 0.42, Math.max(4500, viewDistance * 6));
  panel.galaxyMesh.position.copy(panel.camera.position);
  panel.galaxyMesh.rotation.set(Math.PI / 2, 0, 0);
  panel.galaxyMesh.scale.setScalar(radius);
}

function addReferenceObjects(panel) {
  addSunObject(panel);
  if (panel.data.showAxes) {
    addAxisFrame(panel);
    return;
  }
  const context = panel.data.referenceContext;
  if (!context?.plane) return;
  addReferencePlane(panel);
  addReferenceAxisGuides(panel);
  (context.minorRadii || []).forEach((radius) => addReferenceCircle(panel, radius, false));
  (context.majorRadii || []).forEach((radius) => addReferenceCircle(panel, radius, true));
}

function addSunObject(panel) {
  const context = panel.data.referenceContext;
  const bounds = panel.data.bounds;
  const color = panel.data.showAxes ? "#111111" : cleanCircleColor;
  const extent = Math.max(6, Math.min(18, (context?.radius || bounds?.radius || 500) * 0.018));
  const tubeRadius = Math.max(0.35, Math.min(1.5, extent * 0.9 * 0.12));
  (panel.data.axes || []).forEach((_axis, axisIndex) => {
    const start = new THREE.Vector3(0, 0, 0);
    const end = new THREE.Vector3(0, 0, 0);
    start.setComponent(axisIndex, -extent);
    end.setComponent(axisIndex, extent);
    const arm = tubeFromPoints([start, end], color, tubeRadius, 1, false, 8);
    arm.userData = { kind: "reference" };
    panel.dataGroup.add(arm);
  });
  addTextLabel(panel, "Sun", new THREE.Vector3(0, 0, 0), {
    color,
    className: panel.data.showAxes ? "xuv-three-label is-axis" : "xuv-three-label is-reference",
    yOffset: -12,
  });
}

function addAxisFrame(panel) {
  const axes = panel.data.axes || [];
  const bounds = panel.data.bounds || {};
  const tubeRadius = Math.max(0.7, Math.min(4.2, (bounds.radius || 500) * 0.004));
  axes.forEach((axis, axisIndex) => {
    const range = normalizedAxisRange(bounds.ranges?.[axisIndex], bounds.radius || 500);
    const start = new THREE.Vector3(0, 0, 0);
    const end = new THREE.Vector3(0, 0, 0);
    start.setComponent(axisIndex, range[0]);
    end.setComponent(axisIndex, range[1]);
    const line = tubeFromPoints([start, end], "#111111", tubeRadius, 0.95, false, 8);
    line.userData = { kind: "axis" };
    panel.dataGroup.add(line);
    addAxisTicks(panel, axisIndex, tubeRadius);
    const labelPosition = end.clone();
    labelPosition.setComponent(axisIndex, range[1] + (range[1] - range[0]) * 0.04);
    addTextLabel(panel, `${axis.toUpperCase()} (${axisUnit(axis)})`, labelPosition, {
      color: "#111111",
      className: "xuv-three-label is-axis",
    });
  });
}

function addAxisTicks(panel, axisIndex, axisTubeRadius) {
  const bounds = panel.data.bounds || {};
  const ranges = bounds.ranges || [];
  const range = normalizedAxisRange(ranges[axisIndex], bounds.radius || 500);
  const span = range[1] - range[0];
  if (!finite(span) || span <= 0) return;
  const step = niceAxisTickStep(span / 5);
  const ticks = axisTickValues(range, step);
  const tickLength = Math.max(2, Math.min(36, span * 0.026));
  const perpendicularIndex = axisIndex === 0 ? 1 : 0;
  ticks.forEach((tick) => {
    const center = new THREE.Vector3(0, 0, 0);
    center.setComponent(axisIndex, tick);
    const start = center.clone();
    const end = center.clone();
    start.setComponent(perpendicularIndex, -tickLength * 0.5);
    end.setComponent(perpendicularIndex, tickLength * 0.5);
    panel.dataGroup.add(tubeFromPoints([start, end], "#111111", Math.max(0.28, axisTubeRadius * 0.55), 0.95, false, 6));
    const labelPosition = center.clone();
    labelPosition.setComponent(perpendicularIndex, tickLength * 1.45);
    addTextLabel(panel, formatAxisTickLabel(tick, step), labelPosition, {
      color: "#111111",
      className: "xuv-three-label is-axis is-axis-tick",
    });
  });
}

function addReferencePlane(panel) {
  const context = panel.data.referenceContext;
  const axes = panel.data.axes || [];
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
    color: cleanPlaneColor,
    transparent: true,
    opacity: 0.12,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData = { kind: "reference-plane" };
  panel.dataGroup.add(mesh);
}

function addReferenceAxisGuides(panel) {
  const axes = panel.data.axes || [];
  const { plane, radius } = panel.data.referenceContext;
  const tubeRadius = Math.max(0.75, Math.min(4.2, radius * 0.004));
  const guides = plane.axes.map((axis, index) => ({ axis, label: plane.labels[index] }));
  const verticalAxis = axes.find((axis) => !plane.axes.includes(axis));
  if (verticalAxis) guides.push({ axis: verticalAxis, label: verticalAxis.toUpperCase(), isVertical: true });
  guides.forEach((guide) => {
    const plotIndex = axes.indexOf(guide.axis);
    if (plotIndex < 0) return;
    const start = new THREE.Vector3(0, 0, 0);
    const end = new THREE.Vector3(0, 0, 0);
    end.setComponent(plotIndex, radius * (guide.isVertical ? verticalReferenceAxisScale : 1));
    const line = tubeFromPoints([start, end], cleanReferenceColor, tubeRadius, 0.22, false, 10);
    line.userData = { kind: "reference-axis" };
    panel.dataGroup.add(line);
    addTextLabel(panel, guide.label, end, {
      color: "rgba(0, 168, 255, .72)",
      className: "xuv-three-label is-reference",
    });
  });
}

function addReferenceCircle(panel, radius, major) {
  const axes = panel.data.axes || [];
  const plane = panel.data.referenceContext.plane;
  const plotRadius = referencePlanePlotRadius(plane, radius);
  const tubeRadius = Math.max(0.45, Math.min(3.4, plotRadius * (major ? 0.0042 : 0.0024)));
  const points = [];
  for (let index = 0; index < 192; index += 1) {
    points.push(referenceVector(axes, plane, plotRadius, 2 * Math.PI * index / 192));
  }
  const line = tubeFromPoints(points, cleanReferenceColor, tubeRadius, major ? 0.24 : 0.08, true, 8);
  line.userData = { kind: "reference-circle" };
  panel.dataGroup.add(line);
  if (major) {
    addTextLabel(panel, `${radius} ${plane.unit}`, referenceVector(axes, plane, plotRadius, -Math.PI / 2), {
      color: "rgba(0, 168, 255, .72)",
      className: "xuv-three-label is-radius",
      yOffset: 12,
    });
  }
}

function addMemberObjects(panel) {
  const rowsByAid = new Map();
  (panel.data.rows || []).forEach((row) => {
    const aid = String(row.moca_aid || "Unassigned");
    if (!rowsByAid.has(aid)) rowsByAid.set(aid, []);
    rowsByAid.get(aid).push(row);
  });
  rowsByAid.forEach((rows, aid) => {
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(rows.length * 3);
    rows.forEach((row, index) => {
      positions[index * 3] = Number(row.plot0);
      positions[index * 3 + 1] = Number(row.plot1);
      positions[index * 3 + 2] = Number(row.plot2);
    });
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({
      color: panel.data.colormap?.[aid] || "#777777",
      size: memberPointSize,
      sizeAttenuation: false,
      map: panel.pointTexture,
      alphaTest: 0.28,
      transparent: true,
      opacity: dataPointOpacity,
      depthWrite: false,
    });
    const points = new THREE.Points(geometry, material);
    points.userData = { aid, kind: "members", rows };
    panel.dataGroup.add(points);
    panel.pickObjects.push(points);
  });
}

function addOverlayObjects(panel) {
  (panel.data.overlayRows || []).forEach((row) => {
    if (row.rvLine) {
      const points = row.rvLine.x.map((value, index) => new THREE.Vector3(value, row.rvLine.y[index], row.rvLine.z[index]));
      const line = lineFromPoints(points, "#f8f8f8", 0.9);
      line.userData = { aid: row.moca_aid || "Highlighted", kind: "highlight-line", row };
      panel.dataGroup.add(line);
      return;
    }
    panel.dataGroup.add(highlightObjectMarker(row, Boolean(panel.data.showAxes)));
  });
}

function highlightObjectMarker(row, showAxes = false) {
  const marker = new THREE.Group();
  marker.position.set(row.plot0, row.plot1, row.plot2);
  marker.userData = { aid: row.moca_aid || "Highlighted", kind: "highlight", row };
  marker.renderOrder = 900;

  const color = showAxes ? "#000000" : highlightMarkerColor;
  const radius = overlayPointRadius * 1.35;
  const axisLength = radius * 5.2;
  const axisRadius = Math.max(0.56, radius * 0.12);
  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 24, 16),
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.96,
      depthTest: false,
      depthWrite: false,
    }),
  );
  sphere.renderOrder = 900;
  marker.add(sphere);

  const rotations = [
    [0, 0, Math.PI / 2],
    [0, 0, 0],
    [Math.PI / 2, 0, 0],
  ];
  rotations.forEach((rotation) => {
    const axis = new THREE.Mesh(
      new THREE.CylinderGeometry(axisRadius, axisRadius, axisLength, 16),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.98,
        depthTest: false,
        depthWrite: false,
      }),
    );
    axis.rotation.set(rotation[0], rotation[1], rotation[2]);
    axis.renderOrder = 901;
    marker.add(axis);
  });

  const designation = row.designation || row.label || (row.moca_oid ? `oid${row.moca_oid}` : "");
  if (designation) marker.add(highlightObjectLabel(designation, marker.userData.aid, color, showAxes));
  return marker;
}

function highlightObjectLabel(text, aid, color, showAxes = false) {
  const div = document.createElement("div");
  div.className = "xuv-three-label is-highlight";
  div.textContent = text;
  div.style.color = color;
  div.style.fontSize = "11px";
  div.style.fontWeight = "800";
  div.style.transform = "translate(14px, -50%)";
  div.style.textShadow = showAxes
    ? "0 1px 2px rgba(255, 255, 255, .95), 0 0 6px rgba(255, 255, 255, .85)"
    : "0 1px 3px rgba(0, 0, 0, .95), 0 0 8px rgba(0, 0, 0, .85)";
  const label = new CSS2DObject(div);
  label.userData = { aid, kind: "highlight-label" };
  label.renderOrder = 902;
  return label;
}

function addModelObjects(panel) {
  (panel.data.modelSurfaces || []).forEach((surface) => {
    const x = surface.x || [];
    const y = surface.y || [];
    const z = surface.z || [];
    const count = Math.min(x.length, y.length, z.length);
    const triCount = Math.min((surface.i || []).length, (surface.j || []).length, (surface.k || []).length);
    if (!count || !triCount) return;
    const positions = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      positions[index * 3] = Number(x[index]);
      positions[index * 3 + 1] = Number(y[index]);
      positions[index * 3 + 2] = Number(z[index]);
    }
    const indices = [];
    for (let index = 0; index < triCount; index += 1) {
      indices.push(Number(surface.i[index]), Number(surface.j[index]), Number(surface.k[index]));
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const aid = String(surface.moca_aid || "model");
    const material = new THREE.MeshLambertMaterial({
      color: panel.data.colormap?.[aid] || "#888888",
      transparent: true,
      opacity: Math.max(0.04, Math.min(0.34, Number(surface.opacity || 0.16) * 1.1)),
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData = { aid, kind: "model" };
    panel.dataGroup.add(mesh);
  });
}

function addErrorObjects(panel) {
  (panel.data.errorSegments || []).forEach((group) => {
    const points = [];
    (group.segments || []).forEach((segment) => {
      points.push(new THREE.Vector3(...segment[0]), new THREE.Vector3(...segment[1]));
    });
    if (!points.length) return;
    const line = lineSegmentsFromPoints(points, group.color || "#777777", 0.32);
    line.userData = { aid: group.aid, kind: "errors" };
    panel.dataGroup.add(line);
  });
}

function addAssociationCenterLabels(panel) {
  const rowsByAid = new Map();
  (panel.data.rows || []).forEach((row) => {
    const aid = String(row.moca_aid || "Unassigned");
    if (!rowsByAid.has(aid)) rowsByAid.set(aid, []);
    rowsByAid.get(aid).push(row);
  });
  const range = panel.data.bounds?.ranges?.[2] || [-500, 500];
  const verticalOffset = Math.max(0, range[1] - range[0]) * 0.0175;
  rowsByAid.forEach((rows, aid) => {
    const center = [0, 1, 2].map((index) => robustMedian(rows.map((row) => row[`plot${index}`]).filter(finite).map(Number)));
    if (center.some((value) => !finite(value))) return;
    addTextLabel(panel, aid, new THREE.Vector3(center[0], center[1], center[2] + verticalOffset), {
      color: panel.data.colormap?.[aid] || "#ffffff",
      className: panel.data.showAxes ? "xuv-three-label is-association is-axis" : "xuv-three-label is-association",
      aid,
    });
  });
}

function renderLegend(panel) {
  if (!panel.legendEl) return;
  const counts = new Map();
  (panel.data.rows || []).forEach((row) => {
    const aid = String(row.moca_aid || "Unassigned");
    counts.set(aid, (counts.get(aid) || 0) + 1);
  });
  (panel.data.modelSurfaces || []).forEach((surface) => {
    const aid = String(surface.moca_aid || "model");
    if (!counts.has(aid)) counts.set(aid, 0);
  });
  panel.legendEl.innerHTML = [...counts.keys()].map((aid) => `
    <button type="button" class="${frozenState.hiddenAids.has(aid) ? "is-muted" : ""}" data-aid="${escapeHtml(aid)}" title="Toggle ${escapeHtml(aid)}">
      <span class="xuv-three-swatch" style="--swatch:${escapeHtml(panel.data.colormap?.[aid] || "#777777")}"></span>
      <span>${escapeHtml(aid)}</span>
      <span class="xuv-three-count">${(counts.get(aid) || 0).toLocaleString()}</span>
    </button>
  `).join("");
  panel.legendEl.querySelectorAll("button[data-aid]").forEach((button) => {
    button.addEventListener("click", () => {
      const aid = button.dataset.aid;
      if (frozenState.hiddenAids.has(aid)) frozenState.hiddenAids.delete(aid);
      else frozenState.hiddenAids.add(aid);
      applyLegendVisibility();
    });
  });
}

function applyLegendVisibility() {
  frozenState.panels.forEach((panel) => {
    panel.dataGroup.traverse((object) => {
      const aid = object.userData?.aid;
      if (!aid) return;
      object.visible = !frozenState.hiddenAids.has(String(aid));
    });
    panel.legendEl?.querySelectorAll("button[data-aid]").forEach((button) => {
      button.classList.toggle("is-muted", frozenState.hiddenAids.has(String(button.dataset.aid)));
    });
  });
}

function onPointerUp(panel, event) {
  if (event.button !== 0) return;
  const hit = pickPoint(panel, event);
  if (!hit) {
    frozenState.selectedOid = "";
  } else {
    const row = (hit.object.userData?.rows || [])[hit.index];
    frozenState.selectedOid = normalizedMocaOid(row?.moca_oid);
  }
  renderSelectedMarkers();
  renderFrozenTable();
}

function onPointerMove(panel, event) {
  const hit = pickPoint(panel, event);
  if (!hit) {
    hideTooltip(panel);
    return;
  }
  const row = (hit.object.userData?.rows || [])[hit.index];
  if (!row || !panel.tooltipEl) return;
  panel.tooltipEl.innerHTML = hoverTextForRow(row);
  panel.tooltipEl.hidden = false;
  const rect = panel.plotEl.getBoundingClientRect();
  panel.tooltipEl.style.left = `${Math.min(rect.width - 280, Math.max(10, event.clientX - rect.left + 14))}px`;
  panel.tooltipEl.style.top = `${Math.min(rect.height - 150, Math.max(10, event.clientY - rect.top + 14))}px`;
}

function hideTooltip(panel) {
  if (panel.tooltipEl) panel.tooltipEl.hidden = true;
}

function pickPoint(panel, event) {
  const rect = panel.renderer.domElement.getBoundingClientRect();
  panel.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  panel.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  panel.raycaster.setFromCamera(panel.pointer, panel.camera);
  const intersections = panel.raycaster.intersectObjects(panel.pickObjects.filter((object) => object.visible), false);
  return intersections.length ? intersections[0] : null;
}

function renderSelectedMarkers() {
  frozenState.panels.forEach(renderSelectedMarker);
}

function renderSelectedMarker(panel) {
  panel.selectedGroup.children.slice().forEach((child) => {
    panel.selectedGroup.remove(child);
    disposeObject(child);
  });
  if (!frozenState.selectedOid) return;
  const row = findRowByOid(panel, frozenState.selectedOid);
  if (!row || ![row.plot0, row.plot1, row.plot2].every(finite)) return;
  const radius = Math.max(4, Math.min(14, (panel.data.bounds?.radius || 500) * 0.012)) * 0.7;
  const geometry = new THREE.TorusGeometry(radius, Math.max(0.28, radius * 0.075), 8, 72);
  const material = new THREE.MeshBasicMaterial({
    color: selectionColor,
    transparent: true,
    opacity: 0.3,
    depthTest: false,
  });
  [[0, 0, 0], [Math.PI / 2, 0, 0], [0, Math.PI / 2, 0]].forEach((rotation) => {
    const ring = new THREE.Mesh(geometry.clone(), material.clone());
    ring.rotation.set(rotation[0], rotation[1], rotation[2]);
    ring.position.set(row.plot0, row.plot1, row.plot2);
    ring.renderOrder = 1000;
    panel.selectedGroup.add(ring);
  });
}

function renderFrozenTable() {
  const title = document.getElementById("xuv-table-title");
  const subtitle = document.getElementById("xuv-table-subtitle");
  const table = document.getElementById("xuv-table");
  if (!table) return;
  const tableData = sceneData.table || { columns: [], rows: [] };
  const selectedRow = frozenState.selectedOid ? firstRowByOid(frozenState.selectedOid) : null;
  const rows = selectedRow ? [tableRowForObject(selectedRow, tableData.axes || [])] : (tableData.rows || []);
  title.textContent = selectedRow ? "1 selected object" : (tableData.title || "Displayed objects");
  subtitle.textContent = selectedRow ? "Double-click an empty region of a panel to reset the selection." : (tableData.subtitle || "");
  table.innerHTML = rows.length
    ? tableHtml(tableData.columns || [], rows, new Set(["report"]))
    : `<div class="selection-table">No objects to display.</div>`;
}

function tableRowForObject(row, axes) {
  const reportUrl = mocaReportUrl(row.moca_oid);
  const out = {
    moca_oid: normalizedMocaOid(row.moca_oid),
    designation: row.designation || "",
    moca_aid: row.moca_aid || "",
    moca_mtid: row.moca_mtid || "",
    spt: row.spt || "",
    ya_prob: finite(row.ya_prob) ? Number(row.ya_prob).toFixed(1) : "",
    report: reportUrl,
  };
  axes.forEach((axis, index) => {
    out[axis] = formatNumber(tableAxisValue(row, axes, axis, index), 2);
  });
  return out;
}

function renderSummary() {
  const summary = document.getElementById("xuv-summary");
  const hint = document.getElementById("xuv-hint-text");
  const memberCount = (sceneData.panels || []).reduce((total, panel) => total + Number(panel.summary?.members || 0), 0);
  const highlighted = (sceneData.panels || []).reduce((total, panel) => Math.max(total, Number(panel.summary?.highlighted || 0)), 0);
  const models = (sceneData.panels || []).reduce((total, panel) => Math.max(total, Number(panel.summary?.models || 0)), 0);
  if (summary) summary.textContent = sceneData.dual
    ? `${memberCount.toLocaleString()} plotted panel rows, ${models.toLocaleString()} model components, ${highlighted.toLocaleString()} highlighted objects`
    : `${memberCount.toLocaleString()} members, ${models.toLocaleString()} model components, ${highlighted.toLocaleString()} highlighted objects`;
  if (hint) {
    const lines = [`Frozen export created ${sceneData.exportedAt || ""}.`];
    if ((sceneData.panels || []).some((panel) => panel.galaxyActive)) lines.push(`Galaxy background image: ${sceneData.galaxyCredit || "ESO/S. Brunier"}.`);
    lines.push("Use a local web server if your browser blocks file:// module loading.");
    hint.innerHTML = lines.map(escapeHtml).join("<br>");
  }
}

function recenterAllPanelsOnSun() {
  frozenState.panels.forEach((panel) => {
    const offset = panel.camera.position.clone().sub(panel.controls.target);
    const cleanOffset = offset.lengthSq() > 0 ? offset : new THREE.Vector3(1.25, -1.55, 0.9).normalize().multiplyScalar(500);
    panel.controls.target.set(0, 0, 0);
    panel.camera.position.copy(cleanOffset);
    panel.controls.update();
  });
}

function firstRowByOid(oid) {
  for (const panel of frozenState.panels) {
    const row = findRowByOid(panel, oid);
    if (row) return row;
  }
  return null;
}

function findRowByOid(panel, oid) {
  const normalized = normalizedMocaOid(oid);
  return [...(panel.data.rows || []), ...(panel.data.overlayRows || [])].find((row) => normalizedMocaOid(row.moca_oid) === normalized);
}

function addTextLabel(panel, text, position, options = {}) {
  const div = document.createElement("div");
  div.className = options.className || "xuv-three-label";
  div.textContent = text;
  if (options.color) div.style.color = options.color;
  if (options.yOffset) div.style.transform = `translate(-50%, ${Number(options.yOffset)}px)`;
  const label = new CSS2DObject(div);
  label.position.copy(position);
  label.userData = { aid: options.aid, kind: "label" };
  panel.dataGroup.add(label);
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

function tubeFromPoints(points, color, radius, opacity = 1, closed = false, radialSegments = 8) {
  const cleanPoints = points.filter((point) => point && finite(point.x) && finite(point.y) && finite(point.z));
  if (cleanPoints.length < 2) return new THREE.Group();
  const curve = cleanPoints.length === 2
    ? new THREE.LineCurve3(cleanPoints[0], cleanPoints[1])
    : new THREE.CatmullRomCurve3(cleanPoints, closed, "catmullrom", 0.5);
  const geometry = new THREE.TubeGeometry(curve, Math.max(1, closed ? cleanPoints.length : cleanPoints.length - 1), radius, radialSegments, closed);
  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: opacity < 1,
    opacity,
    depthWrite: opacity >= 1,
  });
  return new THREE.Mesh(geometry, material);
}

function lineFromPoints(points, color, opacity = 1) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity });
  return new THREE.Line(geometry, material);
}

function lineSegmentsFromPoints(points, color, opacity = 1) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity });
  return new THREE.LineSegments(geometry, material);
}

function disposeObject(object) {
  object.traverse((child) => {
    if (child.geometry) child.geometry.dispose();
    if (child.material) {
      const materials = Array.isArray(child.material) ? child.material : [child.material];
      materials.forEach((material) => material.dispose());
    }
  });
}

function referenceVector(axes, plane, radius, angle) {
  const vector = new THREE.Vector3(0, 0, 0);
  const firstIndex = axes.indexOf(plane.axes[0]);
  const secondIndex = axes.indexOf(plane.axes[1]);
  if (firstIndex >= 0) vector.setComponent(firstIndex, radius * Math.cos(angle));
  if (secondIndex >= 0) vector.setComponent(secondIndex, radius * Math.sin(angle));
  return vector;
}

function referencePlanePlotRadius(plane, radius) {
  const scale = finite(plane?.radiusScale) ? Number(plane.radiusScale) : 1;
  return Number(radius) * scale;
}

function normalizedAxisRange(range, fallbackRadius) {
  const lower = finite(range?.[0]) ? Number(range[0]) : -fallbackRadius;
  const upper = finite(range?.[1]) ? Number(range[1]) : fallbackRadius;
  return upper >= lower ? [lower, upper] : [upper, lower];
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
    values.push(Math.abs(value) < step * 1e-8 ? 0 : value);
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

function tableHtml(columns, rows, htmlColumns = new Set()) {
  return `
    <div class="selection-table">
      <table>
        <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>${columns.map((column) => `<td>${htmlColumns.has(column) ? reportCell(row[column]) : escapeHtml(row[column] ?? "")}</td>`).join("")}</tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function reportCell(url) {
  return url ? `<a class="report-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">Report</a>` : "";
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

function tableAxisValue(row, axes, axis, plotIndex) {
  if (row.plotAxesKey === axes.join("") && finite(row[`plot${plotIndex}`])) return Number(row[`plot${plotIndex}`]);
  const optKey = `${axis}_opt`;
  if (sceneData.assumeMembership && finite(row[optKey])) return Number(row[optKey]);
  return finite(row[axis]) ? Number(row[axis]) : null;
}

function axisUnit(axis) {
  return ["u", "v", "w"].includes(axis) ? "km/s" : "pc";
}

function mocaReportUrl(oid) {
  const normalized = normalizedMocaOid(oid);
  return normalized ? `https://mocadb.ca/search/results?search-query=oid%28${encodeURIComponent(normalized)}%29&search-type=star` : "";
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

function formatNumber(value, digits) {
  return finite(value) ? Number(value).toFixed(digits) : "";
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

function cssEscape(value) {
  if (window.CSS?.escape) return CSS.escape(String(value));
  return String(value).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
