import re


class ProviderNotRegistered(LookupError):
    pass


_providers = {}
_PROVIDER_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")


def register_provider(name, adapter):
    if not isinstance(name, str) or not _PROVIDER_NAME.fullmatch(name):
        raise ValueError("Provider names must be lowercase route-safe slugs of at most 32 characters.")
    _providers[name] = adapter
    return adapter


def get_provider(name):
    try:
        return _providers[name]
    except KeyError as exc:
        raise ProviderNotRegistered("The configured SMS provider is unavailable.") from exc
