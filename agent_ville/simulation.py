from __future__ import annotations

import json
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

from .persistence import DEFAULT_SNAPSHOT_PATH, LineageLog, load_snapshot
from .village import Village

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


MOTION_TICK_INTERVAL = 0.033  # seconds — ~30 motion ticks/sec


class SimulationState:
    def __init__(self, village: Village):
        self.village = village
        self.running = False
        self.speed = 1.0  # generations per second
        self._lock = threading.Lock()

    def step(self) -> None:
        with self._lock:
            self.village.step()

    def motion_tick(self) -> None:
        with self._lock:
            self.village.motion_tick()

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return self.village.get_state()

    def toggle(self) -> bool:
        self.running = not self.running
        return self.running


def simulation_loop(state: SimulationState) -> None:
    """Background thread.

    Motion ticks run continuously (so agents drift even while paused).
    Generation steps only run when `state.running`, gated by `state.speed`.
    """
    last_gen_time = time.monotonic()
    while True:
        state.motion_tick()
        if state.running:
            now = time.monotonic()
            gen_interval = 1.0 / max(0.1, state.speed)
            if now - last_gen_time >= gen_interval:
                state.step()
                last_gen_time = now
        time.sleep(MOTION_TICK_INTERVAL)


def make_handler(state: SimulationState):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(WEB_DIR), **kwargs)

        def do_GET(self):
            if self.path == "/api/state":
                data = state.get_state()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.write_safe(body)
                return
            super().do_GET()

        def do_POST(self):
            if self.path == "/api/step":
                state.step()
                self._json_ok({"stepped": True, "generation": state.village.generation})
            elif self.path == "/api/toggle":
                running = state.toggle()
                self._json_ok({"running": running})
            elif self.path.startswith("/api/speed"):
                try:
                    val = float(self.path.split("=")[1])
                    state.speed = max(0.1, min(10.0, val))
                except (IndexError, ValueError):
                    pass
                self._json_ok({"speed": state.speed})
            else:
                self.send_error(404)

        def _json_ok(self, data: dict) -> None:
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.write_safe(body)

        def write_safe(self, body: bytes) -> None:
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def log_message(self, format, *args):
            # Suppress per-request logging
            pass

    return Handler


def run(host: str = "localhost", port: int = 8420) -> None:
    snapshot = load_snapshot(DEFAULT_SNAPSHOT_PATH)
    if snapshot:
        # Resume: reuse the prior lineage session_id so the TSV stays linkable.
        log = LineageLog(session_id=snapshot.get("lineage_session_id"))
        village = Village.from_snapshot(snapshot, lineage_log=log)
        print(f"Resumed snapshot at generation {village.generation} (pop {sum(1 for a in village.agents if a.alive)})")
    else:
        village = Village(lineage_log=LineageLog())
    village.snapshot_path = DEFAULT_SNAPSHOT_PATH
    state = SimulationState(village)

    # Start simulation in background thread
    thread = threading.Thread(target=simulation_loop, args=(state,), daemon=True)
    thread.start()

    server = HTTPServer((host, port), make_handler(state))
    print(f"Agent-Ville running at http://{host}:{port}")
    print("Controls: space=play/pause, click=inspect agent")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
