from dataclasses import dataclass


class Context:

    def __init__(self):
        from stim import Circuit

        self.circuit = Circuit()
        self.measurements_map: dict[int, int] = {}
        self.measurements_count: int = 0
