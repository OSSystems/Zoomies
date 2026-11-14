"""Wipe a kid's home at boot, keeping only the listed game data.

Paths in the keep list are relative to the home directory and may be nested
(".config/supertuxkart"); their parents are kept as directories, everything
else is removed. Symlinks are removed, never followed.
"""

import argparse
import os
import shutil
import sys


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


def main():
    parser = argparse.ArgumentParser(prog="zoomies-reset-home")
    parser.add_argument("home")
    parser.add_argument("keep", nargs="*")
    args = parser.parse_args()
    if not os.path.isdir(args.home):
        return
    keep = {os.path.normpath(k).lstrip("/") for k in args.keep}
    if any(k.startswith("..") for k in keep):
        sys.exit("keep paths must stay inside the home directory")
    prune(args.home, keep)
