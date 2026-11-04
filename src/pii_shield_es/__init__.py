"""Alias obsoleto: el paquete ahora se llama ``datashield_es`` (DataShield).

``import pii_shield_es`` sigue funcionando para no romper código existente, pero emite un
``DeprecationWarning``. Cambia tus imports a ``from datashield_es import ...``.
"""

import warnings

from datashield_es import *  # noqa: F403
from datashield_es import __all__, __version__  # noqa: F401

warnings.warn(
    "pii_shield_es ahora se llama datashield_es; actualiza tus imports "
    "(from datashield_es import ...). El alias se eliminará en una versión futura.",
    DeprecationWarning,
    stacklevel=2,
)
