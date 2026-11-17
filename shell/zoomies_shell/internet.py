"""Which kids may reach the internet right now, told to the firewall.

The firewall rules from the NixOS module reject every kid's traffic unless
the kid's uid is in a list; the timekeeper keeps that list in step with the
grown-ups' rules. An empty or lost list leaves every kid offline. With
nftables, each uid also drops out of the list unless renewed; iptables
cannot do that, so the service empties the list whenever the timekeeper
stops, and systemd's watchdog stops one that hangs.
"""

import subprocess

CHAIN = "zoomies-online"
# nftables lets each kid online for this long only, so a stuck or stopped
# timekeeper cannot leave anyone online.
LEASE_SECONDS = 60
TIMEOUT_SECONDS = 10


def _nftables(uids):
    script = "flush set inet zoomies online\n"
    if uids:
        elements = ", ".join(f"{uid} timeout {LEASE_SECONDS}s" for uid in sorted(uids))
        script += f"add element inet zoomies online {{ {elements} }}\n"
    subprocess.run(
        ["nft", "-f", "-"],
        input=script,
        text=True,
        check=True,
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
    )


def _iptables(uids):
    # Declaring the chain empties it, and the whole table is swapped in
    # one go, so no packet ever sees a half-filled chain.
    lines = ["*filter", f":{CHAIN} - [0:0]"]
    lines += [f"-A {CHAIN} -m owner --uid-owner {uid} -j RETURN" for uid in sorted(uids)]
    lines += [f"-A {CHAIN} -j REJECT", "COMMIT", ""]
    for command in ("iptables-restore", "ip6tables-restore"):
        subprocess.run(
            [command, "--noflush", "--wait"],
            input="\n".join(lines),
            text=True,
            check=True,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
        )


BACKENDS = {"iptables": _iptables, "nftables": _nftables}


def apply(backend, uids):
    """Let only these uids online; raises CalledProcessError on failure."""
    BACKENDS[backend](uids)
