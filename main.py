#!/usr/bin/env python3
"""
NDI Signal Generator — main entry point.

Usage:
  python main.py [--port 8080] [--host 0.0.0.0] [--mock-ndi] [--gpu]

Environment variables:
  NDI_MOCK=1        Force mock NDI (no SDK needed)
  NDI_CONFIG=path   Path to channel config JSON (default: channels.json)
  NDI_PORT=8080     Web server port
  NDI_HOST=0.0.0.0  Web server bind address
"""

import argparse
import logging
import os
import signal
import sys

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


def parse_args():
    p = argparse.ArgumentParser(description="NDI Signal Generator")
    p.add_argument("--host",     default=os.environ.get("NDI_HOST", "0.0.0.0"))
    p.add_argument("--port",     default=int(os.environ.get("NDI_PORT", "8080")), type=int)
    p.add_argument("--mock-ndi", action="store_true",
                   help="Run without NDI SDK (for testing)")
    p.add_argument("--gpu",      action="store_true",
                   help="Enable NVIDIA GPU acceleration by default")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def main():
    args = parse_args()

    logging.getLogger().setLevel(args.log_level)

    # Apply mock flag before importing ndi_wrapper
    if args.mock_ndi:
        os.environ["NDI_MOCK"] = "1"

    # ── NDI SDK init ──────────────────────────────────────────────────────
    import ndi_wrapper
    ndi_wrapper.initialize()

    # ── Channel manager ───────────────────────────────────────────────────
    from channel_manager import ChannelManager
    manager = ChannelManager()

    # Apply global GPU default
    if args.gpu:
        for i in range(manager.NUM_CHANNELS):
            manager.update_channel(i, {"use_gpu": True})

    manager.start_all()
    log.info(f"All {manager.NUM_CHANNELS} channels started")

    # ── Web server ────────────────────────────────────────────────────────
    from web_server import create_app
    app = create_app(manager)

    import uvicorn

    banner = f"""
╔══════════════════════════════════════════════════════╗
║          NDI Signal Generator  v1.0                  ║
║                                                      ║
║   Web UI  →  http://{args.host}:{args.port:<5}                    ║
║   Channels: {manager.NUM_CHANNELS}  │  NDI mock: {str(os.environ.get('NDI_MOCK','0')=='1'):<5}           ║
╚══════════════════════════════════════════════════════╝
"""
    print(banner)

    # ── Graceful shutdown ─────────────────────────────────────────────────
    def _shutdown(sig, frame):
        log.info("Shutdown signal received — stopping channels…")
        manager.stop_all()
        ndi_wrapper.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
