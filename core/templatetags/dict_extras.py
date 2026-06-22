from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def phase_color(phase_code):
    """
    Retorna la clase Bootstrap de color según la fase del torneo.
    """
    phase_colors = {
        'PR': 'text-bg-secondary',      # Primera Ronda - Gris
        'SR': 'text-bg-info',           # Segunda Ronda - Azul claro
        'TR': 'text-bg-primary',        # Tercera Ronda - Azul
        'DR': 'text-bg-success',        # Dieciséisavos - Verde
        'OF': 'text-bg-warning',        # Octavos - Amarillo
        'CF': 'text-bg-danger',         # Cuartos - Rojo
        'SF': 'text-bg-dark',           # Semifinal - Oscuro
        'F': 'text-bg-warning',         # Final - Amarillo/Dorado
    }
    return phase_colors.get(phase_code, 'text-bg-light')

