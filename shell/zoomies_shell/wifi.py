"""Wi-Fi and the cable through NetworkManager, for the admin service.

The admin service runs these for the grown-ups' panel and for the first-boot
wizard, which runs in the greeter before any PIN exists. Networks are saved
for the whole computer, so the kids' sessions get online too when their
internet rules allow it, and the password never shows on a command line.
"""

import socket
import time

import gi

from . import addresses
from .i18n import N_

gi.require_version("NM", "1.0")
from gi.repository import GLib, NM  # noqa: E402

# NM-80211ApFlags and NM-80211ApSecurityFlags.
AP_PRIVACY = 0x1
KEY_MGMT_PSK = 0x100
KEY_MGMT_802_1X = 0x200
KEY_MGMT_SAE = 0x400
KEY_MGMT_OWE = 0x800

CONNECT_SECONDS = 45
SCAN_SECONDS = 6


class Failed(Exception):
    pass


def ssid_text(data):
    """A name to show: SSIDs are bytes, in no particular encoding."""
    return NM.utils_ssid_to_utf8(data.get_data()) if data else ""


def ssid_bytes(data):
    return bytes(data.get_data()) if data else b""


class Session:
    """A NetworkManager client driven to completion, one call at a time."""

    def __init__(self):
        self.context = GLib.MainContext.new()
        self.context.push_thread_default()
        try:
            self.client = NM.Client.new(None)
        except GLib.Error as error:
            self.context.pop_thread_default()
            raise Failed(N_("the network service is not running")) from error
        if not self.client.get_nm_running():
            self.context.pop_thread_default()
            raise Failed(N_("the network service is not running"))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.context.pop_thread_default()

    def wait(self, done, seconds):
        deadline = time.monotonic() + seconds
        while not done() and time.monotonic() < deadline:
            if not self.context.iteration(False):
                time.sleep(0.05)
        return done()

    def call(self, start, finish, seconds=30):
        box = {}

        def callback(source, result, *_):
            try:
                box["value"] = finish(source, result)
            except GLib.Error as error:
                box["error"] = error

        start(callback)
        if not self.wait(lambda: box, seconds):
            raise Failed(N_("the network service did not answer"))
        if "error" in box:
            raise Failed(box["error"].message)
        return box["value"]

    def devices(self, kind):
        return [
            d for d in self.client.get_devices() if d.get_device_type() == kind and d.get_managed()
        ]

    def wifi_device(self):
        devices = self.devices(NM.DeviceType.WIFI)
        if not devices:
            raise Failed(N_("this computer has no Wi-Fi"))
        return devices[0]

    def saved(self, ssid):
        """Saved connections to the network with these SSID bytes."""
        found = []
        for connection in self.client.get_connections():
            setting = connection.get_setting_wireless()
            if setting is not None and ssid_bytes(setting.get_ssid()) == ssid:
                found.append(connection)
        return found

    def status(self):
        wifi = self.devices(NM.DeviceType.WIFI)
        connected = None
        wifi_address = None
        if wifi:
            ap = wifi[0].get_active_access_point()
            if ap is not None and wifi[0].get_state() == NM.DeviceState.ACTIVATED:
                connected = ssid_text(ap.get_ssid())
                wifi_address = current(wifi[0])["address"]
        cables = self.devices(NM.DeviceType.ETHERNET)
        plugged = next((d for d in cables if d.get_state() == NM.DeviceState.ACTIVATED), None)
        return {
            "cable": bool(cables),
            "connected": connected,
            "enabled": self.client.wireless_get_enabled(),
            "online": self.client.get_primary_connection() is not None,
            "wifi": bool(wifi),
            "wifiAddress": wifi_address,
            "wired": plugged is not None,
            "wiredAddress": current(plugged)["address"] if plugged else None,
        }

    def target(self, message):
        """The saved connection a request names, or None for a cable that
        has none yet, and the device it is for."""
        if message.get("cable"):
            cables = self.devices(NM.DeviceType.ETHERNET)
            if not cables:
                raise Failed(N_("this computer has no cable port"))
            device = cables[0]
            active = device.get_active_connection()
            if active is not None and active.get_connection() is not None:
                return active.get_connection(), device
            return next(iter(device.get_available_connections()), None), device
        saved = self.saved(ssid_of(message))
        if not saved:
            raise Failed(N_("this network is not saved"))
        return saved[0], self.wifi_device()

    def address(self, message):
        """How a connection gets its address: what is saved, and what the
        device has now when the connection is up."""
        connection, device = self.target(message)
        setting = connection.get_setting_ip4_config() if connection else None
        method = setting.get_method() if setting else NM.SETTING_IP4_CONFIG_METHOD_AUTO
        saved = {"address": None, "gateway": None, "dns": []}
        if setting is not None:
            if setting.get_num_addresses():
                first = setting.get_address(0)
                saved["address"] = f"{first.get_address()}/{first.get_prefix()}"
            saved["gateway"] = setting.get_gateway()
            saved["dns"] = [setting.get_dns(i) for i in range(setting.get_num_dns())]
        active = device.get_active_connection()
        up = (
            connection is not None
            and same(active, connection)
            and device.get_state() == NM.DeviceState.ACTIVATED
        )
        return {
            "fixed": method == NM.SETTING_IP4_CONFIG_METHOD_MANUAL,
            "now": current(device) if up else None,
            "saved": saved,
        }

    def set_address(self, message):
        connection, device = self.target(message)
        fixed = None
        if message.get("fixed"):
            try:
                fixed = addresses.fixed(
                    message.get("address", ""), message.get("gateway", ""), message.get("dns", "")
                )
            except addresses.Invalid as error:
                raise Failed(str(error)) from error
        new = connection is None
        if new:
            # NetworkManager makes a cable's connection only once one is
            # plugged in; a fixed address may be set before that.
            connection = NM.SimpleConnection.new()
            general = NM.SettingConnection.new()
            general.set_property(NM.SETTING_CONNECTION_ID, "Cable")
            general.set_property(NM.SETTING_CONNECTION_TYPE, NM.SETTING_WIRED_SETTING_NAME)
            general.set_property(NM.SETTING_CONNECTION_UUID, NM.utils_uuid_generate())
            general.set_property(NM.SETTING_CONNECTION_INTERFACE_NAME, device.get_iface())
            connection.add_setting(general)
            connection.add_setting(NM.SettingWired.new())
        setting = connection.get_setting_ip4_config()
        if setting is None:
            setting = NM.SettingIP4Config.new()
            connection.add_setting(setting)
        setting.clear_addresses()
        setting.clear_dns()
        setting.set_property(NM.SETTING_IP_CONFIG_GATEWAY, None)
        if fixed is None:
            setting.set_property(NM.SETTING_IP_CONFIG_METHOD, NM.SETTING_IP4_CONFIG_METHOD_AUTO)
        else:
            setting.set_property(NM.SETTING_IP_CONFIG_METHOD, NM.SETTING_IP4_CONFIG_METHOD_MANUAL)
            setting.add_address(NM.IPAddress.new(socket.AF_INET, fixed["address"], fixed["prefix"]))
            setting.set_property(NM.SETTING_IP_CONFIG_GATEWAY, fixed["gateway"])
            for server in fixed["dns"]:
                setting.add_dns(server)
        if new:
            connection = self.call(
                lambda cb: self.client.add_connection_async(connection, True, None, cb, None),
                lambda c, r: c.add_connection_finish(r),
            )
        else:
            self.call(
                lambda cb: connection.commit_changes_async(True, None, cb, None),
                lambda c, r: c.commit_changes_finish(r),
            )
        # A connection in use takes the new address only when it starts
        # again; one that is not in use takes it next time. It is not
        # waited for: with no router to answer, that takes most of a
        # minute, and the greeter's PIN pad waits on this service too.
        if same(device.get_active_connection(), connection):
            self.call(
                lambda cb: self.client.activate_connection_async(
                    connection, device, None, None, cb
                ),
                lambda c, r: c.activate_connection_finish(r),
            )
        return {}

    def scan(self):
        device = self.wifi_device()
        before = device.get_last_scan()
        try:
            self.call(
                lambda cb: device.request_scan_async(None, cb, None),
                lambda d, r: d.request_scan_finish(r),
            )
            # The scan results arrive a moment after the request returns.
            self.wait(lambda: device.get_last_scan() != before, SCAN_SECONDS)
        except Failed:
            # NetworkManager refuses scans too close together; the last
            # one is recent enough then.
            pass
        active = device.get_active_access_point()
        active_ssid = ssid_bytes(active.get_ssid()) if active else None
        networks = {}
        for ap in device.get_access_points():
            ssid = ssid_bytes(ap.get_ssid())
            if not ssid:
                continue
            security = ap.get_wpa_flags() | ap.get_rsn_flags()
            privacy = bool(ap.get_flags() & AP_PRIVACY)
            network = {
                "connected": ssid == active_ssid and device.get_state() == NM.DeviceState.ACTIVATED,
                # The name is for showing; the bytes, in hex, say which
                # network it is.
                "id": ssid.hex(),
                "password": bool(security & (KEY_MGMT_PSK | KEY_MGMT_SAE)),
                "secure": privacy or bool(security),
                "ssid": ssid_text(ap.get_ssid()),
                "strength": ap.get_strength(),
                # School and office networks need a user name, and old WEP
                # ones a key of their own; the full network editor sets
                # those up.
                "supported": not security & KEY_MGMT_802_1X and not (privacy and not security),
            }
            best = networks.get(ssid)
            if best is None or network["strength"] > best["strength"]:
                networks[ssid] = network
        for ssid, network in networks.items():
            network["known"] = bool(self.saved(ssid))
        return sorted(networks.values(), key=lambda n: (not n["connected"], -n["strength"]))

    def connect(self, ssid, password=None, hidden=False):
        device = self.wifi_device()
        saved = self.saved(ssid)
        if saved and not password:
            reasons, handler = self.watch_reasons(device)
            try:
                active = self.call(
                    lambda cb: self.client.activate_connection_async(
                        saved[0], device, None, None, cb
                    ),
                    lambda c, r: c.activate_connection_finish(r),
                )
                return self.until_active(active, device, reasons=reasons)
            finally:
                device.handler_disconnect(handler)
        # A new password replaces what was saved.
        for connection in saved:
            self.delete(connection)
        connection = NM.SimpleConnection.new()
        general = NM.SettingConnection.new()
        general.set_property(NM.SETTING_CONNECTION_ID, NM.utils_ssid_to_utf8(ssid))
        general.set_property(NM.SETTING_CONNECTION_TYPE, NM.SETTING_WIRELESS_SETTING_NAME)
        uuid = NM.utils_uuid_generate()
        general.set_property(NM.SETTING_CONNECTION_UUID, uuid)
        connection.add_setting(general)
        wireless = NM.SettingWireless.new()
        wireless.set_property(NM.SETTING_WIRELESS_SSID, GLib.Bytes.new(ssid))
        wireless.set_property(NM.SETTING_WIRELESS_HIDDEN, bool(hidden))
        connection.add_setting(wireless)
        ap = next((a for a in device.get_access_points() if ssid_bytes(a.get_ssid()) == ssid), None)
        flags = (ap.get_wpa_flags() | ap.get_rsn_flags()) if ap else 0
        key_mgmt = None
        if password:
            # WPA3-only networks take the password through SAE.
            sae_only = flags & KEY_MGMT_SAE and not flags & KEY_MGMT_PSK
            key_mgmt = "sae" if sae_only else "wpa-psk"
        elif flags & KEY_MGMT_OWE:
            # Encrypted without a password.
            key_mgmt = "owe"
        if key_mgmt is not None:
            security = NM.SettingWirelessSecurity.new()
            security.set_property(NM.SETTING_WIRELESS_SECURITY_KEY_MGMT, key_mgmt)
            if password:
                security.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
            connection.add_setting(security)
        reasons, handler = self.watch_reasons(device)
        try:
            active = self.call(
                lambda cb: self.client.add_and_activate_connection_async(
                    connection, device, None, None, cb
                ),
                lambda c, r: c.add_and_activate_connection_finish(r),
            )
            return self.until_active(active, device, forget=uuid, reasons=reasons)
        finally:
            device.handler_disconnect(handler)

    def until_active(self, active, device, forget=None, reasons=None):
        """Wait for a connection to come up; if it fails, delete the new
        connection `forget` names by its UUID."""

        def settled():
            return active.get_state() in (
                NM.ActiveConnectionState.ACTIVATED,
                NM.ActiveConnectionState.DEACTIVATED,
            )

        self.wait(settled, CONNECT_SECONDS)
        if active.get_state() == NM.ActiveConnectionState.ACTIVATED:
            return {}
        # A wrong password must not stay saved and retried at every boot.
        # The failed activation no longer knows its connection, so it is
        # found by the UUID it was made with.
        connection = self.client.get_connection_by_uuid(forget) if forget else None
        if connection is not None:
            self.delete(connection)
        if NM.DeviceStateReason.NO_SECRETS in (reasons or ()):
            raise Failed(N_("could not connect: check the password"))
        raise Failed(N_("could not connect to this network"))

    def watch_reasons(self, device):
        """Why the device changed state, as it goes: by the time an
        activation fails, the device has moved on to other reasons."""
        reasons = []
        handler = device.connect("state-changed", lambda _d, _new, _old, why: reasons.append(why))
        return reasons, handler

    def delete(self, connection):
        self.call(
            lambda cb: connection.delete_async(None, cb, None),
            lambda c, r: c.delete_finish(r),
        )

    def forget(self, ssid):
        for connection in self.saved(ssid):
            self.delete(connection)
        return {}

    def enable(self, on):
        self.call(
            lambda cb: self.client.dbus_set_property(
                NM.DBUS_PATH,
                NM.DBUS_INTERFACE,
                "WirelessEnabled",
                GLib.Variant("b", bool(on)),
                -1,
                None,
                cb,
                None,
            ),
            lambda c, r: c.dbus_set_property_finish(r),
        )
        return {}


def current(device):
    """The address, router and DNS servers a device has now."""
    config = device.get_ip4_config() if device is not None else None
    if config is None:
        return {"address": None, "gateway": None, "dns": []}
    found = config.get_addresses()
    return {
        "address": found[0].get_address() if found else None,
        "gateway": config.get_gateway(),
        "dns": list(config.get_nameservers()),
    }


def same(active, connection):
    """Whether an active connection runs this saved connection."""
    return active is not None and active.get_uuid() == connection.get_uuid()


def ssid_of(message):
    """Networks from a scan come by their bytes; a hidden one by the name a
    grown-up typed."""
    try:
        ssid = bytes.fromhex(message["id"]) if "id" in message else None
    except (TypeError, ValueError):
        ssid = None
    if ssid is None:
        ssid = str(message.get("ssid", "")).encode()
    if not 1 <= len(ssid) <= 32:
        raise Failed(N_("pick a network"))
    return ssid


def run(action, message):
    """Run one network action of the admin service."""
    with Session() as session:
        if action == "wifi-status":
            return session.status()
        if action == "wifi-scan":
            return {"networks": session.scan()}
        if action == "address":
            return session.address(message)
        if action == "set-address":
            return session.set_address(message)
        ssid = ssid_of(message)
        if action == "wifi-connect":
            password = message.get("password") or None
            if password is not None and not 8 <= len(password) <= 63:
                raise Failed(N_("Wi-Fi passwords have 8 to 63 characters"))
            return session.connect(ssid, password, bool(message.get("hidden")))
        if action == "wifi-forget":
            return session.forget(ssid)
        if action == "wifi-enable":
            return session.enable(message.get("on"))
    raise Failed(f"unknown action {action!r}")
