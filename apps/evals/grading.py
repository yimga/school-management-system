"""
Grading utilities for Phase 1.2.4: Internationalization & Multi-Region Support

Provides score conversion, formatting, and grade calculation functions
for multiple grading scales across different regions.
"""

from decimal import Decimal
from django.core.cache import cache


# Global grading scale definitions
GRADING_SCALES = {
    '0-20': {
        'min': Decimal('0'),
        'max': Decimal('20'),
        'grades': {
            'A': Decimal('18'),
            'B': Decimal('15'),
            'C': Decimal('12'),
            'D': Decimal('9'),
            'F': Decimal('0'),
        },
        'display': lambda score: f"{score:.0f}/20"
    },
    '0-100': {
        'min': Decimal('0'),
        'max': Decimal('100'),
        'grades': {
            'A': Decimal('90'),
            'B': Decimal('80'),
            'C': Decimal('70'),
            'D': Decimal('60'),
            'F': Decimal('0'),
        },
        'display': lambda score: f"{score:.0f}%"
    },
    '0-10': {
        'min': Decimal('0'),
        'max': Decimal('10'),
        'grades': {
            'A': Decimal('9'),
            'B': Decimal('7.5'),
            'C': Decimal('6'),
            'D': Decimal('4.5'),
            'F': Decimal('0'),
        },
        'display': lambda score: f"{score:.1f}/10"
    },
    'a-f': {
        'min': Decimal('0'),
        'max': Decimal('4'),
        'grades': {
            'A': Decimal('4'),
            'B': Decimal('3'),
            'C': Decimal('2'),
            'D': Decimal('1'),
            'F': Decimal('0'),
        },
        'display': lambda score: ('F', 'D', 'C', 'B', 'A')[min(4, int(score))]
    },
    'gpa': {
        'min': Decimal('0'),
        'max': Decimal('4.0'),
        'grades': {
            'A': Decimal('4.0'),
            'B': Decimal('3.0'),
            'C': Decimal('2.0'),
            'D': Decimal('1.0'),
            'F': Decimal('0'),
        },
        'display': lambda score: f"{score:.2f}"
    }
}


def convert_score(score, from_scale, to_scale):
    """
    Convert a score from one grading scale to another.
    
    Args:
        score: Numerical score (Decimal or float)
        from_scale: Source scale identifier ('0-20', '0-100', etc.)
        to_scale: Target scale identifier
    
    Returns:
        Decimal: Converted score rounded to 2 decimal places
    
    Examples:
        >>> convert_score(15, '0-20', '0-100')  # 75.0
        >>> convert_score(85, '0-100', '0-20')  # 17.0
        >>> convert_score(7.5, '0-10', 'gpa')   # 3.0
    """
    if from_scale == to_scale:
        return Decimal(str(score))
    
    cache_key = f"score_convert:{score}:{from_scale}:{to_scale}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    
    from_config = GRADING_SCALES.get(from_scale)
    to_config = GRADING_SCALES.get(to_scale)
    
    if not from_config or not to_config:
        raise ValueError(f"Unknown scale: {from_scale} or {to_scale}")
    
    # Normalize to 0-1 range
    from_min = from_config['min']
    from_max = from_config['max']
    to_min = to_config['min']
    to_max = to_config['max']
    
    score_decimal = Decimal(str(score))
    
    # Handle edge case: score outside valid range
    score_decimal = max(from_min, min(from_max, score_decimal))
    
    # Normalize: (score - min) / (max - min)
    normalized = (score_decimal - from_min) / (from_max - from_min)
    
    # Convert: normalized * (to_max - to_min) + to_min
    converted = normalized * (to_max - to_min) + to_min
    
    result = converted.quantize(Decimal('0.01'))  # Round to 2 decimal places
    cache.set(cache_key, result, 3600)  # Cache for 1 hour
    
    return result


def get_grade_letter(score, scale='0-20'):
    """
    Get letter grade (A-F) from numerical score.
    
    Args:
        score: Numerical score
        scale: Scale identifier
    
    Returns:
        str: Letter grade (A, B, C, D, or F)
    
    Examples:
        >>> get_grade_letter(18, '0-20')  # 'A'
        >>> get_grade_letter(12, '0-20')  # 'C'
        >>> get_grade_letter(90, '0-100')  # 'A'
    """
    config = GRADING_SCALES.get(scale, GRADING_SCALES['0-20'])
    grades = config['grades']
    
    score_decimal = Decimal(str(score))
    
    for letter in ('A', 'B', 'C', 'D', 'F'):
        if score_decimal >= grades[letter]:
            return letter
    
    return 'F'


def format_score(score, scale='0-20'):
    """
    Format score according to scale's display format.
    
    Args:
        score: Numerical score
        scale: Scale identifier
    
    Returns:
        str: Formatted score string
    
    Examples:
        >>> format_score(18.5, '0-20')  # '19/20'
        >>> format_score(87.3, '0-100')  # '87%'
        >>> format_score(3.75, 'gpa')  # '3.75'
    """
    config = GRADING_SCALES.get(scale, GRADING_SCALES['0-20'])
    display_fn = config['display']
    
    try:
        return display_fn(float(score))
    except (TypeError, ValueError):
        return str(score)


def is_passing_score(score, scale='0-20'):
    """
    Determine if a score is passing (not an 'F').
    
    Args:
        score: Numerical score
        scale: Scale identifier
    
    Returns:
        bool: True if score is passing (grade != F)
    
    Examples:
        >>> is_passing_score(12, '0-20')  # True (grade C)
        >>> is_passing_score(8, '0-20')  # False (grade F)
    """
    letter_grade = get_grade_letter(score, scale)
    return letter_grade != 'F'


def get_average_grade(scores, scale='0-20'):
    """
    Calculate average of multiple scores.
    
    Args:
        scores: List of numerical scores
        scale: Scale identifier
    
    Returns:
        Decimal: Average score rounded to 2 decimal places
    """
    if not scores:
        return Decimal('0')
    
    total = sum(Decimal(str(s)) for s in scores)
    average = total / Decimal(str(len(scores)))
    
    return average.quantize(Decimal('0.01'))


def scale_score(score, from_min, from_max, to_min=0, to_max=100):
    """
    Scale a score from one range to another (linear transformation).
    
    Args:
        score: Original score
        from_min: Minimum of original range
        from_max: Maximum of original range
        to_min: Minimum of target range (default 0)
        to_max: Maximum of target range (default 100)
    
    Returns:
        Decimal: Scaled score
    
    Examples:
        >>> scale_score(15, 0, 20, 0, 100)  # 75.0
        >>> scale_score(75, 0, 100, 0, 20)  # 15.0
    """
    score = Decimal(str(score))
    from_min = Decimal(str(from_min))
    from_max = Decimal(str(from_max))
    to_min = Decimal(str(to_min))
    to_max = Decimal(str(to_max))
    
    # Avoid division by zero
    if from_max == from_min:
        return to_min
    
    # Linear transformation: (score - from_min) / (from_max - from_min) * (to_max - to_min) + to_min
    normalized = (score - from_min) / (from_max - from_min)
    scaled = normalized * (to_max - to_min) + to_min
    
    return scaled.quantize(Decimal('0.01'))


# Currency formatting utilities

CURRENCY_SYMBOLS = {
    'XAF': 'FCFA',  # Cameroon/Central Africa
    'USD': '$',      # USA
    'EUR': '€',      # Europe
    'GBP': '£',      # UK
    'KES': 'Ksh',    # Kenya
    'NGN': '₦',      # Nigeria
    'ZAR': 'R',      # South Africa
    'GHS': 'GH₵',    # Ghana
    'TZS': 'TSh',    # Tanzania
}


def format_currency(amount, currency_code='XAF', include_symbol=True):
    """
    Format amount as currency.
    
    Args:
        amount: Numerical amount
        currency_code: ISO currency code
        include_symbol: Whether to include currency symbol
    
    Returns:
        str: Formatted currency string
    
    Examples:
        >>> format_currency(15000, 'XAF')  # 'FCFA 15,000.00'
        >>> format_currency(85.50, 'USD')  # '$ 85.50'
    """
    symbol = CURRENCY_SYMBOLS.get(currency_code, currency_code)
    
    if include_symbol:
        return f"{symbol} {float(amount):,.2f}"
    else:
        return f"{float(amount):,.2f}"
