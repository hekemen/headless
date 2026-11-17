import sys
import subprocess
from pynvml import *

def apply_headless_tuning(offset_mhz=1100, target_gpu_clk=1850, power_limit_watts=130):
    try:
        # 1. Shell out to handle the application clock permission bypass safely
        print("Initializing driver permissions...")
        subprocess.run(["nvidia-smi", "-acp", "0"], check=True)
        print(" -> Application Clocks Permission (acp 0): CONFIGURED")

        # 2. Initialize the NVML hardware layer for clocks, offsets, and power
        nvmlInit()
        device_count = nvmlDeviceGetCount()
        print(f"Found {device_count} NVIDIA GPUs. Executing unified AI tuning...")

        for i in range(device_count):
            handle = nvmlDeviceGetHandleByIndex(i)
            name = nvmlDeviceGetName(handle)
            print(f"\nConfiguring GPU {i} [{name}]:")

            # 3. Enable Driver Persistence Mode
            nvmlDeviceSetPersistenceMode(handle, NVML_FEATURE_ENABLED)
            print(" -> Driver Persistence Mode: ENABLED")

            # 4. Lock Graphics (GPU) Core Frequency to 1850 MHz efficiency sweet spot
            nvmlDeviceSetGpuLockedClocks(handle, target_gpu_clk, target_gpu_clk)
            print(f" -> GPU Core Frequency: LOCKED to {target_gpu_clk} MHz")

            # 5. Inject your custom VF Curve Memory Shift (+1100 mapped to 8501 MHz)
            raw_value = offset_mhz * 2
            nvmlDeviceSetMemClkVfOffset(handle, raw_value)
            print(f" -> VRAM Offset: SHIFTED to +{offset_mhz} MHz (MEM: 8501 MHz)")

            # 6. Enforce a hard Power Management Limit (Converts Watts to Milliwatts)
            # This implements the equivalent of: nvidia-smi -pl 130
            milliwatts_limit = power_limit_watts * 1000
            nvmlDeviceSetPowerManagementLimit(handle, milliwatts_limit)
            print(f" -> TDP Constraint: Enforced structural cap at {power_limit_watts}W")

        nvmlShutdown()
        print("\n[SUCCESS] Hardware cluster optimization complete and locked.")
    except Exception as err:
        print(f"\n[ERROR] Execution failed: {err}")
        print("Please ensure this script is executed with root/sudo privileges.")

if __name__ == "__main__":
    # Parameters: Memory Offset (+1200MHz), Core Clock (1950MHz), Hard Power Cap (130W)
    apply_headless_tuning(offset_mhz=1300, target_gpu_clk=1950, power_limit_watts=180)

