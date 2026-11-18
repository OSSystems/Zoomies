"""Checks a fixed network address as the grown-ups typed it.

The admin service checks it before NetworkManager sees it, so a mistake
comes back as a sentence the panel can show, not as NetworkManager's
error. Only IPv4: home routers hand out IPv6 by themselves.
"""

import ipaddress
import re

from .i18n import N_

# Nearly every home network is a /24, so the panel does not ask for a mask.
DEFAULT_PREFIX = 24


class Invalid(ValueError):
    pass


def fixed(address, gateway="", dns=""):
    """The address, prefix, router and DNS servers to save, or Invalid."""
    text = str(address).strip()
    if not text:
        raise Invalid(N_("type the address"))
    if "/" not in text:
        text += f"/{DEFAULT_PREFIX}"
    try:
        interface = ipaddress.IPv4Interface(text)
    except ValueError as error:
        raise Invalid(N_("the address is not valid; it looks like 192.168.1.50")) from error
    network = interface.network
    if network.prefixlen < 31 and interface.ip in (
        network.network_address,
        network.broadcast_address,
    ):
        raise Invalid(N_("this address cannot be used on its network"))
    router = None
    if str(gateway).strip():
        try:
            router = ipaddress.IPv4Address(str(gateway).strip())
        except ValueError as error:
            raise Invalid(N_("the router is not a valid address")) from error
        if router not in network or router == interface.ip:
            raise Invalid(N_("the router must be on the same network as the address"))
    servers = []
    for item in re.split(r"[\s,;]+", str(dns).strip()):
        if not item:
            continue
        try:
            servers.append(str(ipaddress.IPv4Address(item)))
        except ValueError as error:
            raise Invalid(N_("the DNS servers are not valid addresses")) from error
    return {
        "address": str(interface.ip),
        "prefix": network.prefixlen,
        "gateway": None if router is None else str(router),
        "dns": servers,
    }
