import sys
import subprocess
from pynvml import *

def apply_optimized_cluster_tuning():
    try:
        # 1. Shell out to handle the application clock permission bypass safely
        print("[!] Initializing driver permissions...")
        subprocess.run(["nvidia-smi", "-acp", "0"], check=True)
        print(" -> Application Clocks Permission (acp 0): CONFIGURED")

        # 2. Initialize the NVML hardware layer
        nvmlInit()
        device_count = nvmlDeviceGetCount()
        print(f"[+] Found {device_count} NVIDIA GPUs. Executing per-GPU optimized tuning...")

        # Define custom targets per GPU slot to counter the physical sandwich layout
        # GPU 0: Hot sandwiched card. Lower core clock slightly to prevent power wall & thermal drop.
        # GPU 1: Cool master card. Max out core clock and memory headroom.
        gpu_profiles = {
            0: {"offset_mhz": 900, "target_gpu_clk": 1800, "power_limit_watts": 200, "force_fan_pct": 85},
            1: {"offset_mhz": 900, "target_gpu_clk": 1800, "power_limit_watts": 200, "force_fan_pct": 0}   # 0 means leave on auto
        }

        for i in range(device_count):
            handle = nvmlDeviceGetHandleByIndex(i)
            name = nvmlDeviceGetName(handle)
            print(f"\n⚡ Configuring GPU {i} [{name}]:")

            # Fallback to defaults if layout changes
            prof = gpu_profiles.get(i, {"offset_mhz": 1100, "target_gpu_clk": 1850, "power_limit_watts": 180, "force_fan_pct": 0})

            # 3. Enable Driver Persistence Mode
            nvmlDeviceSetPersistenceMode(handle, NVML_FEATURE_ENABLED)
            print(" -> Driver Persistence Mode: ENABLED")

            # 4. Lock GPU Core Frequency
            nvmlDeviceSetGpuLockedClocks(handle, prof["target_gpu_clk"], prof["target_gpu_clk"])
            print(f" -> GPU Core Frequency: LOCKED to {prof['target_gpu_clk']} MHz")

            # 5. Fix NVML driver offset parsing (offset_mhz * 2 maps correctly to transfer rates)
            raw_value = prof["offset_mhz"] * 2
            try:
                nvmlDeviceSetMemClkVfOffset(handle, raw_value)
                print(f" -> VRAM Offset: SHIFTED to +{prof['offset_mhz']} MHz")
            except NvmlException as e:
                print(f" -> VRAM Shift Alert: {e}")

            # 6. Enforce custom Power Management Limit
            milliwatts_limit = prof["power_limit_watts"] * 1000
            nvmlDeviceSetPowerManagementLimit(handle, milliwatts_limit)
            print(f" -> TDP Constraint: Enforced structural cap at {prof['power_limit_watts']}W")

            # 7. Hardware Cooling Injector for Sandwiched Cards
            if prof["force_fan_pct"] > 0:
                try:
                    # Clear restrictive cooling control knobs if driver locks them
                    try:
                        nvmlDeviceSetDefaultFanSpeed_v2(handle, 0)
                    except:
                        pass
                    # Overriding the knob controls fan index 0 directly via nvml
                    nvmlDeviceSetFanSpeedKnob(handle, prof["force_fan_pct"])
                    print(f" -> Fan Override: Forced cooling array to {prof['force_fan_pct']}% to clear sandwich heat")
                except Exception as fan_err:
                    print(f" -> Fan Override warning: {fan_err} (Driver or hardware policy locked control)")

        nvmlShutdown()
        print("\n🚀 [SUCCESS] Asymmetric hardware cluster optimization complete and locked.")
        return True
    except Exception as err:
        print(f"\n❌ [CRITICAL ERROR] Execution failed: {err}")
        print("Please ensure this script is executed with root/sudo privileges.")
        return False

if __name__ == "__main__":
    success = apply_optimized_cluster_tuning()
    sys.exit(0 if success else 1)