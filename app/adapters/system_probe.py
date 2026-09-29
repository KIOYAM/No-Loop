"""Hardware probe + local-LLM usability verdict (user request 2026-09-29).

One-shot, dependency-free inspection of the machine so the UI can *suggest*
(but never install) a small capable local model. Everything here is read-only
and runs in well under a second; the GPU query is the only subprocess and it
is bounded by a short timeout with an honest fallback.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

__all__ = ["hardware_profile", "diagnose"]

_GPU_TIMEOUT_S = 5.0


class _MemoryStatus(ctypes.Structure):  # noqa: N801 - mirrors Win32 MEMORYSTATUSEX
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _ram_gb() -> tuple[float, float]:
    """(total, available) in GiB — Windows first, portable fallback elsewhere."""
    if platform.system() == "Windows":
        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # Windows only
            return (
                round(status.ullTotalPhys / 1024**3, 1),
                round(status.ullAvailPhys / 1024**3, 1),
            )
    sysconf = getattr(os, "sysconf", None)
    if sysconf is not None:
        try:
            pages = sysconf("SC_PHYS_PAGES")
            page_size = sysconf("SC_PAGE_SIZE")
            return (round(pages * page_size / 1024**3, 1), 0.0)
        except (ValueError, OSError, AttributeError):  # pragma: no cover - non-Windows
            pass
    return (0.0, 0.0)


def _gpus() -> list[dict[str, Any]]:
    """NVIDIA GPUs via ``nvidia-smi`` (fast, no dependency); others are best-effort."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                exe,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=_GPU_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    gpus: list[dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2 and parts[0]:
            gpus.append(
                {
                    "name": parts[0],
                    "vram_mb": int(parts[1]) if parts[1].isdigit() else None,
                    "driver": parts[2] if len(parts) > 2 else None,
                }
            )
    return gpus


def _free_gb(path: str) -> float | None:
    try:
        return round(shutil.disk_usage(path).free / 1024**3, 1)
    except OSError:  # pragma: no cover - drive absent
        return None


def hardware_profile() -> dict[str, Any]:
    """Everything the Settings → AI page shows under 'This machine'."""
    total, available = _ram_gb()
    gpus = _gpus()
    vram_mb = max((g.get("vram_mb") or 0 for g in gpus), default=0)
    project_drive = str(Path.cwd().drive or "C:")
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "cpu": platform.processor() or platform.machine(),
        "cores": os.cpu_count() or 0,
        "ram_total_gb": total,
        "ram_free_gb": available,
        "vram_mb": vram_mb or None,
        "gpus": gpus,
        "disk_free_gb": {
            "project": _free_gb(project_drive),
            "home": _free_gb(Path.home().drive or "C:"),
        },
    }


def _verdict(vram_mb: int, ram_gb: float, disk_free: float | None) -> dict[str, Any]:
    """Suggest (never install) a small-but-capable model band for this machine."""
    warnings: list[str] = []
    if disk_free is not None and disk_free < 6:
        warnings.append(
            f"Only {disk_free} GB free on the working drive — a 4-bit 3B model needs ~2.5 GB."
        )
    if ram_gb and ram_gb < 8:
        warnings.append("Under 8 GB RAM: prefer a 1-2B quantised model, or cloud (BYOK) only.")

    if vram_mb >= 7000:
        band, models = "excellent", ["qwen3:8b", "llama3.1:8b"]
    elif vram_mb >= 3800:
        band, models = "good", ["qwen3:4b", "llama3.2:3b"]
    elif vram_mb >= 2500:
        band, models = "fair", ["llama3.2:3b", "qwen2.5:3b"]
    elif ram_gb >= 14:
        band, models = "fair", ["llama3.2:3b", "qwen2.5:1.5b"]
    elif ram_gb >= 8:
        band, models = "limited", ["qwen2.5:1.5b", "llama3.2:1b"]
    else:
        band, models = "insufficient", []
        warnings.append(
            "Below the 8 GB baseline: local LLM stays disabled (rule-based + Gemini still work)."
        )

    return {
        "usable": bool(models),
        "band": band,
        "recommended_models": models,
        "quantisation": "Q4_K_M (quality/size balance)",
        "expected_speed": (
            "~15-40 tok/s on GPU offload" if vram_mb >= 3800 else "~5-15 tok/s CPU-only"
        ),
        "warnings": warnings,
        # Suggestion only — No_Loop never installs anything (binding principle 1).
        "suggestion": {
            "note": "Suggestion only — nothing is installed by No_Loop.",
            "ollama": "ollama pull qwen3:4b" if models else "",
            "llama_cpp": (
                "llama-server -m <path-to-model.gguf> -ngl 99 --port 8080" if models else ""
            ),
        },
    }


def diagnose() -> dict[str, Any]:
    """Combined probe used by ``GET /api/system/diagnose`` and the AI settings page."""
    hw = hardware_profile()
    disk_free = (hw.get("disk_free_gb") or {}).get("project")
    verdict = _verdict(int(hw.get("vram_mb") or 0), float(hw.get("ram_total_gb") or 0), disk_free)
    return {"hardware": hw, "local_llm": verdict}
