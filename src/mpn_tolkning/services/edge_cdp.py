from __future__ import annotations

import base64
import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import websocket


class EdgeCdpError(RuntimeError):
    pass


class EdgeCdpTimeout(TimeoutError):
    pass


def find_edge_executable() -> Path:
    discovered = shutil.which("msedge")
    candidates = [Path(discovered)] if discovered else []
    for name in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        if root := os.environ.get(name):
            candidates.append(Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise EdgeCdpError("Microsoft Edge was not found on this workstation.")


def build_edge_arguments(
    executable: Path, profile: Path, port: int, *, background: bool
) -> list[str]:
    origin = f"http://127.0.0.1:{port}"
    arguments = [
        str(executable),
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-allow-origins={origin}",
        f"--user-data-dir={profile}",
        "--window-size=1440,1000",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        "--disable-features=msEdgeStartupBoost",
        "--disable-session-crashed-bubble",
        "--new-window",
        "about:blank",
    ]
    if background:
        arguments[1:1] = [
            "--start-minimized",
            "--window-position=-32000,-32000",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
        ]
    return arguments


class EdgeCdpSession:
    """Small direct Microsoft Edge DevTools client with one profile per provider."""

    def __init__(self, profile_root: Path, *, background: bool = True, timeout_ms: int = 45_000):
        self.profile_root = Path(profile_root)
        self.background = background
        self.timeout_ms = timeout_ms
        self.profile_directory: Path | None = None
        self._process: subprocess.Popen | None = None
        self._socket = None
        self._next_id = 1
        self._endpoint = ""

    def start(self, provider: str) -> None:
        self.close()
        safe_name = re.sub(r"[^a-z0-9]+", "-", provider.lower()).strip("-") or "provider"
        self.profile_directory = self.profile_root / safe_name
        self.profile_directory.mkdir(parents=True, exist_ok=True)
        self._launch(self.profile_directory)

    def _launch(self, profile: Path) -> None:
        port = _reserve_local_port()
        self._endpoint = f"http://127.0.0.1:{port}"
        self._process = subprocess.Popen(
            build_edge_arguments(find_edge_executable(), profile.resolve(), port, background=self.background),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        deadline = time.monotonic() + min(20, self.timeout_ms / 1000)
        version = None
        while time.monotonic() < deadline:
            try:
                version = _http_json(f"{self._endpoint}/json/version", timeout=1)
                break
            except EdgeCdpError:
                if self._process.poll() is not None:
                    break
                time.sleep(0.15)
        if not version:
            self.close()
            raise EdgeCdpTimeout("Edge DevTools endpoint did not become available.")
        target = _http_json(f"{self._endpoint}/json/new?about:blank", method="PUT", timeout=3)
        websocket_url = target.get("webSocketDebuggerUrl") or version.get("webSocketDebuggerUrl")
        try:
            self._socket = websocket.create_connection(
                websocket_url,
                timeout=self.timeout_ms / 1000,
                origin=self._endpoint,
                enable_multithread=False,
            )
        except Exception as exc:
            self.close()
            raise EdgeCdpError(f"Could not connect to Edge DevTools: {exc}") from exc
        self._call("Page.enable")
        self._call("Runtime.enable")

    def _call(self, method: str, params: dict[str, Any] | None = None) -> dict:
        if self._socket is None:
            raise EdgeCdpError("Edge session is not started.")
        command_id = self._next_id
        self._next_id += 1
        payload = {"id": command_id, "method": method}
        if params:
            payload["params"] = params
        self._socket.send(json.dumps(payload))
        deadline = time.monotonic() + self.timeout_ms / 1000
        while time.monotonic() < deadline:
            try:
                message = json.loads(self._socket.recv())
            except websocket.WebSocketTimeoutException as exc:
                raise EdgeCdpTimeout(f"Edge timed out during {method}.") from exc
            if message.get("id") != command_id:
                continue
            if error := message.get("error"):
                raise EdgeCdpError(f"Edge rejected {method}: {error.get('message', error)}")
            return dict(message.get("result") or {})
        raise EdgeCdpTimeout(f"Edge timed out during {method}.")

    def navigate(self, url: str) -> None:
        result = self._call("Page.navigate", {"url": url})
        if result.get("errorText"):
            raise EdgeCdpError(str(result["errorText"]))
        deadline = time.monotonic() + self.timeout_ms / 1000
        while time.monotonic() < deadline:
            if self.evaluate("document.readyState") in {"interactive", "complete"}:
                return
            time.sleep(0.08)
        raise EdgeCdpTimeout(f"Edge did not finish navigating to {url}.")

    def evaluate(self, expression: str) -> object:
        result = self._call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True, "userGesture": True},
        )
        if result.get("exceptionDetails"):
            raise EdgeCdpError("JavaScript evaluation failed in Edge.")
        return result.get("result", {}).get("value")

    def screenshot(self, path: Path, clip: dict | None = None) -> Path:
        params: dict[str, Any] = {"format": "png", "fromSurface": True, "captureBeyondViewport": bool(clip)}
        if clip:
            params["clip"] = {**clip, "scale": 1}
        result = self._call("Page.captureScreenshot", params)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(result["data"]))
        return path

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._call("Browser.close")
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        if self._process is not None:
            try:
                self._process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self._process.terminate()
            self._process = None


def _reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _http_json(url: str, *, method: str = "GET", timeout: float = 3) -> Any:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise EdgeCdpError(f"Edge DevTools endpoint failed: {exc}") from exc
