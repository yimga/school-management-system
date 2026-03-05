"""
Minimal state machine engine: get current state and transition by event.
"""
from typing import Optional

from .models import StateMachineDefinition, EntityState


def _get_definition(school, definition_code):
    return (
        StateMachineDefinition.objects.filter(
            code=definition_code,
            is_active=True,
            school=school,
        ).first()
        or StateMachineDefinition.objects.filter(
            code=definition_code,
            is_active=True,
            school__isnull=True,
        ).first()
    )


def get_state(school, entity_type: str, entity_id: str, definition_code: str) -> Optional[str]:
    """Return current state for entity, or None if not set."""
    definition = _get_definition(school, definition_code)
    if not definition:
        return None
    record = EntityState.objects.filter(
        definition=definition,
        school=school,
        entity_type=entity_type,
        entity_id=str(entity_id),
    ).first()
    return record.current_state if record else None


def transition(
    school,
    entity_type: str,
    entity_id: str,
    definition_code: str,
    event: str,
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Apply event to entity; move state if transition allowed.
    Returns (success, from_state, to_state). to_state is None on failure.
    """
    definition = _get_definition(school, definition_code)
    if not definition:
        return False, None, None
    states = definition.states or []
    transitions = definition.transitions or []
    record = EntityState.objects.filter(
        definition=definition,
        school=school,
        entity_type=entity_type,
        entity_id=str(entity_id),
    ).first()
    from_state = record.current_state if record else None
    if from_state is None and states:
        from_state = states[0]
    for t in transitions:
        if not isinstance(t, dict):
            continue
        if t.get("from_state") == from_state and t.get("event") == event:
            to_state = t.get("to_state")
            if to_state not in states:
                continue
            if record:
                record.current_state = to_state
                record.save(update_fields=["current_state", "updated_at"])
            else:
                EntityState.objects.create(
                    definition=definition,
                    school=school,
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    current_state=to_state,
                )
            return True, from_state, to_state
    return False, from_state, None
