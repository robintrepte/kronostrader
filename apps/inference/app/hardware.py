from __future__ import annotations

from typing import Any


def collect_hardware(device: str) -> dict[str, Any]:
    """Best-effort host + model device stats for /health."""
    info: dict[str, Any] = {
        "device": device,
        "cpuPercent": None,
        "cpuCount": None,
        "ramUsedGb": None,
        "ramTotalGb": None,
        "processRssGb": None,
        "cudaAvailable": False,
        "cudaDeviceName": None,
        "cudaMemoryAllocatedGb": None,
        "cudaMemoryReservedGb": None,
    }

    try:
        import os

        info["cpuCount"] = os.cpu_count()
    except Exception:
        pass

    try:
        import psutil

        info["cpuPercent"] = psutil.cpu_percent(interval=0.05)
        vm = psutil.virtual_memory()
        info["ramUsedGb"] = round(vm.used / (1024**3), 2)
        info["ramTotalGb"] = round(vm.total / (1024**3), 2)
        info["processRssGb"] = round(psutil.Process().memory_info().rss / (1024**3), 2)
    except Exception:
        # Fallback without psutil: process RSS via resource / Windows ctypes skip
        try:
            import resource

            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # Linux is KB; macOS is bytes — treat large values as bytes
            if rss > 10_000_000:
                info["processRssGb"] = round(rss / (1024**3), 2)
            else:
                info["processRssGb"] = round(rss / (1024**2), 2)
        except Exception:
            pass

    try:
        import torch

        info["cudaAvailable"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            idx = torch.cuda.current_device()
            info["cudaDeviceName"] = torch.cuda.get_device_name(idx)
            info["cudaMemoryAllocatedGb"] = round(
                torch.cuda.memory_allocated(idx) / (1024**3), 3
            )
            info["cudaMemoryReservedGb"] = round(
                torch.cuda.memory_reserved(idx) / (1024**3), 3
            )
    except Exception:
        pass

    return info
