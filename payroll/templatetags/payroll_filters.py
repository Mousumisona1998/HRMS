from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get a value from a dictionary by key"""
    if dictionary and hasattr(dictionary, 'get'):
        return dictionary.get(key, 0)
    return 0