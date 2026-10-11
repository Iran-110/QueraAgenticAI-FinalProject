"""Detach boundary contracts without silently dropping bypassed nested extras."""

from collections.abc import Mapping

from agent_app.contracts import Contract


def detached_contract[T: Contract](model: type[T], value: T) -> T:
    """Reject constructed extra attributes at every nested Contract before dumping."""
    if not isinstance(value, model):
        raise ValueError("Invalid boundary contract.")
    ancestors: set[int] = set()

    def check(item, depth=0):
        if depth > 64 or id(item) in ancestors:
            raise ValueError("Invalid boundary contract.")
        if isinstance(item, Contract):
            if (
                set(item.__dict__) - set(type(item).model_fields)
                or item.__pydantic_extra__
                or item.__pydantic_private__
            ):
                raise ValueError("Invalid boundary contract.")
            children = item.__dict__.values()
        elif isinstance(item, Mapping):
            children = (*item.keys(), *item.values())
        elif isinstance(item, (tuple, list)):
            children = item
        else:
            return
        ancestors.add(id(item))
        for child in children:
            check(child, depth + 1)
        ancestors.remove(id(item))

    check(value)
    # Validate Python values before any JSON serializer can coerce bypassed
    # bool/int fields. Dumping to Python detaches nested models and containers.
    return model.model_validate(value.model_dump(warnings=False))
