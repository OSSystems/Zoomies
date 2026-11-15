"""Translations of the kids' and grown-ups' screens.

The language comes from the session's locale, which the installer sets for
the whole system; untranslated text stays in English.
"""

import gettext
import os

_translation = gettext.translation(
    "zoomies",
    os.environ.get("ZOOMIES_LOCALEDIR") or os.path.join(os.path.dirname(__file__), "locale"),
    fallback=True,
)

_ = _translation.gettext
ngettext = _translation.ngettext


def N_(message):
    """Mark text for translation where it is shown, not where it is written."""
    return message
