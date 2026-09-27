"""Lowering rules from docs/openqasm-surface-design.md §4.6-4.8: every qubit
parameter is returned, measuring one substitutes a fresh |0>, and every
qubit or bit that comes into existence in a body must be consumed before it
ends.
"""

import pytest
from xdsl.dialects.builtin import ModuleOp

from qstack.dialect.core import KernelOp
from qstack.runtime import CallbackRegistry, Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module


def _module(src: str) -> ModuleOp:
    return lower(parse(src))


def _kernel(module: ModuleOp, name: str) -> KernelOp:
    return next(
        op
        for op in module.body.ops
        if isinstance(op, KernelOp) and op.sym_name.data == name
    )


WRAPPER = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

def flip(qubit q) {
  x q;
}

def wrapper(qubit q) {
  flip q;
}

qreg q[1];
creg c[1];
wrapper q[0];
measure q[0] -> c[0];
"""


def test_wrapper_def_threads_a_call_result_back_out() -> None:
    """A def whose body is just a call to another def still returns its parameter."""

    module = _module(WRAPPER)
    wrapper = _kernel(module, "wrapper")
    assert len(wrapper.input_types) == 1
    assert len(wrapper.declared_result_types) == 1
    verify_module(module)

    hist = dict(Machine(num_qubits=4, registry=CallbackRegistry()).eval(module, shots=200).histogram())
    assert hist == {(1,): 200}


SWITCH_MEASURE = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

extern selector choose(bit) -> int;

def switch_measure(qubit a, qubit b) {
  bit flag;
  h a;
  measure a -> flag;
  switch (choose(flag)) {
    case 0: { }
    case 1: {
      bit extra;
      measure b -> extra;
      switch (choose(extra)) {
        case 0: { }
        case 1: { }
      }
    }
  }
}

qreg q[2];
creg c[2];
switch_measure q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""


def test_switch_case_measuring_a_live_qubit_gets_a_reset() -> None:
    """Every qubit threaded through a switch is a case kernel's "parameter":

    measuring one inside a case body substitutes a fresh |0>, exactly as
    measuring a def's own qubit parameter does.
    """

    module = _module(SWITCH_MEASURE)
    verify_module(module)
    case_kernels = [
        op for op in module.body.ops if isinstance(op, KernelOp) and op.sym_name.data.startswith("__qstack_case_")
    ]
    assert case_kernels
    assert any(kernel.allocation_count >= 1 for kernel in case_kernels)


REPEATED_MEASUREMENT = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

extern selector choose2(bit, bit) -> int;

def measure_twice(qubit a) {
  bit m1;
  bit m2;
  measure a -> m1;
  measure a -> m2;
  switch (choose2(m1, m2)) {
    case 0: { }
  }
}

qreg q[1];
creg c[1];
measure_twice q[0];
measure q[0] -> c[0];
"""


def test_repeated_measurement_of_a_parameter_allocates_one_replacement_each_time() -> None:
    module = _module(REPEATED_MEASUREMENT)
    verify_module(module)
    measure_twice = _kernel(module, "measure_twice")
    assert measure_twice.allocation_count == 2


UNUSED_DECLARATION = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

def with_spare(qubit q) {
  qreg spare[1];
  x q;
}

qreg q[1];
creg c[1];
with_spare q[0];
measure q[0] -> c[0];
"""


def test_unreferenced_qreg_declaration_is_omitted_from_allocation() -> None:
    """An allocated-but-untouched qreg element never enters the IR at all."""

    module = _module(UNUSED_DECLARATION)
    with_spare = _kernel(module, "with_spare")
    assert with_spare.allocation_count == 0
    verify_module(module)


def test_unmeasured_local_ancilla_is_a_compile_error() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

def leaves_ancilla(qubit q) {
  qreg anc[1];
  x anc[0];
}

qreg q[1];
creg c[1];
leaves_ancilla q[0];
measure q[0] -> c[0];
"""
    with pytest.raises(ValueError, match="anc\\[0\\].*measured"):
        _module(source)


def test_unconsumed_bit_is_a_compile_error() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

def leaves_bit(qubit q) {
  bit m;
  measure q -> m;
}

qreg q[1];
creg c[1];
leaves_bit q[0];
measure q[0] -> c[0];
"""
    with pytest.raises(ValueError, match="m.*never consumed"):
        _module(source)


def test_unmeasured_top_level_qubit_is_a_compile_error() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[1];
creg c[1];
h q[0];
"""
    with pytest.raises(ValueError, match="q\\[0\\].*measured"):
        _module(source)
