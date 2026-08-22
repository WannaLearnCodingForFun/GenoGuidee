"""Automatic hardware detection (section 55). Torch-free by default."""
from __future__ import annotations

import os
import platform
from typing import Any


def detect() -> dict[str, Any]:
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "mkl_num_threads": os.environ.get("MKL_NUM_THREADS"),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "device": "cpu",
        "torch": None,
    }
    try:
        import torch  # optional dependency

        info["torch"] = torch.__version__
        if torch.cuda.is_available():
            info["device"] = "cuda"
            info["cuda_device_name"] = torch.cuda.get_device_name(0)
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            info["device"] = "mps"
    except ImportError:
        if platform.machine() == "arm64" and platform.system() == "Darwin":
            info["device_note"] = "Apple Silicon detected; MPS usable once torch is installed"
    return info
