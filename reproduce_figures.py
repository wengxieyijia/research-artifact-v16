"""Command-line entry point for frozen v16 figure reproduction."""
from pathlib import Path
from src.curve_reproduction import main

if __name__ == "__main__":
    raise SystemExit(main(root=Path(__file__).resolve().parent))
