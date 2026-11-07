import json
import torch

result = {
    "cuda_available": False,
    "device_name": None,
    "total_vram_gb": 0,
    "error": None
}

try:
    if torch.cuda.is_available():
        result["cuda_available"] = True
        device = torch.device("cuda:0")
        result["device_name"] = torch.cuda.get_device_name(0)
        _, total_mem = torch.cuda.mem_get_info(device)
        result["total_vram_gb"] = round(total_mem / (1024 ** 3), 2)
    else:
        result["error"] = "CUDA not available."
except Exception as e:
    result["error"] = str(e)

print(json.dumps(result))
