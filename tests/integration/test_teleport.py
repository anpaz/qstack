"""End-to-end test for the quantum-teleportation example.

Mirrors ``mlir/examples/4.teleport.ipynb``: a `def teleport(qubit target)`
that prepares a source state, builds an EPR pair (shared, target),
performs a Bell measurement on (source, shared), and uses a `switch`
over a host-language selector to apply the Pauli correction
$Z^{m_0} X^{m_1}$ to ``target``.  After teleportation, ``target`` is
measured in the computational basis.
"""

from qstack.runtime import CallbackRegistry, Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module


def _teleport_program(prep_gate: str) -> str:
    return f"""
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

extern selector teleport_fix(bit, bit) -> int;

def teleport(qubit target) {{
  qreg shared[1];
  qreg source[1];
  bit m0;
  bit m1;

  {prep_gate} source[0];

  h shared[0];
  cx shared[0], target;

  cx source[0], shared[0];
  h source[0];
  measure source[0] -> m0;
  measure shared[0] -> m1;

  switch (teleport_fix(m0, m1)) {{
    case 0: {{ }}
    case 1: {{ x target; }}
    case 2: {{ z target; }}
    case 3: {{ x target; z target; }}
  }}
}}

qreg q[1];
creg c[1];
teleport q[0];
measure q[0] -> c[0];
"""


def _registry() -> CallbackRegistry:
    reg = CallbackRegistry()

    @reg.selector("teleport_fix")
    def _fix(bits: tuple[int, ...]) -> str:
        # Encode (m0, m1) into the case label: 2*m0 + m1.
        m0, m1 = bits
        return str(m0 * 2 + m1)

    return reg


def test_teleport_module_verifies() -> None:
    module = lower(parse(_teleport_program("x")))
    verify_module(module)


def test_teleport_preserves_one() -> None:
    # source = X|0> = |1>; after teleportation, target should always read 1.
    module = lower(parse(_teleport_program("x")))
    machine = Machine(module, num_qubits=8, registry=_registry())
    hist = dict(machine.eval(shots=1000).histogram())
    assert hist == {(1,): 1000}, f"expected target=|1> deterministically; got {hist!r}"


def test_teleport_preserves_plus_state_statistics() -> None:
    # source = H|0> = |+>; measuring target in Z basis -> 50/50.
    module = lower(parse(_teleport_program("h")))
    machine = Machine(module, num_qubits=8, registry=_registry())
    hist = dict(machine.eval(shots=4000).histogram())
    assert set(hist.keys()) == {(0,), (1,)}
    for key in [(0,), (1,)]:
        assert 1600 < hist[key] < 2400, f"|+> teleportation outcome {key} count {hist[key]} outside [1600, 2400]"
