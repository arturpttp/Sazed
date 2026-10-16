"""Time file searches through the real Windows Search index (median and p95 over 20 queries).

Read-only: it queries the index and never opens a file.
"""

import statistics
import time
from pathlib import Path

from sazed.adapters.windows.files import WindowsFileSearch

WORDS = [
    "relatorio",
    "nota",
    "foto",
    "contrato",
    "planilha",
    "curriculo",
    "boleto",
    "projeto",
    "imagem",
    "captura",
    "documento",
    "video",
    "musica",
    "backup",
    "config",
    "teste",
    "fatura",
    "lista",
    "readme",
    "senha",
]


def main() -> None:
    search = WindowsFileSearch([str(Path.home())])
    search.search(["aquecimento"], [], 6)  # the first query pays for COM and the provider
    times = []
    for word in WORDS:
        start = time.perf_counter()
        search.search([word], [], 6)
        times.append((time.perf_counter() - start) * 1000)
    times.sort()
    p95 = times[int(len(times) * 0.95) - 1]
    print(f"{len(times)} searches: median {statistics.median(times):.0f} ms, p95 {p95:.0f} ms")


if __name__ == "__main__":
    main()
