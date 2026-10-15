"""Download intfloat/multilingual-e5-small (ONNX + tokenizer) once.

This is the only code in Sazed that touches the network. After it runs, everything is offline.
Usage: uv run python scripts/fetch_model.py [--variant qint8|fp32]
"""

import argparse
import urllib.request
from pathlib import Path

REPO = "https://huggingface.co/intfloat/multilingual-e5-small/resolve/main"
VARIANTS = {
    "qint8": "onnx/model_qint8_avx512_vnni.onnx",  # ~118 MB, needs AVX-512 VNNI for speed
    "fp32": "onnx/model.onnx",  # ~470 MB
}
TARGET = Path(__file__).resolve().parents[1] / "models" / "multilingual-e5-small"


def fetch(url: str, dest: Path) -> None:
    partial = dest.with_name(dest.name + ".part")
    urllib.request.urlretrieve(url, partial)
    partial.replace(dest)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="qint8")
    parser.add_argument("--dir", type=Path, default=TARGET)
    args = parser.parse_args(argv)
    args.dir.mkdir(parents=True, exist_ok=True)
    fetch(f"{REPO}/tokenizer.json", args.dir / "tokenizer.json")
    fetch(f"{REPO}/{VARIANTS[args.variant]}", args.dir / "model.onnx")
    (args.dir / "VARIANT").write_text(args.variant, encoding="utf-8")
    for file in sorted(args.dir.iterdir()):
        print(f"{file.name}: {file.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
