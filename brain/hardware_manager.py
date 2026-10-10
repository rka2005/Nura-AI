"""
Neura Hardware & GPU Compute Manager.
Manages GPU detection, prioritization (Dedicated GPU vs System / Integrated GPU),
and compute environment configuration for project testing and execution.
"""

import os
import sys
import json
import logging
import subprocess
from typing import Dict, Any, List, Optional

logger = logging.getLogger("NeuraHardwareManager")

_DETECTED_GPUS_CACHE: Optional[List[Dict[str, Any]]] = None


def get_hardware_gpus(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Discovers all GPUs present on the system.
    Identifies:
    - Dedicated GPUs (NVIDIA RTX/GTX, AMD discrete Radeon RX)
    - System / Integrated GPUs (Intel UHD/Iris, AMD Radeon Graphics, default display adapter)
    """
    global _DETECTED_GPUS_CACHE
    if _DETECTED_GPUS_CACHE is not None and not force_refresh:
        return _DETECTED_GPUS_CACHE

    gpus: List[Dict[str, Any]] = []

    # 1. Discover via PyTorch CUDA
    try:
        import torch
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                name = torch.cuda.get_device_name(i)
                props = torch.cuda.get_device_properties(i)
                vram_gb = round(props.total_memory / (1024 ** 3), 2)
                gpus.append({
                    "name": name,
                    "type": "dedicated",
                    "is_dedicated": True,
                    "cuda": True,
                    "device_index": i,
                    "vram_gb": vram_gb,
                    "source": "torch_cuda",
                })
    except Exception as e:
        logger.debug(f"Torch CUDA check skipped: {e}")

    # 2. Query Windows WMI / CimInstance Win32_VideoController
    if sys.platform == "win32":
        try:
            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Json"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                raw = json.loads(res.stdout.strip())
                items = raw if isinstance(raw, list) else [raw]
                for item in items:
                    v_name = (item.get("Name") or "").strip()
                    v_ram = item.get("AdapterRAM", 0) or 0
                    if not v_name:
                        continue

                    # If already discovered via torch CUDA, update info
                    matched = next((g for g in gpus if v_name.lower() in g["name"].lower() or g["name"].lower() in v_name.lower()), None)
                    if matched:
                        if not matched.get("vram_gb") and v_ram:
                            matched["vram_gb"] = round(v_ram / (1024 ** 3), 2)
                        continue

                    name_lower = v_name.lower()
                    is_dedicated = any(k in name_lower for k in [
                        "nvidia", "geforce", "rtx", "gtx", "quadro", "titan",
                        "radeon rx", "discrete", "dedicated"
                    ])

                    vram_gb = round(v_ram / (1024 ** 3), 2) if v_ram else 0.0

                    gpus.append({
                        "name": v_name,
                        "type": "dedicated" if is_dedicated else "system",
                        "is_dedicated": is_dedicated,
                        "cuda": False,
                        "device_index": None,
                        "vram_gb": vram_gb,
                        "source": "wmi",
                    })
        except Exception as e:
            logger.debug(f"WMI GPU check error: {e}")

    # 3. Fallback: nvidia-smi if not already present
    if not any(g.get("is_dedicated") for g in gpus):
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    name = parts[0]
                    mem_mb = float(parts[1]) if len(parts) > 1 else 0.0
                    gpus.append({
                        "name": name,
                        "type": "dedicated",
                        "is_dedicated": True,
                        "cuda": True,
                        "device_index": 0,
                        "vram_gb": round(mem_mb / 1024.0, 2),
                        "source": "nvidia_smi",
                    })
        except Exception:
            pass

    # 4. Fallback Default CPU / System Adapter if none found
    if not gpus:
        gpus.append({
            "name": "Default System Display Adapter",
            "type": "system",
            "is_dedicated": False,
            "cuda": False,
            "device_index": None,
            "vram_gb": 1.0,
            "source": "default_fallback",
        })

    _DETECTED_GPUS_CACHE = gpus
    return gpus


def select_compute_device(prefer_dedicated: bool = True) -> Dict[str, Any]:
    """
    Selects the optimal compute device according to user policy:
    - Uses Dedicated GPU if available (e.g. NVIDIA RTX 4050, 6GB VRAM, CUDA)
    - Else falls back gracefully to System GPU (e.g. Intel UHD Graphics / Default adapter)
    """
    all_gpus = get_hardware_gpus()

    dedicated = [g for g in all_gpus if g.get("is_dedicated")]
    system = [g for g in all_gpus if not g.get("is_dedicated")]

    chosen: Dict[str, Any]
    if prefer_dedicated and dedicated:
        # Prioritize dedicated with CUDA, highest VRAM
        chosen = sorted(dedicated, key=lambda x: (1 if x.get("cuda") else 0, x.get("vram_gb", 0)), reverse=True)[0]
        dev_type = "DEDICATED"
        cuda_idx = chosen.get("device_index", 0) if chosen.get("cuda") else 0
        torch_dev = f"cuda:{cuda_idx}" if chosen.get("cuda") else "cpu"
        env_vars = {
            "CUDA_VISIBLE_DEVICES": str(cuda_idx) if chosen.get("cuda") else "0",
            "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
            "TORCH_DEVICE": torch_dev,
            "NEURA_COMPUTE_DEVICE": torch_dev,
            "NEURA_GPU_TYPE": "dedicated",
            "NEURA_GPU_NAME": chosen.get("name", "Dedicated GPU"),
            "OPENCV_DNN_BACKEND": "CUDA" if chosen.get("cuda") else "DEFAULT",
            "OPENCV_DNN_TARGET": "CUDA" if chosen.get("cuda") else "CPU",
        }
        summary = f"Dedicated GPU ({chosen.get('name')}, {chosen.get('vram_gb', 0)} GB VRAM)"
    else:
        chosen = system[0] if system else (all_gpus[0] if all_gpus else {"name": "System GPU", "vram_gb": 0})
        dev_type = "SYSTEM_DEFAULT"
        env_vars = {
            "CUDA_VISIBLE_DEVICES": "",
            "TORCH_DEVICE": "cpu",
            "NEURA_COMPUTE_DEVICE": "system_gpu",
            "NEURA_GPU_TYPE": "system",
            "NEURA_GPU_NAME": chosen.get("name", "System GPU"),
            "OPENCV_DNN_BACKEND": "DEFAULT",
            "OPENCV_DNN_TARGET": "CPU",
        }
        summary = f"System GPU ({chosen.get('name')})"

    return {
        "device_type": dev_type,
        "name": chosen.get("name", "Unknown GPU"),
        "is_dedicated": dev_type == "DEDICATED",
        "cuda_available": bool(chosen.get("cuda", False)),
        "device_index": chosen.get("device_index"),
        "vram_gb": chosen.get("vram_gb", 0.0),
        "env_vars": env_vars,
        "summary": summary,
        "all_detected": all_gpus,
    }


def get_gpu_environment(
    device_info: Optional[Dict[str, Any]] = None,
    base_env: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Returns a copy of the environment with injected GPU compute settings.
    """
    env = dict(base_env or os.environ).copy()
    dev = device_info or select_compute_device(prefer_dedicated=True)

    for k, v in dev.get("env_vars", {}).items():
        env[k] = str(v)

    return env


def format_compute_banner(device_info: Dict[str, Any], project_name: str = "Project") -> str:
    """Creates a stylized terminal compute header."""
    dtype = device_info.get("device_type", "UNKNOWN")
    dname = device_info.get("name", "Unknown Device")
    vram = device_info.get("vram_gb", 0)
    cuda_stat = "CUDA Enabled" if device_info.get("cuda_available") else "Standard Acceleration"

    border = "=" * 70
    return (
        f"{border}\n"
        f">> [NEURA HARDWARE ACCELERATION] Testing: {project_name}\n"
        f">> Compute Target : {dtype} GPU -> {dname}\n"
        f">> Memory / State : {vram} GB VRAM | {cuda_stat}\n"
        f"{border}"
    )
