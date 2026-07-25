"""Tests for the ``Results`` wrapper returned by ``Machine.eval``."""

from qstack.runtime.results import Results


def test_results_iterable_and_indexable() -> None:
    r = Results([[0], [1], [1], [0], [1]])
    assert len(r) == 5
    assert r[0] == [0]
    assert list(r) == [[0], [1], [1], [0], [1]]


def test_results_histogram_orders_keys() -> None:
    r = Results([[0, 1], [1, 0], [0, 1], [1, 1]])
    hist = r.histogram()
    assert hist == {(0, 1): 2, (1, 0): 1, (1, 1): 1}
    # keys are sorted
    assert list(hist.keys()) == [(0, 1), (1, 0), (1, 1)]


def test_results_histogram_single_bit_shots() -> None:
    r = Results([[1]] * 100)
    hist = r.histogram()
    assert hist == {(1,): 100}


def test_results_repr_is_summary() -> None:
    r = Results([[0], [1], [1]])
    text = repr(r)
    assert "3 shots" in text
    assert "(0,)" in text and "(1,)" in text


def test_results_plot_histogram_returns_axes_without_showing() -> None:
    matplotlib = __import__("matplotlib")
    matplotlib.use("Agg")
    r = Results([[0], [1], [1]])
    ax = r.plot_histogram(show=False)
    # bar plot has 2 bars
    assert len(ax.patches) == 2
