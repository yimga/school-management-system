"""Persistence-level guard for common start/end field pairs.

Admin ``ModelForm.clean`` provides field-local feedback.  This pre-save guard is
the second line of defence for imports, services and scripts that call ``save()``
without ``full_clean()``.  Equal dates/times remain valid for one-day or
instantaneous records; models requiring a strict positive duration (such as
AcademicYear) retain their explicit model/database constraint.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save

from apps.siteconfig.admin_form_intelligence import RANGE_FIELD_PAIRS


logger = logging.getLogger(__name__)


def validate_common_model_range(sender, instance, raw=False, **kwargs):
    if raw or sender._meta.abstract:
        return
    field_names = {field.name for field in sender._meta.concrete_fields}
    for start_name, end_name in RANGE_FIELD_PAIRS:
        if start_name not in field_names or end_name not in field_names:
            continue
        start = getattr(instance, start_name, None)
        end = getattr(instance, end_name, None)
        if start is not None and end is not None and end < start:
            logger.warning(
                "model_range_rejected model=%s start_field=%s end_field=%s",
                sender._meta.label_lower,
                start_name,
                end_name,
            )
            raise ValidationError(
                {end_name: f"Cannot be earlier than {start_name.replace('_', ' ')}."}
            )
        return


def connect_range_validation() -> None:
    pre_save.connect(
        validate_common_model_range,
        dispatch_uid="siteconfig.validate_common_model_range.v1",
        weak=False,
    )
