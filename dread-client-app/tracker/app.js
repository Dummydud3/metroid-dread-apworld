(() => {
  const $ = (id) => document.getElementById(id);

  const els = {
    conn: $("conn"),
    slot: $("slot-label"),
    counts: $("counts"),
    itemGrid: $("item-grid"),
    bossList: $("boss-list"),
    regionTabs: $("region-tabs"),
    regionTitle: $("region-title"),
    regionCounts: $("region-counts"),
    locList: $("loc-list"),
  };

  let catalog = null;
  let status = {
    ap_connected: false,
    received_items: [],
    checked_location_ids: [],
    in_logic_location_ids: [],
    in_logic_count: 0,
    items_received: 0,
    checked_locations: 0,
    missing_locations: 0,
    bosses: [],
    slot: "",
  };
  let activeRegion = "Artaria";
  let codeById = new Map();
  let itemByCode = new Map();

  function shortItemName(name) {
    return String(name || "")
      .replace(/^Progressive\s+/i, "Prog. ")
      .replace(/\s+Upgrade$/i, " Upg.")
      .replace(/\s+Tank$/i, " Tank");
  }

  function escapeRegExp(str) {
    return String(str).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function regionSortIndex(region) {
    const regions = catalog.regions || [];
    const idx = regions.indexOf(region);
    return idx === -1 ? regions.length : idx;
  }

  function buildLookups() {
    codeById = new Map();
    itemByCode = new Map();
    for (const it of catalog.items || []) {
      itemByCode.set(it.code, it);
    }
    const idMap = catalog.id_to_codes || {};
    for (const [id, codes] of Object.entries(idMap)) {
      codeById.set(Number(id), codes);
    }
    for (const it of catalog.items || []) {
      if (!codeById.has(it.id)) codeById.set(it.id, [it.code]);
    }
  }

  function countOwned() {
    const counts = new Map();
    for (const ri of status.received_items || []) {
      const codes = codeById.get(Number(ri.id)) || [];
      for (const code of codes) {
        counts.set(code, (counts.get(code) || 0) + 1);
      }
    }
    return counts;
  }

  function poolNameCounts() {
    const raw = status.tracker_item_pool;
    if (!raw || typeof raw !== "object") return null;
    const keys = Object.keys(raw);
    if (!keys.length) return null;
    const out = new Map();
    for (const [name, count] of Object.entries(raw)) {
      const n = Number(count);
      if (name && Number.isFinite(n) && n > 0) out.set(String(name), n);
    }
    return out.size ? out : null;
  }

  function filteredItemCodes(owned) {
    const pool = poolNameCounts();
    // No pool yet (offline / old seed): show full catalog rows.
    if (!pool) {
      const all = [];
      for (const row of catalog.item_rows || []) {
        for (const code of row) all.push(code);
      }
      return { codes: all, pool: null };
    }
    const allowed = new Set(pool.keys());
    const codes = [];
    const seen = new Set();
    for (const row of catalog.item_rows || []) {
      for (const code of row) {
        if (seen.has(code)) continue;
        const meta = itemByCode.get(code);
        if (!meta) continue;
        const inPool = allowed.has(meta.name);
        const isOwned = (owned.get(code) || 0) > 0;
        if (!inPool && !isOwned) continue;
        seen.add(code);
        codes.push(code);
      }
    }
    return { codes, pool };
  }

  function packItemRows(codes, perRow = 4) {
    const rows = [];
    for (let i = 0; i < codes.length; i += perRow) {
      rows.push(codes.slice(i, i + perRow));
    }
    return rows;
  }

  function renderItems() {
    const owned = countOwned();
    const { codes, pool } = filteredItemCodes(owned);
    const rows = pool ? packItemRows(codes, 4) : (catalog.item_rows || []);
    els.itemGrid.innerHTML = "";
    for (const row of rows) {
      const rowEl = document.createElement("div");
      rowEl.className = "item-row";
      for (const code of row) {
        const meta = itemByCode.get(code);
        if (!meta) continue;
        const n = owned.get(code) || 0;
        const poolMax = pool ? pool.get(meta.name) : null;
        const max =
          poolMax != null && Number.isFinite(poolMax) && poolMax > 0
            ? poolMax
            : meta.max_count || 1;
        const cell = document.createElement("div");
        cell.className = "item" + (n > 0 ? " owned" : "");
        cell.title = meta.name;
        if (meta.icon) {
          const img = document.createElement("img");
          img.className = "item-icon";
          img.src = meta.icon;
          img.alt = meta.name;
          img.draggable = false;
          img.addEventListener("error", () => {
            const name = document.createElement("span");
            name.className = "item-name";
            name.textContent = shortItemName(meta.name);
            img.replaceWith(name);
          });
          cell.appendChild(img);
        } else {
          const name = document.createElement("span");
          name.className = "item-name";
          name.textContent = shortItemName(meta.name);
          cell.appendChild(name);
        }
        if (max > 1) {
          const cnt = document.createElement("span");
          cnt.className = "item-count";
          cnt.textContent = `${Math.min(n, max)}/${max}`;
          cell.appendChild(cnt);
        }
        rowEl.appendChild(cell);
      }
      if (rowEl.childNodes.length) {
        els.itemGrid.appendChild(rowEl);
      }
    }
  }

  function bossListSortKey(boss) {
    // 0 = in-logic unbeaten (top), 1 = out-of-logic unbeaten, 2 = beaten (bottom)
    if (Boolean(boss.beaten)) return 2;
    if (Boolean(boss.in_logic)) return 0;
    return 1;
  }

  function renderBosses() {
    if (!els.bossList) return;
    const bosses = Array.isArray(status.bosses) ? status.bosses.slice() : [];
    bosses.sort((a, b) => bossListSortKey(a) - bossListSortKey(b));
    els.bossList.innerHTML = "";
    if (!bosses.length) {
      const li = document.createElement("li");
      li.className = "muted";
      li.textContent = status.ap_connected
        ? "Waiting for boss status…"
        : "Connect to see bosses";
      els.bossList.appendChild(li);
      return;
    }
    for (const boss of bosses) {
      const li = document.createElement("li");
      const beaten = Boolean(boss.beaten);
      const inLogic = Boolean(boss.in_logic);
      if (beaten) li.classList.add("beaten");
      else if (inLogic) li.classList.add("in-logic");
      const mark = document.createElement("span");
      mark.className = "mark";
      mark.textContent = beaten ? "✓" : inLogic ? "●" : "";
      const label = document.createElement("span");
      label.textContent = boss.name || boss.key || "?";
      li.title = beaten
        ? "Beaten"
        : inLogic
          ? "In logic (reachable)"
          : "Not yet in logic";
      li.appendChild(mark);
      li.appendChild(label);
      els.bossList.appendChild(li);
    }
  }

  function renderRegionTabs() {
    els.regionTabs.innerHTML = "";
    const regions = catalog.regions || [];
    const tabs = ["ALL", ...regions];
    if (!tabs.includes(activeRegion) && tabs.length) {
      activeRegion = tabs[0];
    }
    for (const region of tabs) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = region === "ALL" ? "All" : region;
      if (region === "ALL") btn.classList.add("tab-all");
      if (region === activeRegion) btn.classList.add("active");
      btn.addEventListener("click", () => {
        activeRegion = region;
        renderRegionTabs();
        renderLocations();
      });
      els.regionTabs.appendChild(btn);
    }
  }

  function renderLocations() {
    const checked = new Set(
      (status.checked_location_ids || []).map((x) => Number(x))
    );
    const inLogic = new Set(
      (status.in_logic_location_ids || []).map((x) => Number(x))
    );
    const isAll = activeRegion === "ALL";
    const bucketOf = (loc) => {
      const id = Number(loc.id);
      return checked.has(id) ? 2 : inLogic.has(id) ? 0 : 1;
    };

    let locs = isAll
      ? (catalog.locations || []).slice()
      : (catalog.locations || []).filter((l) => l.region === activeRegion);

    // In-logic unchecked first, then other unchecked, then checked.
    // In the ALL view, each of those groups is further split by region.
    locs = locs.slice().sort((a, b) => {
      const ac = bucketOf(a);
      const bc = bucketOf(b);
      if (ac !== bc) return ac - bc;
      if (isAll) {
        const ar = regionSortIndex(a.region);
        const br = regionSortIndex(b.region);
        if (ar !== br) return ar - br;
      }
      return String(a.name).localeCompare(String(b.name));
    });

    const done = locs.filter((l) => checked.has(Number(l.id))).length;
    const logicHere = locs.filter(
      (l) => inLogic.has(Number(l.id)) && !checked.has(Number(l.id))
    ).length;
    els.regionTitle.textContent = isAll ? "All Regions" : activeRegion;
    els.regionCounts.textContent = `${logicHere} in logic · ${done} / ${locs.length} checked`;
    els.locList.innerHTML = "";

    let lastGroupKey = null;
    for (const loc of locs) {
      const id = Number(loc.id);
      const isChecked = checked.has(id);
      const isLogic = inLogic.has(id);

      if (isAll) {
        const groupKey = `${bucketOf(loc)}::${loc.region}`;
        if (groupKey !== lastGroupKey) {
          lastGroupKey = groupKey;
          const sep = document.createElement("li");
          sep.className = "region-sep";
          sep.textContent = loc.region;
          els.locList.appendChild(sep);
        }
      }

      const li = document.createElement("li");
      if (isChecked) li.classList.add("checked");
      else if (isLogic) li.classList.add("in-logic");
      const mark = document.createElement("span");
      mark.className = "mark";
      mark.textContent = isChecked ? "✓" : isLogic ? "●" : "";
      const label = document.createElement("span");
      // Drop leading "Region - " for readability
      const labelRegion = isAll ? loc.region : activeRegion;
      const short = String(loc.name).replace(
        new RegExp(`^${escapeRegExp(labelRegion)}\\s*-\\s*`),
        ""
      );
      label.textContent = short;
      li.appendChild(mark);
      li.appendChild(label);
      els.locList.appendChild(li);
    }
  }

  function renderMeta() {
    const on = Boolean(status.ap_connected);
    els.conn.dataset.state = on ? "on" : "off";
    els.conn.textContent = on ? "AP connected" : "AP offline";
    els.slot.textContent = status.slot || "—";
    const totalLocs = (catalog.locations || []).length;
    const checked = status.checked_locations ?? (status.checked_location_ids || []).length;
    const items = status.items_received ?? (status.received_items || []).length;
    const inLogic = status.in_logic_count ?? (status.in_logic_location_ids || []).length;
    const logicItems = status.logic_item_count ?? 0;
    const start = status.logic_start ? ` · start ${status.logic_start}` : "";
    let text = `${items} AP · ${logicItems} inv · ${inLogic} in logic · ${checked} / ${totalLocs} checks${start}`;
    if (status.logic_error) {
      text += ` · logic err: ${status.logic_error}`;
    }
    els.counts.textContent = text;
  }

  function renderAll() {
    if (!catalog) return;
    renderMeta();
    renderItems();
    renderBosses();
    renderRegionTabs();
    renderLocations();
  }

  function applyStatus(st) {
    if (!st) return;
    status = { ...status, ...st };
    renderAll();
  }

  async function init() {
    catalog = await window.dreadTracker.getCatalog();
    if (catalog.error) {
      els.itemGrid.textContent = `Catalog missing: ${catalog.error}\nRun: py -3.11 tools/build_dread_tracker_catalog.py`;
      return;
    }
    buildLookups();
    const st = await window.dreadTracker.getStatus();
    applyStatus(st);
    window.dreadTracker.onUpdate((payload) => applyStatus(payload));
  }

  init().catch((err) => {
    els.itemGrid.textContent = String(err);
  });
})();
