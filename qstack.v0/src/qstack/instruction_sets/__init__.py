import os
import importlib
from ..instruction_set import InstructionSet

# Dynamically populate the LAYER_REGISTRY by scanning the layers directory
INST_SET_REGISTRY = {}
layers_dir = os.path.dirname(__file__)

for filename in os.listdir(layers_dir):
    if filename.endswith(".py") and filename != "__init__.py":
        module_name = f"qstack.instruction_sets.{filename[:-3]}"
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "instruction_set") and isinstance(module.instruction_set, InstructionSet):
                INST_SET_REGISTRY[module.instruction_set.name] = module.instruction_set
        except Exception as e:
            # Log or handle the error if needed
            pass


def get_instruction_set_by_name(name: str):
    """
    Retrieve a Layer instance by its name.

    Args:
        name (str): The name of the layer to retrieve.

    Returns:
        Layer: The corresponding Layer instance.

    Raises:
        ValueError: If the layer name is not found in the registry.
    """
    if name not in INST_SET_REGISTRY:
        raise ValueError(f"Layer '{name}' not found in the registry.")
    return INST_SET_REGISTRY[name]
