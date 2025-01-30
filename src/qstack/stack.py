from dataclasses import dataclass

from .layer import Layer
from .compiler import Compiler


@dataclass(frozen=True)
class Node:
    lower: "Node"


@dataclass(frozen=True)
class LayerNode(Node):
    layer_id: str
    lower: Node | None

    @property
    def layer() -> Layer:
        pass

    def __str__(self):
        if not self.lower:
            return self.layer_id
        else:
            return f"{self.layer_id}@{str(self.lower)}"


@dataclass(frozen=True)
class CompilerNode(Node):
    compiler_id: Compiler
    lower: Node

    @property
    def compiler() -> Compiler:
        pass

    def __str__(self):
        return f"@{self.compiler_id}@{str(self.lower)}"


@dataclass(frozen=True)
class Stack:
    target: LayerNode

    def add_layer(self, compiler: Compiler, layer: Layer):
        # assert self.target == compiler.source
        lower = LayerNode(layer_id=layer.name)
        return Stack(target=LayerNode(layer, CompilerNode(compiler_id=compiler.name, lower=lower)))

    @staticmethod
    def create(layer: Layer):
        return Stack(LayerNode(layer_id=layer.name, lower=None))

    def __str__(self):
        return str(self.target)
