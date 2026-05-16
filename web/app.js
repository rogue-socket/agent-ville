const canvas = document.getElementById("village");
const ctx = canvas.getContext("2d");

// --- State ---
let agents = [];       // visual agents with x, y, vx, vy
let state = null;      // last server state
let selected = null;   // selected agent id
let isRunning = false;

// --- Agent visuals keyed by id ---
const visuals = new Map();

// Canvas fills its wrap; we apply our own viewport (zoom + pan) instead of
// browser scrolling so the user can zoom in on regions without the canvas
// hitting the browser's 8k×4.8k pixel limit at extreme scales.
const canvasWrap = document.getElementById("canvas-wrap");

// World→canvas scaling. Updated from /api/state.
let world = { width: 100, height: 60 };
let worldMap = null;  // { cols, rows, tiles[r][c], colors{name: hex} }

// Viewport state.
// `baseScale` fits the whole world into the canvas at zoom=1.
// `zoom` is the user multiplier; `panX`/`panY` are the canvas-pixel offset of world (0,0).
let baseScale = 1;
const viewport = { zoom: 1, panX: 0, panY: 0 };

function setupCanvas() {
  const cssW = canvasWrap.clientWidth;
  const cssH = canvasWrap.clientHeight;
  const dpr = Math.min(devicePixelRatio || 1, 2);
  canvas.style.width = cssW + "px";
  canvas.style.height = cssH + "px";
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.scale(dpr, dpr);
}

function fitView() {
  const cssW = canvas.clientWidth;
  const cssH = canvas.clientHeight;
  baseScale = Math.min(cssW / world.width, cssH / world.height);
  viewport.zoom = 1;
  viewport.panX = (cssW - world.width * baseScale) / 2;
  viewport.panY = (cssH - world.height * baseScale) / 2;
}

setupCanvas();
fitView();
window.addEventListener("resize", () => { setupCanvas(); fitView(); });

function worldToCanvas(wx, wy) {
  const s = baseScale * viewport.zoom;
  return { x: wx * s + viewport.panX, y: wy * s + viewport.panY };
}

// --- Polling ---
async function fetchState() {
  try {
    const res = await fetch("/api/state");
    state = await res.json();
    syncAgents();
    updateUI();
  } catch (e) { /* server not ready */ }
}

function syncAgents() {
  if (!state) return;
  if (state.world) {
    const hadWorld = world && world.width !== 100;
    world = state.world;
    if (state.world.map) worldMap = state.world.map;
    // First time we learn the real world dims, refit so the whole map shows.
    if (!hadWorld) fitView();
  }
  const alive = new Set();

  for (const a of state.agents) {
    alive.add(a.id);
    if (!visuals.has(a.id)) {
      // Visuals store *world* coords so the viewport (zoom/pan) can change
      // mid-run without stranding them. Render does the canvas conversion.
      visuals.set(a.id, {
        wx: a.x, wy: a.y,
        targetWx: a.x, targetWy: a.y,
        opacity: 0,
        targetOpacity: 1,
        data: a,
      });
    } else {
      const v = visuals.get(a.id);
      v.targetWx = a.x;
      v.targetWy = a.y;
      v.data = a;
    }
  }

  for (const [id, v] of visuals) {
    if (!alive.has(id)) v.targetOpacity = 0;
  }
}

// --- Update header + event log ---
function updateUI() {
  if (!state) return;

  document.getElementById("gen").textContent = state.generation;
  document.getElementById("pop").textContent = state.agents.length;
  document.getElementById("deaths").textContent = state.graveyard_size;
  const meanAge = state.mortality && state.mortality.mean_death_age;
  document.getElementById("mean-death-age").textContent =
    (state.mortality && state.mortality.recent_death_ages.length)
      ? meanAge.toFixed(1)
      : "—";

  const fitnesses = state.agents.map(a => a.fitness);
  const avg = fitnesses.length
    ? (fitnesses.reduce((s, v) => s + v, 0) / fitnesses.length).toFixed(2)
    : "—";
  document.getElementById("fit").textContent = avg;

  // Event log
  const log = document.getElementById("event-log");
  log.innerHTML = state.events
    .slice()
    .reverse()
    .slice(0, 30)
    .map(e => {
      return `<div class="event ${e.kind}"><span class="gen">gen ${e.generation}</span><span class="kind">${e.kind}</span> ${e.agent_name}: ${e.detail}</div>`;
    })
    .join("");

  // Inspector
  if (selected) {
    const a = state.agents.find(a => a.id === selected);
    if (a) renderInspector(a);
    else clearInspector();
  }
}

function renderInspector(a) {
  document.getElementById("inspector-empty").classList.add("hidden");
  document.getElementById("inspector-content").classList.remove("hidden");
  document.getElementById("agent-name").textContent = a.name;
  document.getElementById("agent-name").style.color = `hsl(${a.hue}, 70%, 65%)`;

  document.getElementById("agent-meta").innerHTML = [
    `age: ${a.age} / ${a.max_age}`,
    `fitness: ${a.fitness.toFixed(3)}`,
    `flourishing: ${(a.flourishing ?? 0).toFixed(3)}`,
    `pursuit: ${a.current_pursuit ?? "—"}`,
    `born: gen ${a.generation_born}`,
    `trait: ${a.dominant_trait}`,
    `biome: ${a.biome || "—"}`,
    `mortality pressure: ${(a.mortality_pressure ?? 0).toFixed(2)}`,
    `deaths witnessed: ${(a.deaths_witnessed_recent ?? 0).toFixed(1)}`,
  ].join("<br>");

  // Sixfold need bars. Despair_streak is hidden inside psyche but worth surfacing.
  const needsDiv = document.getElementById("agent-needs");
  const needHues = { body: 10, safety: 200, belonging: 130, esteem: 50, becoming: 280, beyond: 320 };
  const needs = a.psyche || {};
  const needOrder = ["body", "safety", "belonging", "esteem", "becoming", "beyond"];
  const dominant = a.current_pursuit;
  needsDiv.innerHTML = needOrder.map(n => {
    const v = needs[n] ?? 0;
    const hue = needHues[n];
    const cls = (n === dominant) ? " dominant" : "";
    return `<div class="trait-bar${cls}">
      <span class="label">${n}</span>
      <div class="bar"><div class="bar-fill" style="width:${v * 100}%;background:hsl(${hue},65%,55%)"></div></div>
      <span class="value">${v.toFixed(2)}</span>
    </div>`;
  }).join("") + (needs.despair_streak > 0 ? `<div class="trait-bar" style="opacity:0.7;color:#ff9b6b;font-size:10px;">despair streak: ${needs.despair_streak}</div>` : "");

  const pDiv = document.getElementById("agent-personality");
  const traitHues = { curiosity: 45, aggression: 0, caution: 210, sociability: 120, creativity: 280, will_to_live: 170 };
  pDiv.innerHTML = Object.entries(a.personality)
    .map(([k, v]) => {
      const hue = traitHues[k] || 0;
      return `<div class="trait-bar">
        <span class="label">${k}</span>
        <div class="bar"><div class="bar-fill" style="width:${v * 100}%;background:hsl(${hue},60%,55%)"></div></div>
        <span class="value">${v.toFixed(2)}</span>
      </div>`;
    })
    .join("");

  document.getElementById("agent-genome").innerHTML = [
    `tools: ${a.genome.allowed_tools.join(", ")}`,
    `speed: ${a.genome.speed_vs_thoroughness.toFixed(2)}`,
    `risk: ${a.genome.risk_tolerance.toFixed(2)}`,
    a.genome.mutation_ops.length ? `mutations: ${a.genome.mutation_ops.join(", ")}` : "",
  ].filter(Boolean).join("<br>");

  // Mini fitness chart
  drawFitnessChart(a.fitness_history);
}

function drawFitnessChart(history) {
  const c = document.getElementById("fitness-chart");
  const cx = c.getContext("2d");
  cx.clearRect(0, 0, c.width, c.height);
  if (history.length < 2) return;

  cx.strokeStyle = "rgba(124, 110, 240, 0.6)";
  cx.lineWidth = 1.5;
  cx.beginPath();
  const step = c.width / (history.length - 1);
  for (let i = 0; i < history.length; i++) {
    const x = i * step;
    const y = c.height - history[i] * c.height;
    i === 0 ? cx.moveTo(x, y) : cx.lineTo(x, y);
  }
  cx.stroke();
}

function clearInspector() {
  selected = null;
  document.getElementById("inspector-empty").classList.remove("hidden");
  document.getElementById("inspector-content").classList.add("hidden");
}

// --- Mouse: drag to pan, wheel to zoom, click to inspect ---
let dragging = false;
let dragStart = null;
let dragMoved = 0;  // total |dx|+|dy| during the current drag; suppresses click if > threshold

canvas.addEventListener("mousedown", (e) => {
  dragging = true;
  dragMoved = 0;
  dragStart = { x: e.clientX, y: e.clientY, panX: viewport.panX, panY: viewport.panY };
  canvas.classList.add("dragging");
});
window.addEventListener("mousemove", (e) => {
  if (!dragging) return;
  const dx = e.clientX - dragStart.x;
  const dy = e.clientY - dragStart.y;
  viewport.panX = dragStart.panX + dx;
  viewport.panY = dragStart.panY + dy;
  dragMoved += Math.abs(e.movementX) + Math.abs(e.movementY);
});
window.addEventListener("mouseup", () => {
  dragging = false;
  canvas.classList.remove("dragging");
});

canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const oldZoom = viewport.zoom;
  const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
  viewport.zoom = Math.max(0.3, Math.min(8, oldZoom * factor));
  // Keep the world point under the cursor stationary across the zoom.
  viewport.panX = mx - (mx - viewport.panX) * (viewport.zoom / oldZoom);
  viewport.panY = my - (my - viewport.panY) * (viewport.zoom / oldZoom);
}, { passive: false });

canvas.addEventListener("click", (e) => {
  if (dragMoved > 4) return;  // it was a pan, not a click
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;

  let closest = null;
  let closestDist = Infinity;
  for (const [id, v] of visuals) {
    if (v.targetOpacity === 0) continue;
    const pos = worldToCanvas(v.wx, v.wy);
    const dx = pos.x - mx;
    const dy = pos.y - my;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < closestDist && dist < 20) {
      closest = id;
      closestDist = dist;
    }
  }
  selected = closest;
  if (selected) {
    const a = state?.agents.find(a => a.id === selected);
    if (a) renderInspector(a);
  } else {
    clearInspector();
  }
});

// --- Render loop ---
function renderBiomeMap() {
  if (!worldMap) return;
  const tileWorldW = world.width / worldMap.cols;
  const tileWorldH = world.height / worldMap.rows;
  const s = baseScale * viewport.zoom;
  const tilePxW = tileWorldW * s + 0.5;
  const tilePxH = tileWorldH * s + 0.5;
  for (let r = 0; r < worldMap.rows; r++) {
    for (let c = 0; c < worldMap.cols; c++) {
      const biome = worldMap.tiles[r][c];
      const pos = worldToCanvas(c * tileWorldW, r * tileWorldH);
      ctx.fillStyle = worldMap.colors[biome] || "#1a1a2e";
      ctx.fillRect(pos.x, pos.y, tilePxW, tilePxH);
    }
  }
}

function render() {
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  ctx.clearRect(0, 0, w, h);

  renderBiomeMap();

  // Update & draw agents
  const toRemove = [];
  for (const [id, v] of visuals) {
    // Smooth lerp in *world* coords so changing the viewport doesn't shear motion.
    v.wx += (v.targetWx - v.wx) * 0.18;
    v.wy += (v.targetWy - v.wy) * 0.18;
    const pos = worldToCanvas(v.wx, v.wy);

    // Animate opacity
    v.opacity += (v.targetOpacity - v.opacity) * 0.08;
    if (v.targetOpacity === 0 && v.opacity < 0.01) {
      toRemove.push(id);
      continue;
    }

    // Draw
    const a = v.data;
    if (!a) continue;

    const radius = 2 + a.fitness * 5;
    const hue = a.hue;
    const saturation = 60 + a.fitness * 20;
    const lightness = 45 + a.fitness * 15;

    // Glow
    ctx.save();
    ctx.globalAlpha = v.opacity * 0.2;
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, radius + 4, 0, Math.PI * 2);
    ctx.fillStyle = `hsl(${hue}, ${saturation}%, ${lightness}%)`;
    ctx.fill();

    // Body
    ctx.globalAlpha = v.opacity * 0.9;
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = `hsl(${hue}, ${saturation}%, ${lightness}%)`;
    ctx.fill();

    // Mortality ring — dying agents (high mortality_pressure) get a dark halo.
    const mort = a.mortality_pressure || 0;
    if (mort > 0.15) {
      ctx.globalAlpha = v.opacity * Math.min(0.9, mort);
      ctx.strokeStyle = "#1a0a0a";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, radius + 1.5, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Selection ring
    if (id === selected) {
      ctx.globalAlpha = v.opacity;
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, radius + 2.5, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Name label — only show on selected agent (avoid label spam at low pixel size)
    if (id === selected) {
      ctx.globalAlpha = v.opacity * 0.85;
      ctx.fillStyle = "#e0e0e8";
      ctx.font = "11px monospace";
      ctx.textAlign = "center";
      ctx.fillText(a.name, pos.x, pos.y + radius + 10);
    }

    ctx.restore();
  }

  for (const id of toRemove) visuals.delete(id);

  requestAnimationFrame(render);
}

// --- Controls ---
document.getElementById("btn-toggle").addEventListener("click", toggle);
document.getElementById("btn-step").addEventListener("click", step);
document.getElementById("btn-fit").addEventListener("click", fitView);
document.getElementById("speed").addEventListener("input", (e) => {
  fetch(`/api/speed?value=${e.target.value}`, { method: "POST" });
});

document.addEventListener("keydown", (e) => {
  if (e.code === "Space") { e.preventDefault(); toggle(); }
  if (e.code === "ArrowRight") { e.preventDefault(); step(); }
  if (e.code === "KeyF") { e.preventDefault(); fitView(); }
});

async function toggle() {
  const res = await fetch("/api/toggle", { method: "POST" });
  const data = await res.json();
  isRunning = data.running;
  document.getElementById("btn-toggle").textContent = isRunning ? "pause" : "play";
  const ind = document.getElementById("status-indicator");
  ind.textContent = isRunning ? "running" : "paused";
  ind.className = isRunning ? "running" : "paused";
}

async function step() {
  await fetch("/api/step", { method: "POST" });
  fetchState();
}

// --- Boot ---
fetchState();
setInterval(fetchState, 150);
render();
