"""Root service behind the grown-ups panel and the first-boot wizard.

Creating accounts and setting the PIN need root, while the panel and the
greeter run unprivileged. They ask this service over a socket that only the
parent account and the greeter can open. The parent's own session is
trusted; anyone else (the greeter) must send the PIN with each change, and
before any PIN exists only the PIN itself can be set.
"""

import argparse
import ctypes
import getpass
import json
import os
import pwd
import re
import socket
import struct
import subprocess
import sys
import time
import unicodedata

from . import state
from .i18n import N_

SOCKET = os.environ.get("ZOOMIES_ADMIN_SOCKET", "/run/zoomies-admin.sock")
GROUPS = {"little": "zoomies-kids", "older": "zoomies-older"}
PIN = re.compile(r"[0-9]{4,12}")
MAX_FAILURES = 5
LOCKOUT = 60


class Refused(Exception):
    pass


def request(action, **fields):
    """Send one request; raise Refused with a readable reason on failure."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(60)
            sock.connect(SOCKET)
            sock.sendall(json.dumps({"action": action, **fields}).encode() + b"\n")
            with sock.makefile("rb") as stream:
                data = stream.readline()
        reply = json.loads(data) if data else None
    except (OSError, ValueError) as error:
        raise Refused(f"the admin service is not reachable ({error})") from error
    # An empty or broken reply means the service died mid-request; never
    # take that for success.
    if not isinstance(reply, dict):
        raise Refused(N_("no answer from the admin service"))
    if "error" in reply:
        raise Refused(reply["error"])
    return reply


class Admin:
    def __init__(self):
        self.failures = 0
        self.locked_until = 0
        self.crypt = ctypes.CDLL(os.environ.get("ZOOMIES_LIBCRYPT", "libcrypt.so.2")).crypt
        self.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.crypt.restype = ctypes.c_char_p

    @property
    def parent(self):
        parent = state.load_config().get("parent")
        if not parent:
            raise Refused(N_("this system has no grown-up account"))
        return parent["user"]

    def shadow_hash(self):
        with open("/etc/shadow") as f:
            for line in f:
                fields = line.split(":")
                if fields[0] == self.parent:
                    return fields[1]
        return "!"

    def pin_set(self):
        stored = self.shadow_hash()
        return bool(stored) and not stored.startswith(("!", "*"))

    def pin_locked(self):
        # pam_faillock answers with the limits the logins use; a PAM service
        # that only reads its count never counts as a try itself.
        result = subprocess.run(
            ["pamtester", "zoomies-pin-lock", self.parent, "authenticate"],
            capture_output=True,
            text=True,
            env={**os.environ, "LC_ALL": "C"},
        )
        if result.returncode == 0:
            return False
        if "Authentication failure" in result.stderr:
            return True
        raise Refused(f"pamtester failed: {result.stderr.strip()}")

    def check_pin(self, pin):
        if time.monotonic() < self.locked_until:
            raise Refused(N_("too many wrong PINs, wait a minute"))
        stored = self.shadow_hash()
        if pin and self.pin_set():
            result = self.crypt(str(pin).encode(), stored.encode())
            if result and result.decode() == stored:
                self.failures = 0
                return
        self.failures += 1
        if self.failures >= MAX_FAILURES:
            self.failures = 0
            self.locked_until = time.monotonic() + LOCKOUT
        raise Refused(N_("wrong PIN"))

    def authorize(self, uid, message):
        if uid in (0, pwd.getpwnam(self.parent).pw_uid):
            return
        self.check_pin(message.get("pin"))

    def handle(self, uid, message):
        action = message.get("action")
        if action == "status":
            return {"pinSet": self.pin_set()}
        if action == "pin-locked":
            return {"locked": self.pin_locked()}
        if action == "set-pin":
            return self.set_pin(uid, message)
        if action in ("add-kid", "edit-kid", "remove-kid"):
            if not self.pin_set():
                raise Refused(N_("set the grown-ups PIN first"))
            self.authorize(uid, message)
            return getattr(self, action.replace("-", "_"))(message)
        raise Refused(f"unknown action {action!r}")

    def set_pin(self, uid, message):
        new = str(message.get("new", ""))
        if not PIN.fullmatch(new):
            raise Refused(N_("the PIN must be 4 to 12 digits"))
        # Before the first PIN exists there is nothing to protect; after
        # that, even the parent's own session must know the old PIN, so a
        # kid finding the panel open cannot lock the grown-ups out.
        if self.pin_set():
            self.check_pin(message.get("old"))
        subprocess.run(
            ["chpasswd"], input=f"{self.parent}:{new}\n", text=True, check=True
        )
        return {}

    @staticmethod
    def validate(message):
        name = str(message.get("name", "")).strip()
        if not 1 <= len(name) <= 32:
            raise Refused(N_("the name must have 1 to 32 characters"))
        # The name ends up in /etc/passwd, where these split fields.
        if any(c in ":," or unicodedata.category(c).startswith("C") for c in name):
            raise Refused(N_("the name cannot have commas, colons or control characters"))
        avatar = str(message.get("avatar") or state.AVATARS[0])
        if len(avatar) > 8:
            raise Refused(N_("the avatar must be a single emoji"))
        color = message.get("color") or "sky"
        if color not in state.COLORS:
            raise Refused(f"unknown colour {color!r}")
        kind = message.get("kind") or "little"
        if kind not in state.KINDS:
            raise Refused(f"unknown kind {kind!r}")
        if kind == "older" and not state.load_config().get("olderEnabled"):
            raise Refused(N_("older kid profiles are disabled on this system"))
        return {"avatar": avatar, "color": color, "kind": kind, "name": name}

    @staticmethod
    def username(name, taken):
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        base = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:20] or "kid"
        if not base[0].isalpha():
            base = f"kid-{base}"
        candidate, n = base, 1
        while candidate in taken or _user_exists(candidate):
            n += 1
            candidate = f"{base}{n}"
        return candidate

    def runtime_kid(self, user):
        profiles = state.load_profiles()
        for kid in profiles["kids"]:
            if kid["user"] == user:
                return profiles, kid
        if user in state.kids_by_user():
            raise Refused(N_("this kid is set in the system configuration"))
        raise Refused(f"no kid called {user!r}")

    def add_kid(self, message):
        fields = self.validate(message)
        profiles = state.load_profiles()
        taken = set(state.kids_by_user())
        user = self.username(fields["name"], taken)
        # The kid's group is their only group, and they get no subordinate
        # id ranges: the network rules match the group, so there must be
        # nothing to switch to with sg, newgrp or newgidmap. Sound, graphics
        # and gamepads come from logind, not from groups.
        subprocess.run(
            [
                "useradd",
                "--create-home",
                "--gid",
                GROUPS[fields["kind"]],
                "--key",
                "SUB_UID_COUNT=0",
                "--key",
                "SUB_GID_COUNT=0",
                "--comment",
                fields["name"],
                user,
            ],
            check=True,
        )
        profiles["kids"].append({"user": user, **fields})
        state.write_json(state.PROFILES, profiles)
        return {"user": user}

    def edit_kid(self, message):
        user = message.get("user")
        profiles, kid = self.runtime_kid(user)
        fields = self.validate({**kid, **message})
        if fields["kind"] != kid["kind"]:
            # A new primary group moves the kid between the network rules;
            # a running session would keep the old one, so end it.
            subprocess.run(["loginctl", "terminate-user", user])
            subprocess.run(["usermod", "--gid", GROUPS[fields["kind"]], user], check=True)
        subprocess.run(["usermod", "--comment", fields["name"], user], check=True)
        kid.update(fields)
        state.write_json(state.PROFILES, profiles)
        return {}

    def remove_kid(self, message):
        user = message.get("user")
        profiles, kid = self.runtime_kid(user)
        subprocess.run(["loginctl", "terminate-user", user])
        for _ in range(20):
            if subprocess.run(["pgrep", "-u", user], capture_output=True).returncode:
                break
            time.sleep(0.25)
        subprocess.run(["userdel", "--remove", user], check=True)
        profiles["kids"].remove(kid)
        state.write_json(state.PROFILES, profiles)
        policy = state.load_policy()
        policy.get("kids", {}).pop(user, None)
        for key in ("bonus", "stopped"):
            for day in policy.get(key, {}).values():
                day.pop(user, None)
        state.save_policy(policy)
        return {}


def _user_exists(name):
    try:
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


def serve():
    admin = Admin()
    # systemd passes the listening socket as fd 3.
    listener = socket.socket(fileno=3)
    while True:
        conn, _ = listener.accept()
        with conn:
            conn.settimeout(10)
            try:
                creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                _pid, uid, _gid = struct.unpack("3i", creds)
                with conn.makefile("rb") as stream:
                    message = json.loads(stream.readline(65536))
                reply = admin.handle(uid, message)
                print(f"uid {uid}: {message.get('action')} ok", flush=True)
            except Refused as error:
                reply = {"error": str(error)}
            except subprocess.CalledProcessError as error:
                reply = {"error": f"{error.cmd[0]} failed"}
            except Exception as error:  # noqa: BLE001 - keep serving
                print(f"error: {error!r}", file=sys.stderr, flush=True)
                reply = {"error": "something went wrong"}
            try:
                conn.sendall(json.dumps(reply).encode() + b"\n")
            except OSError:
                pass


# For grown-ups in a terminal or over SSH.
def main():
    parser = argparse.ArgumentParser(prog="zoomies-profile")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help=argparse.SUPPRESS)
    commands.add_parser("list")
    commands.add_parser("status")
    add = commands.add_parser("add")
    edit = commands.add_parser("edit")
    edit.add_argument("user")
    for command in (add, edit):
        command.add_argument("--name", required=command is add)
        command.add_argument("--avatar")
        command.add_argument("--color", choices=state.COLORS)
        command.add_argument("--kind", choices=state.KINDS)
    remove = commands.add_parser("remove")
    remove.add_argument("user")
    pin = commands.add_parser("set-pin")
    pin.add_argument("--stdin", action="store_true", help="read old and new PIN as two lines")
    args = parser.parse_args()

    try:
        if args.command == "serve":
            serve()
        elif args.command == "list":
            for kid in state.load_config()["kids"]:
                origin = "configuration" if kid["declared"] else "panel"
                print(f"{kid['user']}\t{kid['avatar']} {kid['name']}\t{kid['kind']}\t{origin}")
        elif args.command == "status":
            print(json.dumps(request("status")))
        elif args.command in ("add", "edit"):
            fields = {
                k: v
                for k, v in vars(args).items()
                if k in ("name", "avatar", "color", "kind", "user") and v is not None
            }
            reply = request(f"{args.command}-kid", **fields)
            print(reply.get("user", getattr(args, "user", None)))
        elif args.command == "remove":
            request("remove-kid", user=args.user)
        elif args.command == "set-pin":
            if args.stdin:
                # First line the current PIN (empty when none), then the new one.
                old, new = (sys.stdin.read().splitlines() + ["", ""])[:2]
            else:
                old = getpass.getpass("Current PIN (empty if none): ")
                new = getpass.getpass("New PIN: ")
                if getpass.getpass("New PIN again: ") != new:
                    sys.exit("The PINs do not match.")
            request("set-pin", old=old, new=new)
    except Refused as error:
        sys.exit(f"zoomies-profile: {error}")
