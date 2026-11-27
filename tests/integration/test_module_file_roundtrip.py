from io import StringIO

from xdsl.context import Context
from xdsl.dialects.builtin import Builtin
from xdsl.parser import Parser
from xdsl.printer import Printer

from qstack.dialect import QStack
from qstack.dialect.cliffords import Cliffords
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.validation import validate_module


def test_kernel_only_module_roundtrips() -> None:
    module = lower(parse('''QSTACKQASM 0.1; include "qstack/cliffords.inc"; qubit[1] q; bit[1] c; x q[0]; measure q[0] -> c[0];'''))
    stream = StringIO(); Printer(stream=stream).print_op(module)
    context = Context(); context.load_dialect(Builtin); context.load_dialect(QStack); context.load_dialect(Cliffords)
    reparsed = Parser(context, stream.getvalue()).parse_module()
    validate_module(reparsed)
