from dataclasses import dataclass, replace

from .layer import Layer
from .compiler import Compiler


@dataclass(frozen=True)
class Node:
    lower: "Node"


@dataclass(frozen=True)
class LayerNode(Node):
    namespace: str
    layer: Layer
    lower: Node | None

    def __str__(self):
        if not self.lower:
            return f"{self.namespace}{self.layer.name}"
        else:
            return f"{self.namespace}{self.layer.name}@{str(self.lower)}"


@dataclass(frozen=True)
class CompilerNode(Node):
    compiler: Compiler
    lower: Node

    def __str__(self):
        return f"{self.compiler.name}@{str(self.lower)}"


@dataclass(frozen=True)
class Stack:
    target: LayerNode

    @property
    def depth(self):
        def layer_depth(node: LayerNode):
            if node.lower is None:
                return 0
            else:
                return 1 + layer_depth(node.lower.lower)

        return layer_depth(self.target)

    def add_layer(self, compiler: Compiler, layer: Layer) -> "Stack":
        # assert self.target == compiler.source
        new_lower = replace(self.target, namespace=f"l{self.depth}:")
        return Stack(
            target=LayerNode(namespace="", layer=layer, lower=CompilerNode(compiler=compiler, lower=new_lower))
        )

    @staticmethod
    def create(layer: Layer):
        return Stack(LayerNode(namespace="", layer=layer, lower=None))

    def __str__(self):
        return str(self.target)
