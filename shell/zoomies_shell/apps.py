"""The apps a kid may start, read from the desktop entries their packages
ship. Free of any GTK version, so GTK 3 and 4 screens share it."""

import os

from gi.repository import Gio


def entries(sources):
    """The visible desktop entries, by name, of packages or of single
    desktop entry files: a package may ship helpers kids do not need."""
    found = []
    seen = set()
    for source in sources:
        # makeDesktopItem packages are named *.desktop too.
        if os.path.isfile(source):
            files = [source]
        else:
            applications = os.path.join(source, "share/applications")
            if not os.path.isdir(applications):
                continue
            files = [os.path.join(applications, n) for n in sorted(os.listdir(applications))]
        for path in files:
            if not path.endswith(".desktop"):
                continue
            try:
                info = Gio.DesktopAppInfo.new_from_filename(path)
            except TypeError:
                # GIO returns nothing for an entry it cannot start, such as
                # one whose TryExec is missing.
                continue
            if info is None or not info.should_show() or info.get_name() in seen:
                continue
            seen.add(info.get_name())
            found.append(info)
    return sorted(found, key=lambda info: info.get_name().lower())


def icon_dirs(sources):
    """Where the packages keep icons the system theme does not know."""
    for source in sources:
        package = source.split("/share/applications/")[0]
        for sub in ("share/icons", "share/pixmaps"):
            path = os.path.join(package, sub)
            if os.path.isdir(path):
                yield path
