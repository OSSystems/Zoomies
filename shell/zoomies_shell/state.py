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

from .i18n import N_

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


class BrokenPolicy(ValueError):
    """The parents' rules exist but cannot be read; nothing is allowed."""


def load_policy():
    # Only a missing file means "no rules yet": a damaged one must not
    # turn into no limits at all.
    try:
        with open(POLICY) as f:
            policy = json.load(f)
    except FileNotFoundError:
        return {"kids": {}, "bonus": {}}
    except (OSError, ValueError) as error:
        raise BrokenPolicy(f"{POLICY}: {error}") from error
    if not isinstance(policy, dict):
        raise BrokenPolicy(f"{POLICY}: not an object")
    return policy


def save_policy(policy):
    # Parents share the state directory through its group, so keep the
    # file group-writable for the next parent edit.
    write_json(POLICY, policy, mode=0o664)


def calm_screen(policy=None):
    """Grown-ups can stop everything that moves on its own: the drifting
    clouds, Zip's loops and the cape on the older kids' desktop."""
    try:
        return bool((policy or load_policy()).get("calm", False))
    except BrokenPolicy:
        return False


def set_calm_screen(calm):
    policy = load_policy()
    policy["calm"] = bool(calm)
    save_policy(policy)


def _set_for_today(policy, key, user, value):
    """Set a kid's entry under a per-day key, or drop it with None; other
    days are dropped so the file does not grow forever."""
    day = dict(policy.get(key, {}).get(today(), {}))
    if value is None:
        day.pop(user, None)
    else:
        day[user] = value
    policy[key] = {today(): day}


def grant_bonus(user, minutes):
    policy = load_policy()
    current = policy.get("bonus", {}).get(today(), {}).get(user, 0)
    _set_for_today(policy, "bonus", user, max(0, current + minutes))
    save_policy(policy)


def stop_today(user, stopped=True):
    """End a kid's play for the rest of today, or undo that."""
    policy = load_policy()
    _set_for_today(policy, "stopped", user, True if stopped else None)
    save_policy(policy)


def stopped_today(user, policy):
    return bool(policy.get("stopped", {}).get(today(), {}).get(user))


def roll_usage(usage):
    """The usage itself, or a fresh count once its day is over."""
    if usage.get("date") != today():
        return {"date": today(), "seconds": {}}
    return usage


def load_usage():
    return roll_usage(read_json(USAGE, {}))


DAY = 24 * 60
WEEKDAYS = 7
STEP = 30


def need(condition, message):
    """Reject rules of the wrong shape; enforcement then allows nothing."""
    if not condition:
        raise ValueError(message)


def is_minutes(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
WEEKDAY_NAMES = (
    N_("Monday"),
    N_("Tuesday"),
    N_("Wednesday"),
    N_("Thursday"),
    N_("Friday"),
    N_("Saturday"),
    N_("Sunday"),
)
# Translators: short weekday names, for the grown-ups' week grid.
WEEKDAY_SHORT = (N_("Mon"), N_("Tue"), N_("Wed"), N_("Thu"), N_("Fri"), N_("Sat"), N_("Sun"))


def minutes_of_day(hhmm):
    """"24:00" is the end of the day, so a window can run until midnight."""
    need(isinstance(hhmm, str), f"not a time of day: {hhmm!r}")
    h, m = hhmm.split(":")
    minutes = int(h) * 60 + int(m)
    if not (0 <= minutes <= DAY and 0 <= int(m) < 60):
        raise ValueError(f"not a time of day: {hhmm!r}")
    return minutes


def format_minutes_of_day(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def merge_blocks(blocks):
    """Sorted blocks of play, with touching or overlapping ones joined."""
    merged = []
    for start, end in sorted(blocks):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def day_from_json(data):
    """A day of the week: None for no play, else its blocks of play, in
    minutes of the day, and its minutes of play (None for no cap)."""
    if data is None:
        return None
    need(isinstance(data, dict), f"not a day: {data!r}")
    blocks = data.get("blocks", [])
    need(isinstance(blocks, list), f"not blocks of play: {blocks!r}")
    for block in blocks:
        need(isinstance(block, list) and len(block) == 2, f"not a block of play: {block!r}")
    minutes = data.get("minutes")
    need(minutes is None or is_minutes(minutes), f"not minutes: {minutes!r}")
    blocks = merge_blocks((minutes_of_day(start), minutes_of_day(end)) for start, end in blocks)
    return {"blocks": blocks, "minutes": minutes}


def day_to_json(day):
    if day is None:
        return None
    return {
        "blocks": [[format_minutes_of_day(s), format_minutes_of_day(e)] for s, e in day["blocks"]],
        "minutes": day["minutes"],
    }


def _every_day(minutes, hours):
    """The same day every day, from a daily budget and allowed hours."""
    if not hours:
        return {"blocks": [(0, DAY)], "minutes": minutes}
    start, end = minutes_of_day(hours["start"]), minutes_of_day(hours["end"])
    # A window like 20:00 to 02:00 runs past midnight into the next day.
    blocks = [(start, end)] if start < end else [(0, end), (start, DAY)]
    return {"blocks": merge_blocks(blocks), "minutes": minutes}


def kid_rules(kid, policy):
    kids = policy.get("kids", {})
    need(isinstance(kids, dict), "kids' rules are not an object")
    rules = kids.get(kid["user"], {})
    need(isinstance(rules, dict), f"{kid['user']}: rules are not an object")
    return rules


def week(kid, policy):
    """Seven days from Monday: the parent's weekly schedule, or else the
    daily budget and hours, from the panel or the configuration."""
    rules = kid_rules(kid, policy)
    schedule = rules.get("schedule")
    if schedule is not None:
        need(isinstance(schedule, dict), f"{kid['user']}: the schedule is not an object")
        days = schedule.get("days")
        need(
            isinstance(days, list) and len(days) == WEEKDAYS,
            f"{kid['user']}: a schedule needs {WEEKDAYS} days",
        )
        return [day_from_json(day) for day in days]
    minutes = rules.get("dailyMinutes", kid.get("dailyMinutes"))
    hours = rules.get("hours", kid.get("hours"))
    need(minutes is None or is_minutes(minutes), f"{kid['user']}: not minutes: {minutes!r}")
    need(hours is None or isinstance(hours, dict), f"{kid['user']}: not hours: {hours!r}")
    return [_every_day(minutes, hours)] * WEEKDAYS


def special_days(kid, policy):
    """Dates that play like another weekday (0 is Monday) or "off"."""
    special = kid_rules(kid, policy).get("special", {})
    need(isinstance(special, dict), f"{kid['user']}: special days are not an object")
    return special


def day_plan(kid, policy, date, days=None):
    """The plan for a date, and the weekday it plays like."""
    days = days if days is not None else week(kid, policy)
    like = special_days(kid, policy).get(date.isoformat(), date.weekday())
    if like == "off":
        return None, date.weekday()
    if isinstance(like, bool) or not isinstance(like, int) or not 0 <= like < WEEKDAYS:
        raise ValueError(f"{kid['user']}: {date} cannot play like {like!r}")
    return days[like], like


def bonus_minutes(kid, policy):
    bonus = policy.get("bonus", {}).get(today(), {}).get(kid["user"], 0)
    need(is_minutes(bonus), f"{kid['user']}: not bonus minutes: {bonus!r}")
    return bonus


def _opens(kid, policy, now, after):
    """When play opens next, from `after` minutes into today: in how many
    days and at what time, or (None, None) when not in the next weeks."""
    days = week(kid, policy)
    for offset in range(4 * WEEKDAYS):
        date = now.date() + datetime.timedelta(days=offset)
        plan, _like = day_plan(kid, policy, date, days)
        if plan is None or plan["minutes"] == 0:
            continue
        for start, end in plan["blocks"]:
            if offset or end > after:
                return offset, format_minutes_of_day(start if offset else max(start, after))
    return None, None


def kid_status(kid, policy, usage, now=None):
    now = now or datetime.datetime.now()
    plan, _like = day_plan(kid, policy, now.date())
    used = usage["seconds"].get(kid["user"], 0)
    status = {
        "allowed": True,
        "reason": None,
        "remaining": None,
        "used": int(used),
        "opensAt": None,
        "opensIn": None,
    }
    current = now.hour * 60 + now.minute

    def closed(reason, after):
        opens_in, opens_at = _opens(kid, policy, now, after)
        status.update(allowed=False, reason=reason, opensAt=opens_at, opensIn=opens_in)
        return status

    # What ends play for today waits for another day, not for later today.
    if plan is None:
        return closed("day", DAY)
    if stopped_today(kid["user"], policy):
        return closed("stopped", DAY)
    if plan["minutes"] is not None:
        remaining = max(0, int((plan["minutes"] + bonus_minutes(kid, policy)) * 60 - used))
        status["remaining"] = remaining
        if remaining <= 0:
            return closed("budget", DAY)
    if plan["blocks"] == [(0, DAY)]:
        return status
    block = next(((s, e) for s, e in plan["blocks"] if s <= current < e), None)
    if block is None:
        return closed("hours", current)
    close = block[1]
    if close == DAY:
        # Play goes on past midnight when the next day starts right away.
        tomorrow, _like = day_plan(kid, policy, now.date() + datetime.timedelta(days=1))
        first = tomorrow["blocks"][0] if tomorrow and tomorrow["blocks"] else None
        if first and first[0] == 0 and tomorrow["minutes"] != 0:
            close += first[1]
    until_close = max(0, (close - current) * 60 - now.second)
    # Kids limited only by hours get the same countdown and warnings as
    # kids with a daily budget.
    if status["remaining"] is None:
        status["remaining"] = until_close
    else:
        status["remaining"] = min(status["remaining"], until_close)
    return status


def clamp_block(start, end):
    """A block of play inside the day, at least STEP long."""
    start = min(max(0, start), DAY - STEP)
    return start, min(DAY, max(end, start + STEP))


def retime(days, index, i, new, targets):
    """Days with block i of day `index` moved to `new`, and on the other
    target days, the block at the same time moved too, or `new` added."""
    old = days[index]["blocks"][i]
    out = list(days)
    for target in targets:
        day = out[target]
        if day is None:
            continue
        blocks = list(day["blocks"])
        if target == index:
            match = i
        else:
            # The same hours, else the one that overlaps them.
            same = [j for j, b in enumerate(blocks) if b == old]
            overlapping = [j for j, (s, e) in enumerate(blocks) if s < old[1] and old[0] < e]
            match = (same or overlapping or [None])[0]
        if match is None:
            blocks.append(new)
        else:
            blocks[match] = new
        out[target] = {**day, "blocks": merge_blocks(blocks)}
    return out


def set_kid_rule(user, key, value):
    """Change one of a kid's rules; the others keep following the
    configuration until a parent changes them too."""
    policy = load_policy()
    policy.setdefault("kids", {}).setdefault(user, {})[key] = value
    save_policy(policy)


def save_week(user, days):
    days = [day_to_json(day) for day in days]
    # What could not be read back would keep the kid out every day.
    for day in days:
        day_from_json(day)
    set_kid_rule(user, "schedule", {"days": days})


def save_special_days(user, special):
    # Days gone by matter no more.
    set_kid_rule(user, "special", {d: like for d, like in special.items() if d >= today()})


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
