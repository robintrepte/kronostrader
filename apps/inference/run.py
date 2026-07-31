"""Start Kronos inference — loads root .env and vendor PYTHONPATH automatically."""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor" / "kronos"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.inference_host,
        port=settings.inference_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
