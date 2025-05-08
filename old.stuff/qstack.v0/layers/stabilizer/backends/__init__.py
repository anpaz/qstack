import qstack.backend

from .stim.emulator import StimEmulator, NoiseModel


class Backend(qstack.backend.Backend):
    def __init__(self, noise_model=None) -> None:
        super().__init__(StimEmulator(noise=noise_model))
