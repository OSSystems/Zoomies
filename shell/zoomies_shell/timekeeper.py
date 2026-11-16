"""Screen time enforcement.

`zoomies-time daemon` counts the minutes each kid spends in the foreground
session and ends the session once the budget or the allowed hours run out.
`zoomies-time check` runs from PAM so a kid whose time is up cannot log in
again, whatever the greeter shows.
"""

import argparse
import os
import pwd
import subprocess
import sys
import time

from . import state
from .i18n import _, ngettext

TICK = 5
# Warn at these remaining-seconds marks.
WARNINGS = (300, 60)
# Seconds without saving usage before kid sessions are ended.
FAILSAFE = 30


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


def daemon(_args):
    os.makedirs(state.RUN_DIR, exist_ok=True)
    # Usage lives in memory and is only saved from here, so a failed save
    # never loses time already counted.
    usage = state.load_usage()
    last = time.monotonic()
    saved = last
    previous = {}
    while True:
        now = time.monotonic()
        # Monotonic time stands still during suspend, so sleep adds no play;
        # the cap only keeps one stalled tick from counting as minutes.
        elapsed = min(now - last, TICK * 4)
        last = now
        usage = state.roll_usage(usage)
        config = state.load_config()
        policy = state.load_policy()

        statuses = {}
        active = []
        for kid in config["kids"]:
            user = kid["user"]
            # One broken profile must not stop enforcement for the others.
            try:
                login = user_state(user)
                if login == "active":
                    active.append(user)
                    seconds = usage["seconds"]
                    seconds[user] = seconds.get(user, 0) + elapsed
                status = state.kid_status(kid, policy, usage)
                statuses[user] = status

                remaining = status["remaining"]
                before = previous.get(user)
                if login in ("active", "online") and remaining is not None and before:
                    for mark in WARNINGS:
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
            if now - saved > FAILSAFE:
                for user in active:
                    end_session(user, "screen time cannot be saved")
        try:
            state.write_json(state.STATUS, statuses)
        except OSError as error:
            log(f"cannot save status: {error}")
        time.sleep(TICK)


def check(args):
    user = args.user or os.environ.get("PAM_USER")
    kid = state.kids_by_user().get(user)
    if kid is None:
        return 0
    status = state.kid_status(kid, state.load_policy(), state.load_usage())
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
        print(f"{user}: {verdict}, {left} left, {status['used'] // 60} min played")
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
    commands.add_parser("status").set_defaults(run=show)
    args = parser.parse_args()
    sys.exit(args.run(args))
