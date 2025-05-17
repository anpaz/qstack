from IPython.core.magic import Magics, magics_class, cell_magic
from .parser import QStackParser


@magics_class
class QStackMagics(Magics):

    @cell_magic
    def qstack(self, line, cell):
        layer = None
        if line.strip():
            # Evaluate the line as a Python expression in user namespace
            layer = eval(line, self.shell.user_ns)

        parser = QStackParser(instruction_set=layer)
        program = parser.parse(cell)

        # Set `program` in user namespace
        self.shell.user_ns["program"] = program

        # Return the program so it's displayed as the cell result
        return program


def load_ipython_extension(ipython):
    ipython.register_magics(QStackMagics)
