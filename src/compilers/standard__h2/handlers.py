import math

from instruction_sets.h2 import instructions as h2
from instruction_sets.standard import instructions as standard
from qcir.circuit import Circuit, Comment, Instruction, Tick
from qstack import Handler, InstructionDefinition


class MeasureZ(Handler):
    @property
    def source(self):
        return standard.MeasureZ

    def uses(self) -> set[InstructionDefinition]:
        return {
            h2.Measure,
        }

    def handle(self, inst: Instruction, _):
        return Circuit(
            self.__class__.__name__,
            [
                h2.Measure(targets=inst.targets),
            ],
        )


class PrepareBell(Handler):
    @property
    def source(self):
        return standard.PrepareBell

    def uses(self) -> set[InstructionDefinition]:
        return {
            h2.U1,
            h2.RZ,
            h2.ZZ,
        }

    def handle(self, inst: Instruction, _):
        return Circuit(
            self.__class__.__name__,
            [
                Comment(f"start: " + inst.name),
                Tick(),
                Comment("H " + str(inst.targets[0])),
                h2.U1(parameters=[math.pi / 2.0, -math.pi / 2.0], targets=[inst.targets[0]]),
                h2.RZ(parameters=[math.pi], targets=[inst.targets[0]]),

                Tick(),
                Comment(" ".join(["CX", str(inst.targets[0]), str(inst.targets[1])])),
                
                h2.U1(parameters=[-math.pi / 2.0, math.pi / 2.0], targets=[inst.targets[1]]),
                h2.ZZ([inst.targets[0], inst.targets[1]]),
                
                h2.RZ(parameters=[-math.pi / 2.0], targets=[inst.targets[0]]),
                h2.U1(parameters=[math.pi / 2.0, math.pi], targets=[inst.targets[1]]),
                h2.RZ(parameters=[-math.pi / 2.0], targets=[inst.targets[1]]),
            ],
        )


class PrepareZero(Handler):
    @property
    def source(self):
        return standard.PrepareZero

    def uses(self) -> set[InstructionDefinition]:
        return {}

    def handle(self, inst: Instruction, _):
        return Circuit(
            self.__class__.__name__,
            [],
        )


class Hadamard(Handler):
    @property
    def source(self):
        return standard.Hadamard

    def uses(self) -> set[InstructionDefinition]:
        return {
            h2.U1,
            h2.RZ,
        }

    def handle(self, inst: Instruction, _):
        return Circuit(
            self.__class__.__name__,
            [
                Comment(f"start: " + inst.name),
                h2.U1(parameters=[math.pi / 2.0, -math.pi / 2.0], targets=[inst.targets[0]]),
                h2.RZ(parameters=[math.pi], targets=[inst.targets[0]]),
            ],
        )


class CtrlX(Handler):
    @property
    def source(self):
        return standard.CtrlX

    def uses(self) -> set[InstructionDefinition]:
        return {
            h2.U1,
            h2.RZ,
            h2.ZZ,
        }

    def handle(self, inst: Instruction, _):
        return Circuit(
            self.__class__.__name__,
            [
                Comment(f"start: " + inst.name),
                h2.U1(parameters=[-math.pi / 2.0, math.pi / 2.0], targets=[inst.targets[1]]),
                h2.ZZ([inst.targets[0], inst.targets[1]]),
                h2.RZ(parameters=[-math.pi / 2.0], targets=[inst.targets[0]]),
                h2.U1(parameters=[math.pi / 2.0, math.pi], targets=[inst.targets[1]]),
                h2.RZ(parameters=[-math.pi / 2.0], targets=[inst.targets[1]]),
            ],
        )
