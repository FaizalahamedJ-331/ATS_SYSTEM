from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Return mapping[key], or None when missing."""
    if mapping is None:
        return None
    return mapping.get(key)
