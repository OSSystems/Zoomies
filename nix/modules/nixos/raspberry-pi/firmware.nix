# The whole redistributable set is about 2 GiB of PC Wi-Fi, GPU, sound and
# TV tuner firmware the Pi never loads. The Pi gets its own Wi-Fi and
# Bluetooth firmware, plus the USB Wi-Fi dongles families plug in when the
# built-in Wi-Fi is weak or missing.
{
  lib,
  pkgs,
  ...
}:

let
  # What the Pi kernel's USB Wi-Fi drivers ask for, read from their
  # modinfo: mt7601u, mt76x0u, mt76x2u, mt7921u, mt7925u, rt2800usb,
  # ath9k_htc, rtl8xxxu and rtl8192cu/du, and the rtw88 and rtw89 USB
  # chips. rtw89 tries several firmware formats, so it takes every one.
  usbWifiFiles = [
    "ath9k_htc"
    "mediatek/WIFI_MT7961_patch_mcu_1_2_hdr.bin"
    "mediatek/WIFI_RAM_CODE_MT7961_1.bin"
    "mediatek/mt7601u.bin"
    "mediatek/mt7610e.bin"
    "mediatek/mt7610u.bin"
    "mediatek/mt7662.bin"
    "mediatek/mt7662_rom_patch.bin"
    "mediatek/mt7925/WIFI_MT7925_PATCH_MCU_1_1_hdr.bin"
    "mediatek/mt7925/WIFI_RAM_CODE_MT7925_1_1.bin"
    "mt7601u.bin"
    "mt7662.bin"
    "mt7662_rom_patch.bin"
    "rt2870.bin"
    "rtlwifi"
    "rtw88"
    "rtw89/rtw8851b_fw*.bin"
    "rtw89/rtw8852a_fw*.bin"
    "rtw89/rtw8852b_fw*.bin"
  ];

  usbWifiFirmware =
    pkgs.runCommand "usb-wifi-firmware-${pkgs.linux-firmware.version}"
      {
        inherit (pkgs.linux-firmware) meta;
      }
      ''
        from=${pkgs.linux-firmware}/lib/firmware
        to=$out/lib/firmware
        mkdir -p $to
        cd $from
        shopt -s nullglob
        for pattern in ${lib.escapeShellArgs usbWifiFiles}; do
          # The package may ship a blob already compressed; the kernel
          # looks for either name.
          matches=()
          for match in $pattern $pattern.zst $pattern.xz; do
            if [ -e "$match" ] || [ -L "$match" ]; then matches+=("$match"); fi
          done
          if [ ''${#matches[@]} -eq 0 ]; then
            echo "linux-firmware has no $pattern" >&2
            exit 1
          fi
          cp -dR --parents --no-preserve=mode "''${matches[@]}" $to
        done
        # Deduplicated blobs are links to files that may not have come along.
        find -L $to -type l | while read -r link; do
          cp --remove-destination --no-preserve=mode "$from/''${link#$to/}" "$link"
        done
        # The firmware's licences travel with it in the image.
        cp -r --no-preserve=mode ${pkgs.linux-firmware.src}/{LICENSE,LICENSES,WHENCE} $to
      '';
in
{
  hardware = {
    enableRedistributableFirmware = lib.mkForce false;
    firmware = [
      pkgs.raspberrypiWirelessFirmware
      usbWifiFirmware
    ];
    wirelessRegulatoryDatabase = true;
  };
}
