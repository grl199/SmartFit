"""Utilidades puras de códigos de barras."""


def is_restricted_barcode(code: str | None) -> bool:
    """¿Es un código de circulación restringida (uso interno de una empresa/tienda)?

    Open Food Facts los marca como «código de barras ambiguo»: distintos fabricantes y tiendas pueden reutilizar el
    mismo número para productos diferentes. GS1 reserva los prefijos 02 y 20-29 (EAN-13) y, en UPC-A, los sistemas
    2 (peso variable) y 4 (uso local). Los códigos largos que empiezan por 2 (p. ej. los de 24 dígitos de tienda)
    se tratan igual.
    """
    if not code or not code.isdigit():
        return False
    if len(code) == 13 and (code.startswith(("02", "04")) or code[0] == "2"):
        return True
    return len(code) > 13 and code[0] == "2"
