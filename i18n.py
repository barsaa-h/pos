"""i18n helper — loads locale JSON and provides translation function."""
import json
import os

_LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
_CACHE = {}

def _load_locale(lang):
    """Load a locale JSON file, caching it in memory."""
    if lang in _CACHE:
        return _CACHE[lang]
    path = os.path.join(_LOCALE_DIR, f"{lang}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            _CACHE[lang] = json.load(f)
    except Exception:
        _CACHE[lang] = {}
    return _CACHE[lang]

def t(key, lang="mn", default=None):
    """Translate a key for the given language. Falls back to Mongolian."""
    locale = _load_locale(lang)
    if key in locale:
        return locale[key]
    mn = _load_locale("mn")
    if key in mn:
        return mn[key]
    return default or key

def get_locale():
    try:
        from config import get_config
        lang = get_config("ui_language")
        if lang in ("mn", "en"):
            return lang
    except Exception:
        pass
    return "mn"

# Jinja2 template global: {{ _t('key') }}
def _t(key):
    return t(key, get_locale())
