import math

from runtimes.h2 import instruction_set as instruction_set
from runtimes.standard.instruction_set import instructions as standard
from qcir.circuit import Circuit, Comment, Instruction, Tick
from qstack import Handler, InstructionDefinition


class MeasureZ(Handler):
    @property
    def source(self):
        return standard.MeasureZ

    def uses(self) -> set[InstructionDefinition]:
        return {
            instruction_set.Measure,
        }

    def handle(self, inst: Instruction, _):
        return Circuit(
            self.__class__.__name__,
            [
                instruction_set.Measure(targets=inst.targets),
            ],
        )


class PrepareBell(Handler):
    @property
    def source(self):
        return standard.PrepareBell

    def uses(self) -> set[InstructionDefinition]:
        return {
            instruction_set.U1,
            instruction_set.RZ,
            instruction_set.ZZ,
        }

    def handle(self, inst: Instruction, _):
        return Circuit(
            self.__class__.__name__,
            [
                Comment("start: " + inst.name),
                Tick(),
                Comment("H " + str(inst.targets[0])),
                instruction_set.U1(parameters=[math.pi / 2.0, -math.pi / 2.0], targets=[inst.targets[0]]),
                instruction_set.RZ(parameters=[math.pi], targets=[inst.targets[0]]),
                Tick(),
                Comment(" ".join(["CX", str(inst.targets[0]), str(inst.targets[1])])),
                instruction_set.U1(parameters=[-math.pi / 2.0, math.pi / 2.0], targets=[inst.targets[1]]),
                instruction_set.ZZ([inst.targets[0], inst.targets[1]]),
                instruction_set.RZ(parameters=[-math.pi / 2.0], targets=[inst.targets[0]]),
                instruction_set.U1(parameters=[math.pi / 2.0, math.pi], targets=[inst.targets[1]]),
                instruction_set.RZ(parameters=[-math.pi / 2.0], targets=[inst.targets[1]]),
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
            instruction_set.U1,
            instruction_set.RZ,
        }

    def handle(self, inst: Instruction, _):
        return Circuit(
            self.__class__.__name__,
            [
                Comment("start: " + inst.name),
                instruction_set.U1(parameters=[math.pi / 2.0, -math.pi / 2.0], targets=[inst.targets[0]]),
                instruction_set.RZ(parameters=[math.pi], targets=[inst.targets[0]]),
            ],
        )


class CtrlX(Handler):
    @property
    def source(self):
        return standard.CtrlX

    def uses(self) -> set[InstructionDefinition]:
        return {
            instruction_set.U1,
            instruction_set.RZ,
            instruction_set.ZZ,
        }

    def handle(self, inst: Instruction, _):
        return Circuit(
            self.__class__.__name__,
            [
                Comment("start: " + inst.name),
                instruction_set.U1(parameters=[-math.pi / 2.0, math.pi / 2.0], targets=[inst.targets[1]]),
                instruction_set.ZZ([inst.targets[0], inst.targets[1]]),
                instruction_set.RZ(parameters=[-math.pi / 2.0], targets=[inst.targets[0]]),
                instruction_set.U1(parameters=[math.pi / 2.0, math.pi], targets=[inst.targets[1]]),
                instruction_set.RZ(parameters=[-math.pi / 2.0], targets=[inst.targets[1]]),
            ],
        )
