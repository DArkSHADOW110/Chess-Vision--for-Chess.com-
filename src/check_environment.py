"""Check the interpreter and optional training support without installing anything."""
import importlib.util
import platform
import sys

print(f"Python: {sys.version.split()[0]}")
print(f"Interpreter: {sys.executable}")
print(f"System: {platform.system()} {platform.machine()}")

if importlib.util.find_spec("torch") is None:
    print("PyTorch: not installed. Project scaffolding is ready; training is not configured yet.")
else:
    import torch

    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
