"""
FastAPI web server — management API + WebSocket live stats + static UI.
"""

import asyncio
import json
import logging
import os
import shutil
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("web")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def create_app(manager) -> FastAPI:
    app = FastAPI(title="NDI Generator", version="1.0.0")

    # ── Static files ──────────────────────────────────────────────────────
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ── Root — serve UI ───────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def root():
        idx = static_dir / "index.html"
        if idx.exists():
            return idx.read_text(encoding="utf-8")
        return HTMLResponse("<h1>NDI Generator — static/index.html not found</h1>")

    # ── Options ───────────────────────────────────────────────────────────
    @app.get("/api/options")
    async def get_options():
        return manager.get_options()

    # ── Channels list ─────────────────────────────────────────────────────
    @app.get("/api/channels")
    async def get_channels():
        return manager.get_all_status()

    # ── Single channel ────────────────────────────────────────────────────
    @app.get("/api/channels/{idx}")
    async def get_channel(idx: int):
        try:
            rows = manager.get_all_status()
            return rows[idx]
        except IndexError:
            raise HTTPException(404, "Channel not found")

    @app.patch("/api/channels/{idx}")
    async def patch_channel(idx: int, body: dict):
        try:
            manager.update_channel(idx, body)
            return {"ok": True}
        except IndexError:
            raise HTTPException(404, "Channel not found")
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.post("/api/channels/{idx}/restart")
    async def restart_channel(idx: int):
        try:
            manager.restart_channel(idx)
            return {"ok": True}
        except IndexError:
            raise HTTPException(404, "Channel not found")

    # ── Image upload ──────────────────────────────────────────────────────
    @app.post("/api/channels/{idx}/upload")
    async def upload_image(idx: int, file: UploadFile = File(...)):
        try:
            ext  = Path(file.filename).suffix.lower()
            if ext not in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"):
                raise HTTPException(400, f"Unsupported file type: {ext}")

            dest = UPLOAD_DIR / f"ch{idx}{ext}"
            with dest.open("wb") as f:
                shutil.copyfileobj(file.file, f)

            manager.update_channel(idx, {"source": "image", "image_path": str(dest)})
            return {"ok": True, "path": str(dest)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── System info ───────────────────────────────────────────────────────
    @app.get("/api/system")
    async def system_info():
        info: dict = {"gpu": False, "gpu_name": None, "cpu_count": os.cpu_count()}
        try:
            import subprocess
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0 and r.stdout.strip():
                parts = r.stdout.strip().split(",")
                info["gpu"] = True
                info["gpu_name"] = parts[0].strip()
                info["gpu_memory_mb"] = int(parts[1].strip()) if len(parts) > 1 else None
        except Exception:
            pass
        return info

    # ── WebSocket — live stats push ───────────────────────────────────────
    _clients: list[WebSocket] = []

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        _clients.append(ws)
        log.debug(f"WS client connected ({len(_clients)} total)")
        try:
            while True:
                # Echo any message back (keep-alive ping support)
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            _clients.remove(ws)

    # Background task: push stats to all WS clients every second
    @app.on_event("startup")
    async def _start_stats_push():
        async def pusher():
            while True:
                await asyncio.sleep(1)
                if not _clients:
                    continue
                data = json.dumps(manager.get_all_status())
                dead = []
                for ws in list(_clients):
                    try:
                        await ws.send_text(data)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    if ws in _clients:
                        _clients.remove(ws)

        asyncio.create_task(pusher())

    return app
