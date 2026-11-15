# Calamares has partitioned and mounted the target; the shell script does
# the rest, so the installer check can run it without the GUI.
import os
import subprocess

import libcalamares


def pretty_name():
    return "Copying Zoomies"


def run():
    gs = libcalamares.globalstorage
    root = gs.value("rootMountPoint")
    partitions = gs.value("partitions") or []

    def device_for(mount_point):
        for part in partitions:
            if part.get("mountPoint") == mount_point:
                return part.get("device")
        return ""

    zone = ""
    if gs.value("locationRegion") and gs.value("locationZone"):
        zone = f"{gs.value('locationRegion')}/{gs.value('locationZone')}"

    command = [
        os.environ["ZOOMIES_INSTALL_TARGET"],
        "--root", root,
        "--root-device", device_for("/"),
        "--esp-device", device_for("/boot/efi"),
        "--firmware", gs.value("firmwareType") or "bios",
        "--time-zone", zone,
    ]
    libcalamares.utils.debug("Running " + " ".join(command))
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    # Each line starting with "progress " carries a fraction from 0 to 1.
    for line in process.stdout:
        line = line.rstrip()
        if line.startswith("progress "):
            libcalamares.job.setprogress(float(line.split()[1]))
        else:
            libcalamares.utils.debug(line)
    if process.wait() != 0:
        return (
            "Zoomies could not be installed",
            "The log is in /tmp/zoomies-install.log on the installer.",
        )
    return None
