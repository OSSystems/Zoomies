"""The apps a kid may start, read from the desktop entries their packages
ship. Free of any GTK version, so GTK 3 and 4 screens share it."""

import os

from gi.repository import Gio


def entries(packages):
    """The visible desktop entries the packages ship, by name."""
    found = []
    seen = set()
    for package in packages:
        applications = os.path.join(package, "share/applications")
        if not os.path.isdir(applications):
            continue
        for name in sorted(os.listdir(applications)):
            if not name.endswith(".desktop"):
                continue
            info = Gio.DesktopAppInfo.new_from_filename(os.path.join(applications, name))
            if info is None or not info.should_show() or info.get_name() in seen:
                continue
            seen.add(info.get_name())
            found.append(info)
    return sorted(found, key=lambda info: info.get_name().lower())


def icon_dirs(packages):
    """Where the packages keep icons the system theme does not know."""
    for package in packages:
        for sub in ("share/icons", "share/pixmaps"):
            path = os.path.join(package, sub)
            if os.path.isdir(path):
                yield path
