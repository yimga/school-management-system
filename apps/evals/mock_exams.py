"""
Mock exam utilities for Phase 1.2.3: Mock Exam Score Blending

Provides utility functions for calculating blended scores and detecting
FORM 5/7 classrooms for automatic mock exam setup.

The MockExamSetting model is defined in models.py to ensure proper Django integration.
"""


def calculate_blended_score(final_score, mock_score, setting):
    """Calculate blended score: (final × final_weight/100) + (mock × mock_weight/100).

    Args:
        final_score: Final exam score (Decimal or float or None)
        mock_score: Mock exam score (Decimal or float or None)
        setting: MockExamSetting instance

    Returns:
        float: Blended score rounded to 2 decimal places, or final_score if blending disabled.

    Examples:
        >>> setting = MockExamSetting(..., final_weight=70, mock_weight=30, is_active=True)
        >>> calculate_blended_score(18.5, 16.0, setting)
        17.95  # (18.5 * 0.7) + (16.0 * 0.3) = 12.95 + 4.8 = 17.75
    """
    if not setting.is_active or mock_score is None:
        return final_score
    if final_score is None:
        return 0.0

    final = float(final_score)
    mock = float(mock_score)
    blended = (final * setting.final_weight / 100) + (mock * setting.mock_weight / 100)
    return round(blended, 2)


def should_use_mock_blending(classroom):
    """Detect if a classroom should use mock exam blending (FORM 5/7 detection).

    Checks both name and code for indicators of advanced forms:
    - Names: "FORM 5", "FORM 7", "UPPER 6", "FORM VI", "FORM VII"
    - Codes: "F5", "F7", "U6", "A2"

    Args:
        classroom: Classroom instance

    Returns:
        bool: True if classroom is detected as FORM 5/7 type

    Examples:
        >>> classroom1 = Classroom(name="FORM 5A")
        >>> should_use_mock_blending(classroom1)
        True

        >>> classroom2 = Classroom(name="FORM 1", code="F1")
        >>> should_use_mock_blending(classroom2)
        False
    """
    if not classroom:
        return False

    # Check classroom name (case-insensitive)
    name_upper = (classroom.name or "").upper()
    upper_form_names = ("FORM 5", "FORM 7", "UPPER 6", "FORM VI", "FORM VII")
    if any(name in name_upper for name in upper_form_names):
        return True

    # Check classroom code (case-insensitive)
    code_upper = (classroom.code or "").upper()
    upper_form_codes = ("F5", "F7", "U6", "A2")
    if code_upper in upper_form_codes:
        return True

    return False
