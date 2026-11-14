"""Wipe a kid's home at boot, keeping only the listed game data.

Paths in the keep list are relative to the home directory and may be nested
(".config/supertuxkart"); their parents are kept as directories, everything
else is removed. Symlinks are removed, never followed.
"""

import argparse
import os
import pwd
import shutil
import sys

from . import state


def remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)


def prune(directory, keep, prefix=""):
    for entry in os.listdir(directory):
        rel = prefix + entry
        path = os.path.join(directory, entry)
        if rel in keep:
            continue
        if any(k.startswith(rel + "/") for k in keep) and (
            os.path.isdir(path) and not os.path.islink(path)
        ):
            prune(path, keep, rel + "/")
            continue
        remove(path)


def reset(home, keep):
    if not os.path.isdir(home):
        return
    keep = {os.path.normpath(k).lstrip("/") for k in keep}
    if any(k.startswith("..") for k in keep):
        sys.exit("keep paths must stay inside the home directory")
    prune(home, keep)


def main():
    parser = argparse.ArgumentParser(prog="zoomies-reset-home")
    parser.add_argument("--all", action="store_true", help="every little kid, as configured")
    parser.add_argument("home", nargs="?")
    parser.add_argument("keep", nargs="*")
    args = parser.parse_args()
    if not args.all:
        if args.home is None:
            parser.error("give a home directory or --all")
        reset(args.home, args.keep)
        return
    config = state.load_config()
    failed = False
    # Older kids keep their homes: that is where their schoolwork lives.
    for kid in config["kids"]:
        if kid.get("kind") != "little":
            continue
        # One stuck home must not leave the other kids' homes unreset.
        try:
            home = pwd.getpwnam(kid["user"]).pw_dir
            print(f"resetting {home}", flush=True)
            reset(home, config.get("resetKeep", []))
        except (KeyError, OSError) as error:
            print(f"cannot reset {kid['user']}: {error}", file=sys.stderr, flush=True)
            failed = True
    if failed:
        sys.exit(1)
