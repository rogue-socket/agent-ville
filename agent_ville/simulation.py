from __future__ import annotations

import json
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

from .village import Village

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class SimulationState:
    def __init__(self, village: Village):
        self.village = village
        self.running = False
        self.speed = 1.0  # generations per second
        self._lock = threading.Lock()

    def step(self) -> None:
        with self._lock:
            self.village.step()

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return self.village.get_state()

    def toggle(self) -> bool:
        self.running = not self.running
        return self.running


def simulation_loop(state: SimulationState) -> None:
    """Background thread that advances the simulation."""
    while True:
        if state.running:
            state.step()
        interval = 1.0 / max(0.1, state.speed)
        time.sleep(interval)


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
    village = Village(population_size=15)
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
