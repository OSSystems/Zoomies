# Finishes an install once Calamares has partitioned and mounted the target:
# labels the filesystems the system mounts, copies the prebuilt system and
# installs GRUB. TOPLEVEL and CLOSURE_INFO come from the Nix wrapper.
set -eu

root='' root_device='' esp_device='' firmware=bios time_zone=''
while [ $# -gt 0 ]; do
  case $1 in
    --root) root=$2 ;;
    --root-device) root_device=$2 ;;
    --esp-device) esp_device=$2 ;;
    --firmware) firmware=$2 ;;
    --time-zone) time_zone=$2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift 2
done

log=/tmp/zoomies-install.log
exec > >(tee -a "$log") 2>&1

say() {
  echo "$*"
  echo "zoomies-installer: $*" >/dev/kmsg 2>/dev/null || true
}

trap 'say "ERROR: the installation stopped (line $LINENO)"' ERR

[ -n "$root" ] && [ -n "$root_device" ] || { say "ERROR: no root filesystem"; exit 1; }

echo "progress 0.02"
# The system mounts / by label, so an older Zoomies on another disk would
# make it ambiguous.
for other in $(blkid -t LABEL=zoomies -o device); do
  if [ "$other" != "$root_device" ]; then
    say "Renaming the old Zoomies filesystem on $other"
    e2label "$other" zoomies-old
  fi
done
e2label "$root_device" zoomies

if [ -n "$esp_device" ]; then
  mkdir -p "$root/var/lib/zoomies"
  blkid -s PARTUUID -o value "$esp_device" >"$root/var/lib/zoomies/esp-partuuid"
fi

disk=/dev/$(lsblk -no PKNAME "$root_device")
# GRUB installs to the disk this link points at.
ln -sfn "$disk" /dev/disk/zoomies-boot

# Old BIOSes only boot a GPT disk whose protective MBR is marked active. The
# UEFI specification forbids that mark and some UEFI firmware rejects the
# disk because of it, so set it only on machines started in BIOS mode.
if [ "$firmware" = bios ] && [ "$(blkid -s PTTYPE -o value "$disk")" = gpt ]; then
  parted --script "$disk" disk_set pmbr_boot on
fi

if [ -n "$time_zone" ] && [ -e "/etc/zoneinfo/$time_zone" ]; then
  mkdir -p "$root/etc"
  ln -sfn "/etc/zoneinfo/$time_zone" "$root/etc/localtime"
fi

echo "progress 0.05"
say "Copying Zoomies to $disk, this takes a while"
# nixos-install reports nothing useful through a pipe, so the progress bar
# follows the space used on the new disk against the size of the system.
total=$(cat "$CLOSURE_INFO/total-nar-size")
start=$(df -B1 --output=used "$root" | tail -1)
(
  while sleep 2; do
    used=$(($(df -B1 --output=used "$root" | tail -1) - start))
    awk -v u="$used" -v t="$total" 'BEGIN { p = u / t; if (p > 1) p = 1; printf "progress %.3f\n", 0.05 + 0.9 * p }'
  done
) &
watcher=$!
# Calamares reads until the output closes, which the watcher would hold open.
trap 'kill "$watcher" 2>/dev/null || true' EXIT
nixos-install --root "$root" --system "$TOPLEVEL" --no-root-passwd --no-channel-copy
echo "progress 1"
say "Installation complete."
