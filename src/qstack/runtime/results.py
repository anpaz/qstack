"""Repeated-evaluation result container with histogram + plotting helpers.

Modeled on the legacy ``qstack.machine.Results`` so notebooks using the
new MLIR runtime feel familiar:

    results = machine.eval(shots=1000)
    results.histogram()        # -> OrderedDict[tuple, int]
    results.plot_histogram()   # matplotlib bar chart
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from typing import Any, Iterator


class Results:
    def __init__(self, data: list[list[int | None]]) -> None:
        self._data = list(data)
        self._histogram: OrderedDict[tuple, int] | None = None

    # ---- sequence protocol -------------------------------------------

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[list[int | None]]:
        return iter(self._data)

    def __getitem__(self, idx: int) -> list[int | None]:
        return self._data[idx]

    # ---- aggregation -------------------------------------------------

    @property
    def shots(self) -> int:
        return len(self._data)

    @property
    def data(self) -> list[list[int | None]]:
        return self._data

    def histogram(self) -> OrderedDict[tuple, int]:
        if self._histogram is None:
            counts = Counter(tuple(s) for s in self._data)
            self._histogram = OrderedDict(
                (k, counts[k]) for k in sorted(counts.keys(), key=lambda t: tuple(str(x) for x in t))
            )
        return self._histogram

    # ---- presentation ------------------------------------------------

    def __repr__(self) -> str:
        return f"Results({self.shots} shots, histogram={dict(self.histogram())})"

    def plot_histogram(self, *, show: bool = True) -> Any:
        """Render a matplotlib bar chart of the histogram.

        Returns the ``Axes`` object so notebook callers can further
        customize. ``show=False`` skips ``plt.show()`` (useful in tests).
        """
        import matplotlib.pyplot as plt

        hist = self.histogram()
        fig, ax = plt.subplots()
        ax.bar([str(k) for k in hist.keys()], list(hist.values()))
        ax.set_xlabel("Outcomes")
        ax.set_ylabel("Frequency")
        if show:
            plt.show()
        return ax
