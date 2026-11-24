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
  flip(q);
}

qubit[1] q;
bit[1] c;
wrapper(q[0]);
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
    case 0 { }
    case 1 {
      bit extra;
      measure b -> extra;
      switch (choose(extra)) {
        case 0 { }
        case 1 { }
      }
    }
  }
}

qubit[2] q;
bit[2] c;
switch_measure(q[0], q[1]);
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
    case 0 { }
  }
}

qubit[1] q;
bit[1] c;
measure_twice(q[0]);
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
  qubit[1] spare;
  x q;
}

qubit[1] q;
bit[1] c;
with_spare(q[0]);
measure q[0] -> c[0];
"""


def test_unreferenced_qubit_declaration_is_omitted_from_allocation() -> None:
    """A declared-but-untouched qubit never enters the IR at all."""

    module = _module(UNUSED_DECLARATION)
    with_spare = _kernel(module, "with_spare")
    assert with_spare.allocation_count == 0
    verify_module(module)


def test_unmeasured_local_ancilla_is_a_compile_error() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

def leaves_ancilla(qubit q) {
  qubit[1] anc;
  x anc[0];
}

qubit[1] q;
bit[1] c;
leaves_ancilla(q[0]);
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

qubit[1] q;
bit[1] c;
leaves_bit(q[0]);
measure q[0] -> c[0];
"""
    with pytest.raises(ValueError, match="m.*never consumed"):
        _module(source)


def test_unmeasured_top_level_qubit_is_a_compile_error() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qubit[1] q;
bit[1] c;
h q[0];
"""
    with pytest.raises(ValueError, match="q\\[0\\].*measured"):
        _module(source)


# ----------------------------------------------------------------------
# while, for, decoder calls, measurement plus reset, and qubits in any block


def _registry() -> CallbackRegistry:
    registry = CallbackRegistry()

    @registry.selector("repeat_until_one")
    def _retry(bits: tuple[int, ...]) -> str:
        return "0" if bits[0] == 1 else "1"  # 1 = run the body again, 0 = stop

    @registry.selector("flip_if")
    def _flip_if(bits: tuple[int, ...]) -> str:
        return str(bits[0])

    @registry.decoder("majority")
    def _majority(bits: tuple[int, ...]) -> int:
        return int(sum(bits) >= 2)

    return registry


def _run(module: ModuleOp, shots: int = 200) -> dict:
    return dict(Machine(num_qubits=8, registry=_registry()).eval(module, shots=shots).histogram())


PREPARE_ONE_WHILE = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

extern selector repeat_until_one(bit) -> bool;

def prepare_one(qubit q) {
  qubit[1] a;
  bit m;
  h q;
  cx q, a[0];
  measure a[0] -> m;
  while (repeat_until_one(m)) {
    qubit[1] b;
    h q;
    cx q, b[0];
    measure b[0] -> m;
  }
}

qubit[1] q;
bit[1] c;
prepare_one(q[0]);
measure q[0] -> c[0];
"""


def test_while_lowers_to_a_recursive_loop_kernel_and_an_exit_kernel() -> None:
    module = _module(PREPARE_ONE_WHILE)
    verify_module(module)
    loop = _kernel(module, "__qstack_while_1")
    exit_kernel = _kernel(module, "__qstack_while_1_exit")
    # The loop kernel borrows the qubit live at the loop and allocates the
    # ancilla the body uses; its select names the loop kernel itself.
    assert len(loop.input_types) == 1
    assert loop.allocation_count == 1
    assert exit_kernel.allocation_count == 0
    selects = [op for op in loop.body.block.ops if op.name == "qstack.select"]
    assert len(selects) == 1
    cases = {label: ref.root_reference.data for label, ref in selects[0].cases.data.items()}
    assert cases == {"1": "__qstack_while_1", "0": "__qstack_while_1_exit"}
    assert _run(module) == {(1,): 200}


def test_while_body_must_measure_the_condition_bits() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";
extern selector repeat_until_one(bit) -> bool;
def f(qubit q) {
  qubit[1] a;
  bit m;
  measure a[0] -> m;
  while (repeat_until_one(m)) { x q; }
}
qubit[1] q;
bit[1] c;
f(q[0]);
measure q[0] -> c[0];
"""
    with pytest.raises(ValueError, match="must measure m"):
        _module(source)


REPETITION = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

extern majority(bit, bit, bit) -> bit;

qubit[3] q;
bit[3] c;
x q[0];
for int i in [1:2] { cx q[0], q[i]; }
for int i in {0, 1, 2} { measure q[i] -> c[i]; }
bit b = majority(c[0], c[1], c[2]);
"""


def test_for_is_unrolled_and_a_decoder_call_lowers_to_decode() -> None:
    module = _module(REPETITION)
    verify_module(module)
    main = _kernel(module, "main")
    names = [op.name for op in main.body.block.ops]
    assert names.count("cliffords.cx") == 2
    assert names.count("qstack.measure") == 3
    assert names.count("qstack.decode") == 1
    assert len(main.declared_result_types) == 1
    assert _run(module) == {(1,): 200}


def test_for_range_with_a_step_is_inclusive() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qubit[5] q;
bit[5] c;
for int i in [0:2:4] { x q[i]; }
for int i in [0:4] { measure q[i] -> c[i]; }
"""
    module = _module(source)
    verify_module(module)
    assert _run(module) == {(1, 0, 1, 0, 1): 200}


def test_measuring_a_local_and_using_it_again_allocates_a_fresh_qubit() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qubit[1] q;
bit[2] c;
x q[0];
measure q[0] -> c[0];
measure q[0] -> c[1];
"""
    module = _module(source)
    verify_module(module)
    assert _kernel(module, "main").allocation_count == 2
    # The second measurement sees the fresh |0>, not the measured state.
    assert _run(module) == {(1, 0): 200}


ARM_QREG = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

extern selector flip_if(bit) -> int;

def f(qubit q) {
  qubit[1] a;
  bit m;
  x a[0];
  measure a[0] -> m;
  switch (flip_if(m)) {
    case 0 { }
    case 1 {
      qubit[1] t;
      bit k;
      x t[0];
      cx t[0], q;
      measure t[0] -> k;
      switch (flip_if(k)) { case 0 { } case 1 { } }
    }
  }
}

qubit[1] q;
bit[1] c;
f(q[0]);
measure q[0] -> c[0];
"""


def test_a_switch_arm_can_declare_its_own_qubits() -> None:
    module = _module(ARM_QREG)
    verify_module(module)
    assert _kernel(module, "__qstack_case_1_2").allocation_count == 1
    assert _run(module) == {(1,): 200}


def test_a_qubit_measured_before_a_switch_can_be_used_in_an_arm() -> None:
    """The measured name holds a fresh |0>, which the switch passes to its arms."""

    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";
extern selector flip_if(bit) -> int;
def f(qubit q) {
  bit m;
  x q;
  measure q -> m;
  switch (flip_if(m)) { case 0 { } case 1 { x q; } }
}
qubit[1] q;
bit[1] c;
f(q[0]);
measure q[0] -> c[0];
"""
    module = _module(source)
    verify_module(module)
    assert _run(module) == {(1,): 200}


def test_a_measured_qubit_not_used_again_is_retired() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qubit[2] q;
bit[2] c;
x q[0];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""
    module = _module(source)
    verify_module(module)
    assert _kernel(module, "main").allocation_count == 2


def test_an_ancilla_reused_inside_a_while_must_be_declared_there() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";
extern selector repeat_until_one(bit) -> bool;
def prepare_one(qubit q) {
  qubit[1] a;
  bit m;
  h q;
  cx q, a[0];
  measure a[0] -> m;
  while (repeat_until_one(m)) {
    h q;
    cx q, a[0];
    measure a[0] -> m;
  }
}
qubit[1] q;
bit[1] c;
prepare_one(q[0]);
measure q[0] -> c[0];
"""
    with pytest.raises(ValueError, match="a\\[0\\].*measured.*declared there"):
        _module(source)


def test_a_qubit_declared_in_a_for_body_is_local_to_each_iteration() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qubit[1] q;
bit[3] c;
for int i in [0:1] {
  qubit[1] t;
  x t[0];
  cx t[0], q[0];
  measure t[0] -> c[i];
}
measure q[0] -> c[2];
"""
    module = _module(source)
    verify_module(module)
    assert _kernel(module, "main").allocation_count == 3
    assert _run(module) == {(1, 1, 0): 200}


def test_single_qubits_and_bits_are_declared_without_a_size() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";
def flip(qubit q) { x q; }
qubit q;
bit m;
flip(q);
measure q -> m;
"""
    module = _module(source)
    verify_module(module)
    assert _run(module) == {(1,): 200}


_HEADER = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";
extern selector to_int(bit) -> int;
extern selector to_bool(bit) -> bool;
def flip(qubit q) { x q; }
qubit q;
bit m;
"""


@pytest.mark.parametrize(
    ("statements", "message"),
    [
        ("flip q; measure q -> m;", "called as flip"),
        ("x(q); measure q -> m;", "x, a gate, is applied without parentheses"),
        ("nope(q); measure q -> m;", "nope is not a def"),
        ("flip(q, q); measure q -> m;", "expects 1 qubits, got 2"),
        ("measure q -> m; switch (to_bool(m)) { case 0 { } case 1 { } }", "switch needs a selector declared -> int"),
        ("measure q -> m; while (to_int(m)) { measure q -> m; }", "while needs a selector declared -> bool"),
    ],
)
def test_misused_defs_gates_and_selectors_are_compile_errors(statements: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _module(_HEADER + statements)


def test_a_selector_returns_int_or_bool() -> None:
    with pytest.raises(NotImplementedError, match="result must be int or bool"):
        _module("QSTACKQASM 0.1;\nextern selector s(bit) -> bit;\n")


@pytest.mark.parametrize("declaration", ["qreg q[1];", "creg c[1];"])
def test_openqasm_2_declarations_are_rejected(declaration: str) -> None:
    with pytest.raises(NotImplementedError, match="unknown apply target"):
        _module(f"QSTACKQASM 0.1;\n{declaration}\n")
