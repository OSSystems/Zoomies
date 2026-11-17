"""Screen time enforcement.

`zoomies-time daemon` counts the minutes each kid spends in the foreground
session and ends the session once the budget or the allowed hours run out.
`zoomies-time check` runs from PAM so a kid whose time is up cannot log in
again, whatever the greeter shows. The daemon also tells the firewall which
kids may be online.
"""

import argparse
import datetime
import os
import pwd
import socket
import subprocess
import sys
import time

from . import internet, state
from .i18n import _, ngettext

TICK = 5
WARN_AT_SECONDS = (300, 60)
FAILSAFE_SECONDS = 30
# The firewall lets kids online only for a lease (see internet.py), so it
# is renewed well before it ends, even when nothing changed.
INTERNET_REFRESH_SECONDS = internet.LEASE_SECONDS // 3


def user_state(user):
    result = subprocess.run(
        ["loginctl", "show-user", user, "--property=State", "--value"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "offline"


def as_user(user, *command):
    uid = pwd.getpwnam(user).pw_uid
    subprocess.Popen(
        [
            "runuser",
            "-u",
            user,
            "--",
            "env",
            f"XDG_RUNTIME_DIR=/run/user/{uid}",
            f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
            *command,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def warn(user, remaining, sound):
    if sound:
        as_user(user, "pw-play", sound)
    # Older kids work in a desktop with notifications; little kids are in a
    # fullscreen game, where only the sound gets through.
    minutes = max(1, remaining // 60)
    as_user(
        user,
        "notify-send",
        "--urgency=critical",
        "--app-name=Zoomies",
        ngettext("{minutes} minute left", "{minutes} minutes left", minutes).format(minutes=minutes),
        _("Save your work, time is almost up for today."),
    )


def log(message):
    print(message, file=sys.stderr, flush=True)


def end_session(user, reason):
    log(f"ending the session of {user}: {reason}")
    subprocess.run(["loginctl", "terminate-user", user])


def send_online(config, uids, sent, now):
    """Tell the firewall who is online, when that changed or is due again."""
    backend = config.get("internet", {}).get("backend")
    if backend is None or (uids == sent[0] and now - sent[1] < INTERNET_REFRESH_SECONDS):
        return sent
    try:
        internet.apply(backend, uids)
    except (OSError, subprocess.SubprocessError) as error:
        log(f"cannot update who is online: {getattr(error, 'stderr', None) or error}")
        # A grant that cannot be taken back is worse than none: try to
        # leave everyone offline, and retry the list on the next tick.
        try:
            internet.apply(backend, set())
        except (OSError, subprocess.SubprocessError) as again:
            log(f"cannot take kids offline either: {again}")
        return None, 0.0
    if uids != sent[0]:
        log(f"online: {', '.join(pwd.getpwuid(uid).pw_name for uid in sorted(uids)) or 'nobody'}")
    return uids, now


def notify(message):
    """Tell systemd the daemon is alive; its watchdog restarts a stuck one."""
    path = os.environ.get("NOTIFY_SOCKET")
    if not path:
        return
    if path.startswith("@"):
        path = "\0" + path[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        try:
            sock.sendto(message.encode(), path)
        except OSError as error:
            log(f"cannot notify systemd: {error}")


BROKEN = {
    "allowed": False,
    "online": False,
    "opensAt": None,
    "opensIn": None,
    "reason": "broken",
    "remaining": None,
}


def daemon(_args):
    os.makedirs(state.RUN_DIR, exist_ok=True)
    # Usage lives in memory and is only saved from here, so a failed save
    # never loses time already counted.
    usage = state.load_usage()
    last = time.monotonic()
    saved = last
    previous = {}
    sent = (None, 0.0)
    while True:
        now = time.monotonic()
        # Monotonic time stands still during suspend, so sleep adds no play;
        # the cap only keeps one stalled tick from counting as minutes.
        elapsed = min(now - last, TICK * 4)
        last = now
        usage = state.roll_usage(usage)
        config = state.load_config()
        try:
            policy = state.load_policy()
        except state.BrokenPolicy as error:
            log(f"broken rules: {error}")
            policy = None

        statuses = {}
        active = []
        online = set()
        for kid in config["kids"]:
            user = kid["user"]
            # One broken profile must not stop enforcement for the others.
            try:
                login = user_state(user)
                if login == "active":
                    active.append(user)
                    seconds = usage["seconds"]
                    seconds[user] = seconds.get(user, 0) + elapsed
                try:
                    if policy is None:
                        raise state.BrokenPolicy("the rules cannot be read")
                    status = state.kid_status(kid, policy, usage)
                    status["online"] = state.online(kid, policy, status["allowed"])
                except Exception as error:  # noqa: BLE001 - whatever breaks, fail closed
                    # Rules that cannot be read allow nothing, as in PAM.
                    log(f"{user}: broken rules: {error!r}")
                    status = {**BROKEN, "used": int(usage["seconds"].get(user, 0))}
                statuses[user] = status
                if status["online"]:
                    online.add(pwd.getpwnam(user).pw_uid)

                remaining = status["remaining"]
                before = previous.get(user)
                if login in ("active", "online") and remaining is not None and before:
                    for mark in WARN_AT_SECONDS:
                        if before > mark >= remaining > 0:
                            warn(user, remaining, config.get("warningSound"))
                previous[user] = remaining

                if not status["allowed"] and login in ("active", "online"):
                    end_session(user, f"time is up ({status['reason']})")
            except Exception as error:  # noqa: BLE001 - keep enforcing
                log(f"{user}: {error!r}")

        # Synced writes are slow on old disks; skip them while nobody plays.
        if not active:
            saved = now
        else:
            try:
                state.write_json(state.USAGE, usage)
                saved = now
            except OSError as error:
                log(f"cannot save usage: {error}")
            # PAM reads the saved usage at login, so if it cannot be kept
            # up to date, screen time would quietly stop working: fail
            # closed and end the kids' sessions instead.
            if now - saved > FAILSAFE_SECONDS:
                for user in active:
                    end_session(user, "screen time cannot be saved")
        sent = send_online(config, online, sent, now)
        try:
            state.write_json(state.STATUS, statuses)
        except OSError as error:
            log(f"cannot save status: {error}")
        notify("READY=1\nWATCHDOG=1")
        time.sleep(TICK)


def check(args):
    user = args.user or os.environ.get("PAM_USER")
    kid = state.kids_by_user().get(user)
    if kid is None:
        return 0
    try:
        status = state.kid_status(kid, state.load_policy(), state.load_usage())
    except Exception as error:  # noqa: BLE001 - whatever breaks, fail closed
        print(f"{user}: broken rules: {error!r}", file=sys.stderr)
        return 1
    if status["allowed"]:
        return 0
    print(f"{user}: {status['reason']}", file=sys.stderr)
    return 1


def grant(args):
    if args.user not in state.kids_by_user():
        sys.exit(f"unknown kid: {args.user}")
    state.grant_bonus(args.user, args.minutes)
    return 0


def show(_args):
    for user, status in state.read_status().items():
        remaining = status["remaining"]
        left = "unlimited" if remaining is None else state.format_duration(remaining)
        verdict = "ok" if status["allowed"] else status["reason"]
        line = f"{user}: {verdict}, {left} left, {status['used'] // 60} min played"
        if status.get("opensAt"):
            line += f", opens in {status['opensIn']} days at {status['opensAt']}"
        if "online" in status:
            line += ", online" if status["online"] else ", offline"
        print(line)
    return 0


def open_internet(args):
    if args.user not in state.kids_by_user():
        sys.exit(f"unknown kid: {args.user}")
    until = None
    if args.minutes:
        until = datetime.datetime.now() + datetime.timedelta(minutes=args.minutes)
    state.open_internet(args.user, until)
    return 0


def offline(_args):
    """Everyone offline, for when the daemon stops."""
    backend = state.load_config().get("internet", {}).get("backend")
    if backend is not None:
        internet.apply(backend, set())
    return 0


def stop(args):
    if args.user not in state.kids_by_user():
        sys.exit(f"unknown kid: {args.user}")
    state.stop_today(args.user, not args.undo)
    return 0


def main():
    parser = argparse.ArgumentParser(prog="zoomies-time")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("daemon").set_defaults(run=daemon)
    command = commands.add_parser("check", help="exit 1 if the kid may not play now")
    command.add_argument("user", nargs="?")
    command.set_defaults(run=check)
    command = commands.add_parser("grant", help="give extra minutes for today")
    command.add_argument("user")
    command.add_argument("minutes", type=int)
    command.set_defaults(run=grant)
    command = commands.add_parser("internet", help="let a kid online for a while, 0 closes it")
    command.add_argument("user")
    command.add_argument("minutes", type=int)
    command.set_defaults(run=open_internet)
    commands.add_parser("offline", help=argparse.SUPPRESS).set_defaults(run=offline)
    command = commands.add_parser("stop", help="no more play today")
    command.add_argument("user")
    command.add_argument("--undo", action="store_true", help="let the kid play again today")
    command.set_defaults(run=stop)
    commands.add_parser("status").set_defaults(run=show)
    args = parser.parse_args()
    sys.exit(args.run(args))
