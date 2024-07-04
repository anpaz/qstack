from typing import Callable

import logging

logger = logging.getLogger("qcir")


def cache_field(instance: object, field: str, evaluator: Callable):
    if not hasattr(instance, field):
        logger.debug(f"populating field {field}")
        value = evaluator()
        object.__setattr__(instance, field, value)
    return getattr(instance, field)
