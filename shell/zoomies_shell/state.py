"""Configuration, profiles, parental policy and screen time bookkeeping.

The NixOS module writes the static configuration and the kids declared in
it; kids added from the grown-ups panel live in profiles.json, which only
the root admin service writes. Parents change the policy at runtime; only
the timekeeper (root) writes usage and status, so kids can read their
remaining time but never change it.
"""

import datetime
import json
import os
import pwd
import sys
import tempfile

CONFIG = os.environ.get("ZOOMIES_CONFIG", "/etc/zoomies/config.json")
STATE_DIR = os.environ.get("ZOOMIES_STATE_DIR", "/var/lib/zoomies")
RUN_DIR = os.environ.get("ZOOMIES_RUN_DIR", "/run/zoomies")
POLICY = os.path.join(STATE_DIR, "policy.json")
PROFILES = os.path.join(STATE_DIR, "profiles.json")
USAGE = os.path.join(STATE_DIR, "usage.json")
STATUS = os.path.join(RUN_DIR, "status.json")


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data, mode=0o644):
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            # Kids pull power cords; a granted bonus must survive that.
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    dirfd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)


KINDS = ("little", "older")
AVATARS = "🦊 🐼 🦄 🐸 🐱 🐶 🐰 🐯 🦁 🐵 🐨 🐙 🐢 🦖 🐧 🦉".split()
COLORS = ("orange", "green", "purple", "pink", "sky", "yellow", "red", "teal")


def load_profiles():
    return read_json(PROFILES, {"kids": []})


def load_config():
    config = read_json(CONFIG, {"kids": [], "parent": None})
    declared = {kid["user"] for kid in config["kids"]}
    for kid in config["kids"]:
        kid["declared"] = True
        kid.setdefault("kind", "little")
    for profile in load_profiles()["kids"]:
        if profile["user"] in declared:
            continue
        kid = {
            "dailyMinutes": None,
            "declared": False,
            "games": config.get("defaultGames", []),
            "hours": None,
        }
        kid.update(profile)
        config["kids"].append(kid)
    return config


def kids_by_user(config=None):
    config = config or load_config()
    return {kid["user"]: kid for kid in config["kids"]}


def current_kid(config):
    """The kid this session belongs to; anyone else has no place here."""
    user = pwd.getpwuid(os.getuid()).pw_name
    kid = kids_by_user(config).get(user)
    if kid is None:
        sys.exit(f"{user} has no Zoomies profile")
    return kid


def today():
    return datetime.date.today().isoformat()


def load_policy():
    return read_json(POLICY, {"kids": {}, "bonus": {}})


def save_policy(policy):
    # Parents share the state directory through its group, so keep the
    # file group-writable for the next parent edit.
    write_json(POLICY, policy, mode=0o664)


def calm_screen(policy=None):
    """Grown-ups can stop everything that moves on its own: the drifting
    clouds, Zip's loops and the cape on the older kids' desktop."""
    return bool((policy or load_policy()).get("calm", False))


def set_calm_screen(calm):
    policy = load_policy()
    policy["calm"] = bool(calm)
    save_policy(policy)


def grant_bonus(user, minutes):
    policy = load_policy()
    bonus = policy.setdefault("bonus", {})
    # Old days are dropped so the file does not grow forever.
    day = dict(bonus.get(today(), {}))
    day[user] = max(0, day.get(user, 0) + minutes)
    policy["bonus"] = {today(): day}
    save_policy(policy)


def roll_usage(usage):
    """The usage itself, or a fresh count once its day is over."""
    if usage.get("date") != today():
        return {"date": today(), "seconds": {}}
    return usage


def load_usage():
    return roll_usage(read_json(USAGE, {}))


def effective_rules(kid, policy):
    """Merge the build-time defaults with the parent's runtime overrides."""
    override = policy.get("kids", {}).get(kid["user"], {})
    minutes = override.get("dailyMinutes", kid.get("dailyMinutes"))
    hours = override.get("hours", kid.get("hours"))
    bonus = policy.get("bonus", {}).get(today(), {}).get(kid["user"], 0)
    return minutes, hours, bonus


def minutes_of_day(hhmm):
    """"24:00" is the end of the day, so a window can run until midnight."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def format_minutes_of_day(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def kid_status(kid, policy, usage, now=None):
    now = now or datetime.datetime.now()
    minutes, hours, bonus = effective_rules(kid, policy)
    used = usage["seconds"].get(kid["user"], 0)
    status = {
        "allowed": True,
        "reason": None,
        "remaining": None,
        "used": int(used),
        "opensAt": None,
    }
    if minutes is not None:
        remaining = max(0, int((minutes + bonus) * 60 - used))
        status["remaining"] = remaining
        if remaining <= 0:
            status.update(allowed=False, reason="budget")
    if hours and (hours["start"], hours["end"]) == ("00:00", "24:00"):
        hours = None
    if hours:
        current = now.hour * 60 + now.minute
        start = minutes_of_day(hours["start"])
        end = minutes_of_day(hours["end"])
        inside = start <= current < end if start <= end else not end <= current < start
        if not inside:
            status.update(allowed=False, reason="hours", opensAt=hours["start"])
        else:
            close = end if end > current else end + 24 * 60
            until_close = max(0, (close - current) * 60 - now.second)
            # Kids limited only by hours get the same countdown and warnings
            # as kids with a daily budget.
            if status["remaining"] is None:
                status["remaining"] = until_close
            else:
                status["remaining"] = min(status["remaining"], until_close)
    return status


def read_status():
    return read_json(STATUS, {})


LOW_SECONDS = 300


def time_left(status):
    """The time-left text and whether it runs low, or None without a limit."""
    remaining = (status or {}).get("remaining")
    if remaining is None:
        return None
    return f"⏳ {format_duration(remaining)}", remaining <= LOW_SECONDS


def format_duration(seconds):
    minutes = (seconds + 59) // 60
    if minutes >= 60:
        h, m = divmod(minutes, 60)
        return f"{h} h {m:02d} min" if m else f"{h} h"
    return f"{minutes} min"
