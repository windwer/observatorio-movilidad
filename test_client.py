"""Loopback integration client for the pinned Starlette/httpx combination."""
from __future__ import annotations

import atexit
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

_PROCESS = None


def _stop_process():
    global _PROCESS
    if _PROCESS is not None and _PROCESS.poll() is None:
        _PROCESS.terminate()
        try:
            _PROCESS.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _PROCESS.kill()
    _PROCESS = None


atexit.register(_stop_process)


class TestClient:
    def __init__(self, application, base_url: str = "http://testserver"):
        del application, base_url
        global _PROCESS
        _stop_process()
        import app as app_module

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        env = os.environ.copy()
        env.update({
            "OBS_DB": str(app_module.DB),
            "OBS_GEOGRAPHY_DIR": str(Path(app_module.DB).parent / "geography"),
            "OBS_HOST": "127.0.0.1",
            "OBS_PORT": str(port),
            "OBS_PUBLIC_READ": "1",
            "OBS_IMMUTABLE_DATA": "0",
        })
        if app_module.PASSWORD:
            env["OBS_PASSWORD"] = app_module.PASSWORD
        else:
            env.pop("OBS_PASSWORD", None)
        _PROCESS = subprocess.Popen(
            [sys.executable, "app.py"], cwd=Path(__file__).resolve().parent,
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and _PROCESS.poll() is None:
            try:
                httpx.get(self.base_url + "/api/health", timeout=.5)
                return
            except httpx.HTTPError:
                time.sleep(.05)
        raise RuntimeError("El servidor HTTP aislado de pruebas no arrancó")

    def request(self, method: str, url: str, **kwargs):
        return httpx.request(method, self.base_url + url, timeout=30, **kwargs)

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)
