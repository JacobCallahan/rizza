from fauxfactory import *


def gen_string():
    """Overriden since it doesn't apply."""
    return gen_alphanumeric()


def gen_choice():
    """Overriden since it doesn't apply."""
    return None


def gen_alpha_long():
    return gen_alpha(256)


def gen_alphanumeric_long():
    return gen_alphanumeric(256)


def gen_cjk_long():
    return gen_cjk(256)


def gen_cyrillic_long():
    return gen_cyrillic(256)


def gen_html_long():
    return gen_html(256)


def gen_iplum_long():
    return gen_iplum(256)


def gen_latin1_long():
    return gen_latin1(256)


def gen_numeric_string_long():
    return gen_numeric_string(256)


def gen_utf8_long():
    return gen_utf8(256)
