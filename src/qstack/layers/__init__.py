import os
import importlib
from ..layer import Layer

# Dynamically populate the LAYER_REGISTRY by scanning the layers directory
LAYER_REGISTRY = {}
layers_dir = os.path.dirname(__file__)

for filename in os.listdir(layers_dir):
    if filename.endswith(".py") and filename != "__init__.py":
        module_name = f"qstack.layers.{filename[:-3]}"
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "layer") and isinstance(module.layer, Layer):
                LAYER_REGISTRY[module.layer.name] = module.layer
        except Exception as e:
            # Log or handle the error if needed
            pass


def get_layer_by_name(name: str):
    """
    Retrieve a Layer instance by its name.

    Args:
        name (str): The name of the layer to retrieve.

    Returns:
        Layer: The corresponding Layer instance.

    Raises:
        ValueError: If the layer name is not found in the registry.
    """
    if name not in LAYER_REGISTRY:
        raise ValueError(f"Layer '{name}' not found in the registry.")
    return LAYER_REGISTRY[name]
