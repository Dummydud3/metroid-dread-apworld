(() => {
  const $ = (id) => document.getElementById(id);
  const SVG_NS = "http://www.w3.org/2000/svg";

  const els = {
    conn: $("conn"),
    slot: $("slot-label"),
    counts: $("counts"),
    spots: $("spot-count"),
    tabs: $("region-tabs"),
    pane: $("map-pane"),
    svg: $("world-map"),
    tooltip: $("tooltip"),
    panel: $("explain-panel"),
    title: $("explain-title"),
    body: $("explain-body"),
    close: $("explain-close"),
  };

  let layout = null;
  let terrain = null;
  let catalog = null;
  let status = {
    ap_connected: false,
    checked_location_ids: [],
    in_logic_location_ids: [],
    reachable_cells: {},
    reachable_areas: {},
    reachable_spots: {},
    checked_locations: 0,
    missing_locations: 0,
    slot: "",
  };
  let activeRegion = "Artaria";
  let idByName = new Map();
  let selectedMarker = null;
  let explainSeq = 0;
  let view = { minX: 0, minY: 0, maxX: 1, maxY: 1 };
  let drag = null;
  let lastPaintSig = "";

  function svgEl(name, attrs) {
    const el = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attrs || {})) {
      el.setAttribute(key, String(value));
    }
    return el;
  }

  function currentRegion() {
    return (layout && layout.regions && layout.regions[activeRegion]) || null;
  }

  function applyViewBox() {
    const w = view.maxX - view.minX;
    const h = view.maxY - view.minY;
    els.svg.setAttribute("viewBox", `${view.minX} ${-view.maxY} ${w} ${h}`);
    layoutIcons();
  }

  function resetView() {
    const region = currentRegion();
    if (!region || !region.bounds) return;
    const [x1, y1, x2, y2] = region.bounds;
    view = { minX: x1, minY: y1, maxX: x2, maxY: y2 };
    applyViewBox();
  }

  function clientToWorld(ev) {
    const rect = els.svg.getBoundingClientRect();
    const x = view.minX + ((ev.clientX - rect.left) / rect.width) * (view.maxX - view.minX);
    const y = view.maxY - ((ev.clientY - rect.top) / rect.height) * (view.maxY - view.minY);
    return [x, y];
  }

  function markerKind(apName) {
    const id = idByName.get(apName);
    if (id == null) return "unchecked";
    const checked = new Set((status.checked_location_ids || []).map(Number));
    const inLogic = new Set((status.in_logic_location_ids || []).map(Number));
    if (checked.has(Number(id))) return "checked";
    if (inLogic.has(Number(id))) return "in-logic";
    return "unchecked";
  }

  function hideTooltip() {
    els.tooltip.hidden = true;
  }

  function showTooltip(text, ev) {
    els.tooltip.hidden = false;
    els.tooltip.textContent = text;
    const pad = 12;
    let x = ev.clientX + pad;
    let y = ev.clientY + pad;
    const rect = els.tooltip.getBoundingClientRect();
    if (x + rect.width > window.innerWidth - 8) x = ev.clientX - rect.width - pad;
    if (y + rect.height > window.innerHeight - 8) y = ev.clientY - rect.height - pad;
    els.tooltip.style.left = `${Math.max(8, x)}px`;
    els.tooltip.style.top = `${Math.max(8, y)}px`;
  }

  function closeExplain() {
    explainSeq += 1;
    els.panel.hidden = true;
    if (selectedMarker) {
      selectedMarker.classList.remove("selected");
      selectedMarker = null;
    }
  }

  function chipRow(kind, labels) {
    if (!labels || !labels.length) return "";
    return `<div class="chip-row">${labels
      .map((label) => `<span class="chip ${kind}">${escapeHtml(label)}</span>`)
      .join("")}</div>`;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderNeedGroup(group) {
    const items = group.items || [];
    const tricks = group.tricks || [];
    const events = group.events || [];
    if (!items.length && !tricks.length && !events.length) {
      return `<p class="explain-note">No extra items or enabled tricks on this path.</p>`;
    }
    return [
      items.length ? `<div class="explain-section"><h3>Items</h3>${chipRow("item", items)}</div>` : "",
      tricks.length ? `<div class="explain-section"><h3>Tricks</h3>${chipRow("trick", tricks)}</div>` : "",
      events.length ? `<div class="explain-section"><h3>Events</h3>${chipRow("event", events)}</div>` : "",
    ].join("");
  }

  function renderExplainResult(result, checked) {
    if (!result) return `<p class="explain-note">No explanation returned.</p>`;
    if (result.error) return `<p class="explain-note">${escapeHtml(result.error)}</p>`;
    const badge = checked
      ? `<span class="badge checked">Checked</span>`
      : result.in_logic
        ? `<span class="badge in-logic">In logic</span>`
        : `<span class="badge out-logic">Out of logic</span>`;
    const alts = Array.isArray(result.alternatives) ? result.alternatives : [];
    let body = "";
    if (result.in_logic) {
      body = renderNeedGroup({
        items: result.items || [],
        tricks: result.tricks || [],
        events: [],
      });
      if (!(result.items || []).length && !(result.tricks || []).length) {
        body = `<p class="explain-note">Reachable with your current kit. No extra items or enabled tricks on this path.</p>`;
      }
    } else if (alts.length > 1) {
      body = `<div class="explain-section"><h3>Need one of</h3>${alts
        .map(
          (group, idx) =>
            `<div class="alt-block"><p class="alt-label">Option ${idx + 1}</p>${renderNeedGroup(group)}</div>`
        )
        .join("")}</div>`;
    } else if (
      alts.length === 1 ||
      (result.items || []).length ||
      (result.tricks || []).length ||
      (result.events || []).length
    ) {
      body = `<div class="explain-section"><h3>Next hop needs</h3>${renderNeedGroup({
        items: result.items || [],
        tricks: result.tricks || [],
        events: result.events || [],
      })}</div>`;
    } else {
      body = `<p class="explain-note">Not in logic with your current items and enabled tricks.</p>`;
    }
    return `<p class="explain-name">${badge}</p>${body}`;
  }

  async function openExplain(apName, markerEl) {
    const seq = ++explainSeq;
    if (selectedMarker && selectedMarker !== markerEl) {
      selectedMarker.classList.remove("selected");
    }
    selectedMarker = markerEl;
    markerEl.classList.add("selected");
    hideTooltip();
    els.title.textContent = apName;
    els.body.innerHTML = `<p class="explain-note">Reading logic…</p>`;
    els.panel.hidden = false;
    const id = idByName.get(apName);
    if (id == null) {
      els.body.innerHTML = `<p class="explain-note">This pickup is not in the Archipelago catalog.</p>`;
      return;
    }
    try {
      const requestId = `vis-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const result = await window.dreadVisualizer.explainLocation(id, requestId);
      if (seq !== explainSeq) return;
      const checked = new Set((status.checked_location_ids || []).map(Number));
      els.body.innerHTML = `<div class="explain-check">${renderExplainResult(
        result,
        checked.has(Number(id))
      )}</div>`;
    } catch (err) {
      if (seq !== explainSeq) return;
      els.body.innerHTML = `<p class="explain-note">${escapeHtml(err.message || err)}</p>`;
    }
  }

  function renderTabs() {
    els.tabs.textContent = "";
    const names = (layout && layout.region_order) || Object.keys((layout && layout.regions) || {});
    for (const name of names) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = name;
      if (name === activeRegion) btn.classList.add("active");
      btn.addEventListener("click", () => {
        activeRegion = name;
        closeExplain();
        resetView();
        renderTabs();
        renderMap();
      });
      els.tabs.appendChild(btn);
    }
  }

  function renderHeader() {
    els.conn.dataset.state = status.ap_connected ? "on" : "off";
    els.conn.textContent = status.ap_connected ? "AP online" : "AP offline";
    els.slot.textContent = status.slot || "—";
    const checked = Number(status.checked_locations) || (status.checked_location_ids || []).length;
    const missing = Number(status.missing_locations) || 0;
    const total = checked + missing || (catalog && catalog.locations ? catalog.locations.length : 0);
    els.counts.textContent = `${checked} / ${total} checks`;
    const region = currentRegion();
    const scenario = region && region.scenario;
    const rooms = ((status.reachable_areas || {})[scenario] || []).length;
    const floors = ((status.reachable_spots || {})[scenario] || []).length;
    els.spots.textContent = floors ? `${floors} spots` : `${rooms} rooms`;
  }

  function loopPath(loops) {
    return (loops || [])
      .filter((loop) => loop && loop.length >= 3)
      .map((loop) => {
        const first = loop[0];
        const rest = loop.slice(1).map(([x, y]) => `L ${x},${-y}`).join(" ");
        return `M ${first[0]},${-first[1]} ${rest} Z`;
      })
      .join(" ");
  }

  function appendOverlay(parent, loops, cls) {
    const d = loopPath(loops);
    if (!d) return;
    parent.appendChild(svgEl("path", { class: cls, d, "fill-rule": "evenodd" }));
  }

  function appendBox(parent, box, cls) {
    if (!box || box.length < 4) return;
    const [x1, y1, x2, y2] = box;
    parent.appendChild(
      svgEl("rect", {
        class: cls,
        x: x1,
        y: -y2,
        width: Math.max(1, x2 - x1),
        height: Math.max(1, y2 - y1),
      })
    );
  }

  function currentTerrain() {
    return (terrain && terrain.regions && terrain.regions[activeRegion]) || null;
  }

  function pointInPoly(x, y, poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const xi = poly[i][0];
      const yi = poly[i][1];
      const xj = poly[j][0];
      const yj = poly[j][1];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-30) + xi) {
        inside = !inside;
      }
    }
    return inside;
  }

  function polygonArea(poly) {
    let acc = 0;
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i];
      const b = poly[(i + 1) % poly.length];
      acc += a[0] * b[1] - b[0] * a[1];
    }
    return Math.abs(acc) * 0.5;
  }

  function loopFractionInside(loop, camera) {
    if (!camera || camera.length < 3 || !loop || !loop.length) return 1;
    let hits = 0;
    let sx = 0;
    let sy = 0;
    for (const [px, py] of loop) {
      if (pointInPoly(px, py, camera)) hits += 1;
      sx += px;
      sy += py;
    }
    if (pointInPoly(sx / loop.length, sy / loop.length, camera)) hits += 1;
    return hits / (loop.length + 1);
  }

  function areaCamera(areaName) {
    const region = currentRegion();
    if (!region || !areaName) return null;
    const area = (region.areas || []).find((item) => item.name === areaName);
    return (area && area.polygon) || null;
  }

  function spotXY(spot) {
    if (!spot) return null;
    if (Array.isArray(spot) && spot.length >= 2) return [Number(spot[0]), Number(spot[1]), ""];
    if (spot.x == null || spot.y == null) return null;
    return [Number(spot.x), Number(spot.y), spot.area || ""];
  }

  const FLOOR_MIN_AREA = 120000;

  function pickLoopForSpot(x, y, layers, camera) {
    const contained = [];
    layers.forEach((layer, li) => {
      (layer.loops || []).forEach((loop, j) => {
        if (!loop || loop.length < 3 || !pointInPoly(x, y, loop)) return;
        const frac = camera ? loopFractionInside(loop, camera) : 1;
        contained.push({ li, j, area: polygonArea(loop), frac });
      });
    });
    const floorsInRoom = contained.filter((row) => row.frac >= 0.35 && row.area >= FLOOR_MIN_AREA);
    if (floorsInRoom.length) {
      floorsInRoom.sort((a, b) => a.area - b.area);
      return floorsInRoom[0];
    }
    if (camera && camera.length >= 3) {
      let bestFloor = null;
      let bestFloorArea = -1;
      let bestNear = null;
      let bestD = Infinity;
      layers.forEach((layer, li) => {
        (layer.loops || []).forEach((loop, j) => {
          if (!loop || loop.length < 3 || loopFractionInside(loop, camera) < 0.5) return;
          const area = polygonArea(loop);
          if (area >= FLOOR_MIN_AREA && area > bestFloorArea) {
            bestFloorArea = area;
            bestFloor = { li, j };
          }
          let sx = 0;
          let sy = 0;
          for (const [px, py] of loop) {
            sx += px;
            sy += py;
          }
          const dx = sx / loop.length - x;
          const dy = sy / loop.length - y;
          const dist = dx * dx + dy * dy;
          if (dist < bestD) {
            bestD = dist;
            bestNear = { li, j };
          }
        });
      });
      if (bestFloor) return bestFloor;
      if (bestNear) return bestNear;
    }
    if (contained.length) {
      contained.sort((a, b) => a.area - b.area);
      return contained[0];
    }
    return null;
  }

  function reachableFloorLoops(data) {
    const region = currentRegion();
    const scenario = region && region.scenario;
    const spots = (status.reachable_spots || {})[scenario] || [];
    const layers = (data && data.terrain) || [];
    const chosen = layers.map(() => new Set());
    for (const raw of spots) {
      const parsed = spotXY(raw);
      if (!parsed) continue;
      const [x, y, areaName] = parsed;
      const picked = pickLoopForSpot(x, y, layers, areaCamera(areaName));
      if (picked) chosen[picked.li].add(picked.j);
    }
    return chosen;
  }

  function renderReachableFloors(group, data) {
    const chosen = reachableFloorLoops(data);
    (data.terrain || []).forEach((layer, li) => {
      const loops = [...(chosen[li] || [])].map((j) => layer.loops[j]);
      const d = loopPath(loops);
      if (!d) return;
      group.appendChild(svgEl("path", { class: "terrain-reachable", d }));
    });
  }

  function renderTerrain(group) {
    const data = currentTerrain();
    if (!data) return;
    const clipId = `terrain-clip-${activeRegion.replace(/[^A-Za-z0-9_-]/g, "")}`;
    const defs = svgEl("defs", {});
    const clip = svgEl("clipPath", { id: clipId });
    for (const layer of data.terrain || []) {
      const d = loopPath(layer.loops || []);
      if (!d) continue;
      const z = Number(layer.z) || 0;
      group.appendChild(
        svgEl("path", {
          class: `terrain-fill z-${z}`,
          d,
          "fill-rule": "evenodd",
        })
      );
      clip.appendChild(svgEl("path", { d, "fill-rule": "evenodd" }));
    }
    defs.appendChild(clip);
    group.appendChild(defs);
    const overlays = svgEl("g", {
      class: "overlays",
      "clip-path": `url(#${clipId})`,
    });
    appendOverlay(overlays, data.heat, "overlay-heat");
    appendOverlay(overlays, data.water, "overlay-water");
    appendOverlay(overlays, data.freeze, "overlay-freeze");
    appendOverlay(overlays, data.emmi, "overlay-emmi");
    appendOverlay(overlays, data.occluders, "overlay-occluder");
    group.appendChild(overlays);
    const reachableFloors = svgEl("g", { class: "reachable-floors" });
    renderReachableFloors(reachableFloors, data);
    group.appendChild(reachableFloors);
    for (const line of data.magnets || []) {
      if (!line || line.length < 2) continue;
      group.appendChild(
        svgEl("polyline", {
          class: "magnet-line",
          points: line.map(([x, y]) => `${x},${-y}`).join(" "),
        })
      );
    }
    for (const line of data.transports || []) {
      group.appendChild(
        svgEl("line", {
          class: "transport-line",
          x1: line.x1,
          y1: -line.y1,
          x2: line.x2,
          y2: -line.y2,
        })
      );
    }
    for (const door of data.doors || []) {
      if (door.left) appendBox(group, door.left, "door-box");
      if (door.right) appendBox(group, door.right, "door-box");
      if (!door.left && !door.right && door.x != null && door.y != null) {
        appendBox(group, [door.x - 40, door.y - 80, door.x + 40, door.y + 80], "door-box");
      }
    }
    for (const block of data.blockages || []) {
      if (block.box) appendBox(group, block.box, "blockage-box");
    }
  }

  function iconWorldSize() {
    const rect = els.svg.getBoundingClientRect();
    const worldPerPx = (view.maxX - view.minX) / Math.max(1, rect.width);
    return Math.max(200, Math.min(620, worldPerPx * 22));
  }

  function layoutIcons() {
    const s = iconWorldSize() / 24;
    for (const g of els.svg.querySelectorAll(".map-icon")) {
      const x = Number(g.getAttribute("data-x"));
      const y = Number(g.getAttribute("data-y"));
      g.setAttribute("transform", `translate(${x} ${-y}) scale(${s})`);
    }
  }

  function iconTip(icon) {
    const dest = icon.dest ? ` → ${icon.dest}` : "";
    return `${icon.label || icon.kind || "Icon"}${dest}`;
  }

  function drawGlyph(parent, kind, letter) {
    const bg = (cls, shape, attrs) => {
      parent.appendChild(svgEl(shape, { class: `icon-bg ${cls}`, ...attrs }));
    };
    const mark = (shape, attrs) => {
      parent.appendChild(svgEl(shape, attrs));
    };
    const label = (text, cls) => {
      const el = svgEl("text", {
        class: cls || "icon-letter",
        x: 0,
        y: 4.2,
        "text-anchor": "middle",
      });
      el.textContent = text;
      parent.appendChild(el);
    };
    if (kind === "save") {
      bg("save", "rect", { x: -9, y: -9, width: 18, height: 18, rx: 3 });
      label("S");
      return;
    }
    if (kind === "map") {
      bg("map", "rect", { x: -9, y: -9, width: 18, height: 18, rx: 3 });
      mark("path", {
        class: "icon-stroke",
        d: "M-5.5,-4.5 L-1.5,-6 L1.5,-4 L5.5,-6 L5.5,5 L1.5,7 L-1.5,5 L-5.5,7 Z",
      });
      return;
    }
    if (kind === "energy") {
      bg("energy", "circle", { r: 9 });
      label("E");
      return;
    }
    if (kind === "ammo") {
      bg("ammo", "circle", { r: 9 });
      mark("path", {
        class: "icon-fill",
        d: "M-1.2,-6.5 L1.2,-6.5 L2.4,1.5 L1.2,6.5 L-1.2,6.5 L-2.4,1.5 Z",
      });
      return;
    }
    if (kind === "total") {
      bg("total", "circle", { r: 9 });
      label("T");
      return;
    }
    if (kind === "nav") {
      bg("nav", "rect", { x: -9, y: -9, width: 18, height: 18, rx: 3 });
      mark("path", {
        class: "icon-stroke",
        d: "M-5,3 L0,-5 L5,3 M-2.5,3 L0,0.4 L2.5,3",
      });
      return;
    }
    if (kind === "elevator") {
      bg("elevator", "rect", { x: -8, y: -10, width: 16, height: 20, rx: 3 });
      mark("path", {
        class: "icon-fill",
        d: "M0,-6.5 L-3.5,-2.2 L3.5,-2.2 Z M0,6.5 L-3.5,2.2 L3.5,2.2 Z",
      });
      return;
    }
    if (kind === "tram") {
      bg("tram", "rect", { x: -10, y: -8, width: 20, height: 16, rx: 3 });
      mark("path", {
        class: "icon-fill",
        d: "M-6.5,0 L-2.2,-3.5 L-2.2,3.5 Z M6.5,0 L2.2,-3.5 L2.2,3.5 Z",
      });
      return;
    }
    if (kind === "capsule") {
      bg("capsule", "rect", { x: -7, y: -10, width: 14, height: 20, rx: 7 });
      mark("path", { class: "icon-stroke", d: "M-3,-2 L3,2 M-3,2 L3,-2" });
      return;
    }
    if (kind === "teleport") {
      bg("teleport", "polygon", { points: "0,-10 8.7,-5 8.7,5 0,10 -8.7,5 -8.7,-5" });
      label(letter || "T");
      return;
    }
    if (kind === "device") {
      bg("device", "rect", { x: -8, y: -8, width: 16, height: 16, rx: 2 });
      mark("circle", { class: "icon-stroke", r: 3.4, fill: "none" });
      return;
    }
    if (kind === "cu") {
      bg("cu", "circle", { r: 9.5 });
      label("CU", "icon-letter small");
      return;
    }
    if (kind === "boss") {
      bg("boss", "circle", { r: 9.5 });
      mark("path", { class: "icon-stroke", d: "M-4.5,-4.5 L4.5,4.5 M4.5,-4.5 L-4.5,4.5" });
      return;
    }
    if (kind === "ship") {
      bg("ship", "polygon", { points: "0,-9 8,7 -8,7" });
      return;
    }
    bg("save", "rect", { x: -8, y: -8, width: 16, height: 16, rx: 3 });
  }

  function renderIcons(parent, icons) {
    const layer = svgEl("g", { class: "map-icons" });
    for (const icon of icons || []) {
      if (icon.x == null || icon.y == null) continue;
      const g = svgEl("g", {
        class: `map-icon kind-${icon.kind || "other"}`,
        "data-x": icon.x,
        "data-y": icon.y,
      });
      drawGlyph(g, icon.kind, icon.letter);
      const tip = iconTip(icon);
      g.addEventListener("mouseenter", (ev) => showTooltip(tip, ev));
      g.addEventListener("mousemove", (ev) => showTooltip(tip, ev));
      g.addEventListener("mouseleave", hideTooltip);
      g.addEventListener("pointerdown", (ev) => ev.stopPropagation());
      layer.appendChild(g);
    }
    parent.appendChild(layer);
    layoutIcons();
  }

  function renderMap() {
    const region = currentRegion();
    els.svg.textContent = "";
    if (!region) return;

    const terrainGroup = svgEl("g", { class: "terrain" });
    renderTerrain(terrainGroup);
    els.svg.appendChild(terrainGroup);

    const reachable = new Set((status.reachable_areas || {})[region.scenario] || []);
    const rooms = svgEl("g", { class: "rooms" });
    for (const area of region.areas || []) {
      const poly = area.polygon || [];
      if (poly.length < 3) continue;
      const points = poly.map(([x, y]) => `${x},${-y}`).join(" ");
      const cls = reachable.has(area.name) ? "room-poly reachable" : "room-poly";
      const el = svgEl("polygon", { class: cls, points });
      el.addEventListener("mouseenter", (ev) => showTooltip(area.name, ev));
      el.addEventListener("mousemove", (ev) => showTooltip(area.name, ev));
      el.addEventListener("mouseleave", hideTooltip);
      rooms.appendChild(el);
    }
    els.svg.appendChild(rooms);

    const iconGroup = svgEl("g", { class: "poi" });
    renderIcons(iconGroup, (currentTerrain() || {}).icons || []);
    els.svg.appendChild(iconGroup);

    const markers = svgEl("g", { class: "checks" });
    const markerR = 70;
    for (const pickup of region.pickups || []) {
      const kind = markerKind(pickup.name);
      const el = svgEl("rect", {
        class: `marker ${kind}`,
        x: pickup.x - markerR,
        y: -(pickup.y + markerR),
        width: markerR * 2,
        height: markerR * 2,
        transform: `rotate(45 ${pickup.x} ${-pickup.y})`,
      });
      el.addEventListener("mouseenter", (ev) => showTooltip(`${pickup.name}\nClick for items / tricks`, ev));
      el.addEventListener("mousemove", (ev) => showTooltip(`${pickup.name}\nClick for items / tricks`, ev));
      el.addEventListener("mouseleave", hideTooltip);
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        openExplain(pickup.name, el);
      });
      markers.appendChild(el);
    }
    els.svg.appendChild(markers);
    applyViewBox();
  }

  function paintSig() {
    const region = currentRegion();
    const scenario = region && region.scenario;
    const areas = (status.reachable_areas || {})[scenario] || [];
    const spots = (status.reachable_spots || {})[scenario] || [];
    const checked = status.checked_location_ids || [];
    const logic = status.in_logic_location_ids || [];
    return [
      activeRegion,
      areas.length,
      spots.length,
      spots[0] && JSON.stringify(spots[0]),
      spots[spots.length - 1] && JSON.stringify(spots[spots.length - 1]),
      checked.length,
      logic.length,
      logic[0],
      logic[logic.length - 1],
    ].join("|");
  }

  function applyStatus(payload) {
    if (!payload || typeof payload !== "object") return;
    status = { ...status, ...payload };
    renderHeader();
    const sig = paintSig();
    if (sig !== lastPaintSig) {
      lastPaintSig = sig;
      renderMap();
    }
  }

  function onWheel(ev) {
    ev.preventDefault();
    const [wx, wy] = clientToWorld(ev);
    const factor = ev.deltaY < 0 ? 0.85 : 1.18;
    const nMinX = wx - (wx - view.minX) * factor;
    const nMaxX = wx + (view.maxX - wx) * factor;
    const nMinY = wy - (wy - view.minY) * factor;
    const nMaxY = wy + (view.maxY - wy) * factor;
    if (nMaxX - nMinX < 800 || nMaxY - nMinY < 800) return;
    if (nMaxX - nMinX > 80000 || nMaxY - nMinY > 80000) return;
    view = { minX: nMinX, minY: nMinY, maxX: nMaxX, maxY: nMaxY };
    applyViewBox();
  }

  function onPointerDown(ev) {
    if (ev.button !== 0) return;
    if (ev.target && ev.target.closest && (ev.target.closest(".marker") || ev.target.closest(".map-icon"))) return;
    drag = { x: ev.clientX, y: ev.clientY, view: { ...view } };
    els.pane.classList.add("dragging");
    els.pane.setPointerCapture(ev.pointerId);
  }

  function onPointerMove(ev) {
    if (!drag) return;
    const rect = els.svg.getBoundingClientRect();
    const dx = ((ev.clientX - drag.x) / rect.width) * (drag.view.maxX - drag.view.minX);
    const dy = ((ev.clientY - drag.y) / rect.height) * (drag.view.maxY - drag.view.minY);
    view = {
      minX: drag.view.minX - dx,
      maxX: drag.view.maxX - dx,
      minY: drag.view.minY + dy,
      maxY: drag.view.maxY + dy,
    };
    applyViewBox();
  }

  function onPointerUp(ev) {
    drag = null;
    els.pane.classList.remove("dragging");
    try {
      els.pane.releasePointerCapture(ev.pointerId);
    } catch (_) {
      /* ignore */
    }
  }

  function api() {
    return window.dreadVisualizer || null;
  }

  async function boot() {
    const bridge = api();
    const [layoutRes, terrainRes, cat] = await Promise.all([
      fetch("./world_layout.json"),
      fetch("./terrain.json"),
      bridge ? bridge.getCatalog() : Promise.resolve({ locations: [] }),
    ]);
    layout = await layoutRes.json();
    terrain = terrainRes.ok ? await terrainRes.json() : { regions: {} };
    catalog = cat || { locations: [] };
    idByName = new Map();
    for (const loc of catalog.locations || []) {
      idByName.set(loc.name, Number(loc.id));
    }
    if ((layout.region_order || []).length) {
      activeRegion = layout.region_order[0];
    }
    renderTabs();
    resetView();
    renderHeader();
    renderMap();
    if (bridge) {
      const live = await bridge.getStatus();
      applyStatus(live);
      bridge.onUpdate(applyStatus);
    }
    els.close.addEventListener("click", closeExplain);
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") closeExplain();
    });
    els.svg.addEventListener("wheel", onWheel, { passive: false });
    els.pane.addEventListener("pointerdown", onPointerDown);
    els.pane.addEventListener("pointermove", onPointerMove);
    els.pane.addEventListener("pointerup", onPointerUp);
    els.pane.addEventListener("pointerleave", onPointerUp);
    window.addEventListener("resize", layoutIcons);
  }

  boot().catch((err) => {
    els.counts.textContent = String(err.message || err);
  });
})();
