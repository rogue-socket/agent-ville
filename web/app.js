const canvas = document.getElementById("village");
const ctx = canvas.getContext("2d");

// --- State ---
let agents = [];       // visual agents with x, y, vx, vy
let state = null;      // last server state
let selected = null;   // selected agent id
let isRunning = false;

// --- Agent visuals keyed by id ---
const visuals = new Map();

function resizeCanvas() {
  canvas.width = canvas.clientWidth * devicePixelRatio;
  canvas.height = canvas.clientHeight * devicePixelRatio;
  ctx.scale(devicePixelRatio, devicePixelRatio);
}
window.addEventListener("resize", resizeCanvas);
resizeCanvas();

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
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  const alive = new Set();

  for (const a of state.agents) {
    alive.add(a.id);
    if (!visuals.has(a.id)) {
      // New agent — spawn at random position
      visuals.set(a.id, {
        x: Math.random() * w * 0.85 + w * 0.05,
        y: Math.random() * h * 0.85 + h * 0.05,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        opacity: 0,        // fade in
        targetOpacity: 1,
        data: a,
      });
    } else {
      visuals.get(a.id).data = a;
    }
  }

  // Mark dead agents for fade-out
  for (const [id, v] of visuals) {
    if (!alive.has(id)) {
      v.targetOpacity = 0;
    }
  }
}

// --- Update header + event log ---
function updateUI() {
  if (!state) return;

  document.getElementById("gen").textContent = state.generation;
  document.getElementById("pop").textContent = state.agents.length;
  document.getElementById("deaths").textContent = state.graveyard_size;

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
    `born: gen ${a.generation_born}`,
    `trait: ${a.dominant_trait}`,
  ].join("<br>");

  const pDiv = document.getElementById("agent-personality");
  const traitHues = { curiosity: 45, aggression: 0, caution: 210, sociability: 120, creativity: 280 };
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
    `style: ${a.genome.style}`,
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

// --- Canvas click ---
canvas.addEventListener("click", (e) => {
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;

  let closest = null;
  let closestDist = Infinity;
  for (const [id, v] of visuals) {
    if (v.targetOpacity === 0) continue;
    const dx = v.x - mx;
    const dy = v.y - my;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < closestDist && dist < 30) {
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
function render() {
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  ctx.clearRect(0, 0, w, h);

  // Subtle grid
  ctx.strokeStyle = "rgba(30, 30, 46, 0.3)";
  ctx.lineWidth = 0.5;
  for (let x = 0; x < w; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
  }
  for (let y = 0; y < h; y += 40) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }

  // Update & draw agents
  const toRemove = [];
  for (const [id, v] of visuals) {
    // Physics — gentle brownian motion
    v.vx += (Math.random() - 0.5) * 0.15;
    v.vy += (Math.random() - 0.5) * 0.15;
    v.vx *= 0.95;
    v.vy *= 0.95;

    // Personality affects movement
    if (v.data) {
      const p = v.data.personality;
      const speedMul = 0.5 + p.curiosity;
      v.vx *= speedMul;
      v.vy *= speedMul;
    }

    v.x += v.vx;
    v.y += v.vy;

    // Bounce off walls
    const margin = 20;
    if (v.x < margin) { v.x = margin; v.vx *= -1; }
    if (v.x > w - margin) { v.x = w - margin; v.vx *= -1; }
    if (v.y < margin) { v.y = margin; v.vy *= -1; }
    if (v.y > h - margin) { v.y = h - margin; v.vy *= -1; }

    // Animate opacity
    v.opacity += (v.targetOpacity - v.opacity) * 0.08;
    if (v.targetOpacity === 0 && v.opacity < 0.01) {
      toRemove.push(id);
      continue;
    }

    // Draw
    const a = v.data;
    if (!a) continue;

    const radius = 6 + a.fitness * 14;
    const hue = a.hue;
    const saturation = 60 + a.fitness * 20;
    const lightness = 45 + a.fitness * 15;

    // Glow
    ctx.save();
    ctx.globalAlpha = v.opacity * 0.25;
    ctx.beginPath();
    ctx.arc(v.x, v.y, radius + 8, 0, Math.PI * 2);
    ctx.fillStyle = `hsl(${hue}, ${saturation}%, ${lightness}%)`;
    ctx.fill();

    // Body
    ctx.globalAlpha = v.opacity * 0.85;
    ctx.beginPath();
    ctx.arc(v.x, v.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = `hsl(${hue}, ${saturation}%, ${lightness}%)`;
    ctx.fill();

    // Selection ring
    if (id === selected) {
      ctx.globalAlpha = v.opacity;
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(v.x, v.y, radius + 4, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Name label
    ctx.globalAlpha = v.opacity * 0.7;
    ctx.fillStyle = "#c8c8d4";
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    ctx.fillText(a.name, v.x, v.y + radius + 14);

    ctx.restore();
  }

  for (const id of toRemove) visuals.delete(id);

  requestAnimationFrame(render);
}

// --- Controls ---
document.getElementById("btn-toggle").addEventListener("click", toggle);
document.getElementById("btn-step").addEventListener("click", step);
document.getElementById("speed").addEventListener("input", (e) => {
  fetch(`/api/speed?value=${e.target.value}`, { method: "POST" });
});

document.addEventListener("keydown", (e) => {
  if (e.code === "Space") { e.preventDefault(); toggle(); }
  if (e.code === "ArrowRight") { e.preventDefault(); step(); }
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
setInterval(fetchState, 800);
render();
