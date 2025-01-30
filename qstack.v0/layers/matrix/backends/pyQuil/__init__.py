import qstack.backend

from .emulator import pyQuilEmulator as Emulator


class Backend(qstack.backend.Backend):
    def __init__(self) -> None:
        super().__init__(Emulator())
