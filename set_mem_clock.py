import sys
from pynvml import *

def apply_headless_overclock(offset_mhz=1000):
    try:
        # Initialize the NVML hardware layer
        nvmlInit()
        device_count = nvmlDeviceGetCount()
        print(f"Found {device_count} NVIDIA GPUs. Injecting memory offsets...")

        for i in range(device_count):
            handle = nvmlDeviceGetHandleByIndex(i)
            name = nvmlDeviceGetName(handle)
            
            # NVML maps the memory offset using the VF curve matrix.
            # To get an effective +1000 MHz speedup, the raw value must be doubled.
            raw_value = offset_mhz * 2
            
            # Use the correct Ampere function name
            nvmlDeviceSetMemClkVfOffset(handle, raw_value)
            print(f" -> GPU {i} [{name}]: Memory Offset set to +{offset_mhz} MHz successfully.")
            
        nvmlShutdown()
        print("Hardware configuration locked.")
    except Exception as err:
        print(f"Execution Error: {err}")
        print("Ensure you are running the script with sudo privileges.")

if __name__ == "__main__":
    # 1000 will result in a true +1000 MHz shift past the 7301MHz cap
    apply_headless_overclock(1000)

