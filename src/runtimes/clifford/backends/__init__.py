import qstack.backend

from .stim.emulator import StimEmulator


class Backend(qstack.backend.Backend):
    def __init__(self) -> None:
        super().__init__(StimEmulator())
