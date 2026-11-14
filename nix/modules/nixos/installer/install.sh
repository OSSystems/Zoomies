# TOPLEVEL, DISKO_SCRIPT and CLOSURE_INFO come from the Nix wrapper.
set -E

gib=$((1024 * 1024 * 1024))
log=/tmp/zoomies-install.log

exec > >(tee -a "$log") 2>&1

say() {
  echo "$*"
  echo "zoomies-installer: $*" >/dev/kmsg 2>/dev/null || true
}

fail() {
  trap - ERR
  # The journal and the serial console only get the kernel log.
  tail -n 40 "$log" | while IFS= read -r line; do
    echo "zoomies-installer: $line" >/dev/kmsg 2>/dev/null || true
  done
  say "ERROR: $*"
  echo "Run 'sudo zoomies-install' to try again."
  exit 1
}

trap 'fail "the installation stopped unexpectedly (line $LINENO)"' ERR

udevadm settle

if [ -d /sys/firmware/efi ]; then
  firmware=UEFI
else
  firmware=BIOS
fi

# ext4 rounds every store file up to a whole block; the rest is the ESP and
# room for later generations.
required=$(($(cat "$CLOSURE_INFO/total-nar-size") * 5 / 4 + 3 * gib))

# A memory card in a built-in reader looks like an internal SSD, but it
# usually holds photos, not an operating system.
internal_disks() {
  lsblk -Jbdpo PATH,SIZE,TYPE,RM,RO,ROTA,TRAN,MODEL |
    jq -r '
      .blockdevices[]
      | select(.type == "disk" and (.rm | not) and (.ro | not) and .tran != "usb")
      | [.path, .size, .tran // "", (if .rota then "HDD" else "SSD" end), (.model // "" | gsub("\\s+$"; ""))]
      | @tsv' |
    while IFS=$'\t' read -r path size tran kind model; do
      devtype=/sys/block/${path#/dev/}/device/type
      if [ ! -r "$devtype" ] || [ "$(<"$devtype")" != SD ]; then
        printf '%s\t%s\t%s\t%s\t%s\n' "$path" "$size" "$tran" "$kind" "$model"
      fi
    done
}

# NVMe first, then other SSDs, then hard disks; larger first.
mapfile -t candidates < <(
  internal_disks |
    while IFS=$'\t' read -r path size tran kind model; do
      if [ "$size" -lt "$required" ]; then
        continue
      fi
      rank=0
      if [ "$tran" = nvme ]; then
        rank=2
      elif [ "$kind" = SSD ]; then
        rank=1
      fi
      printf '%s\t%s\t%s\t%s\t%s\n' "$rank" "$size" "$path" "$kind" "$model"
    done |
    sort -t $'\t' -k1,1nr -k2,2nr |
    cut -f2-
)

clear 2>/dev/null || true
say "Zoomies installer (this computer started in $firmware mode)"
echo

if [ "${#candidates[@]}" -eq 0 ]; then
  echo "Disks found:"
  lsblk -dpo PATH,SIZE,TYPE,TRAN,MODEL
  echo
  fail "no internal disk of at least $(numfmt --to=iec "$required") was found"
fi

target_line=${candidates[0]}
if [ "${#candidates[@]}" -gt 1 ]; then
  echo "Zoomies can be installed on one of these disks:"
  note="  (recommended)"
  for i in "${!candidates[@]}"; do
    IFS=$'\t' read -r size path kind model <<<"${candidates[$i]}"
    printf '  %d) %-14s %8s  %s  %s%s\n' "$((i + 1))" "$path" "$(numfmt --to=iec "$size")" \
      "$kind" "$model" "$note"
    note=""
  done
  echo
  while :; do
    read -rp "Choose a disk [1]: " choice
    choice=${choice:-1}
    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#candidates[@]}" ]; then
      target_line=${candidates[$((choice - 1))]}
      break
    fi
    echo "Type a number from 1 to ${#candidates[@]}."
  done
fi
IFS=$'\t' read -r size target kind model <<<"$target_line"

# The system mounts its partitions by label, so an older Zoomies install on
# another internal disk could be mounted instead of the new one.
stale=()
while IFS=$'\t' read -r disk _; do
  if [ "$disk" != "$target" ] && lsblk -nlo PARTLABEL "$disk" | grep -q '^disk-zoomies-'; then
    stale+=("$disk")
  fi
done < <(internal_disks)

echo
echo "Zoomies will be installed on $target ($(numfmt --to=iec "$size") $kind $model)."
echo
echo "EVERYTHING ON THIS DISK WILL BE ERASED:"
lsblk -po NAME,SIZE,FSTYPE,LABEL "$target" | sed 's/^/    /'
for disk in "${stale[@]}"; do
  echo
  echo "The old Zoomies install on this disk will be erased as well:"
  lsblk -po NAME,SIZE,FSTYPE,LABEL "$disk" | sed 's/^/    /'
done
echo
echo "zoomies-installer: waiting for confirmation to erase $target" >/dev/kmsg 2>/dev/null || true
while :; do
  read -rp "Type ERASE to install, or NO to power off: " answer
  case "$answer" in
    ERASE) break ;;
    NO | no)
      say "Nothing was changed. Powering off."
      sleep 3
      systemctl poweroff
      exit 0
      ;;
  esac
done

# Asked here, before the long copy, so nobody has to wait around for it.
# The image is shared publicly, so the PIN cannot be part of it.
pin=""
if [ -n "$PARENT_USER" ]; then
  echo
  echo "Choose a PIN for grown-ups: 4 to 12 digits. It opens the settings"
  echo "and lets you leave the kids' screens. Press Enter to choose it on"
  echo "the first start instead."
  echo "zoomies-installer: waiting for the grown-ups PIN" >/dev/kmsg 2>/dev/null || true
  while :; do
    read -rsp "PIN: " pin
    echo
    if [ -z "$pin" ]; then
      break
    fi
    if [[ ! "$pin" =~ ^[0-9]{4,12}$ ]]; then
      echo "Use 4 to 12 digits."
      continue
    fi
    read -rsp "Same PIN again: " again
    echo
    if [ "$pin" = "$again" ]; then
      break
    fi
    echo "The two PINs are different. Try again."
  done
fi

for disk in "${stale[@]}"; do
  say "Erasing the old Zoomies install on $disk"
  wipefs -a "$disk"
done

say "Partitioning $target"
ln -sfn "$target" /dev/disk/zoomies-boot
"$DISKO_SCRIPT" --yes-wipe-all-disks

# Old BIOSes only boot a GPT disk whose protective MBR is marked active. The
# UEFI specification forbids that mark and some UEFI firmware rejects the
# disk because of it, so set it only on machines started in BIOS mode.
if [ "$firmware" = BIOS ]; then
  parted --script "$target" disk_set pmbr_boot on
fi

say "Copying Zoomies to $target, this takes a while"
nixos-install --root /mnt --system "$TOPLEVEL" --no-root-passwd --no-channel-copy

if [ -n "$pin" ]; then
  say "Setting the grown-ups PIN"
  printf '%s:%s\n' "$PARENT_USER" "$pin" | nixos-enter --root /mnt -c chpasswd
fi

umount -R /mnt
sync
say "Installation complete."

echo
read -rp "Remove the USB stick or disc, then press Enter to power off. " _ || true
systemctl poweroff
