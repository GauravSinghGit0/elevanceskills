from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def param_replace(context, **kwargs):
    """
    Preserves current GET parameters while updating/overriding specific keys.
    Usage: {% param_replace page=movies.next_page_number %}
    """
    request = context.get('request')
    if not request:
        return ""
    params = request.GET.copy()
    for k, v in kwargs.items():
        if v is not None and v != "":
            params[k] = v
        else:
            params.pop(k, None)
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else ""


@register.filter
def duration_format(minutes):
    """
    Converts integer duration in minutes to hours and minutes.
    Example: 148 -> "2h 28m", 45 -> "45m"
    """
    if not minutes:
        return "TBD"
    try:
        mins = int(minutes)
        if mins < 60:
            return f"{mins}m"
        hours = mins // 60
        remaining_mins = mins % 60
        if remaining_mins == 0:
            return f"{hours}h"
        return f"{hours}h {remaining_mins}m"
    except (ValueError, TypeError):
        return f"{minutes} min"


@register.filter
def star_list(rating):
    """
    Returns a list of 5 star statuses for 1-5 star ratings:
    e.g. rating=4 -> ['full', 'full', 'full', 'full', 'empty']
    """
    try:
        val = float(rating)
    except (ValueError, TypeError):
        val = 0.0

    stars = []
    for i in range(1, 6):
        if val >= i:
            stars.append('full')
        elif val >= (i - 0.5):
            stars.append('half')
        else:
            stars.append('empty')
    return stars
