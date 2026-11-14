# Some games ship no desktop entry, or only a tiny icon, which would leave
# them missing or blurry on the home screen. Known ones get patched here;
# any other package passes through untouched.
{ lib, pkgs }:

let
  entry =
    pkg: name: desktopName: icon:
    pkgs.makeDesktopItem {
      inherit desktopName name;
      categories = [ "Game" ];
      exec = "${pkg}/bin/${name}";
      icon = "${pkg}/${icon}";
    };

  withEntries =
    pkg: entries:
    pkgs.symlinkJoin {
      inherit (pkg) meta name;
      paths = [ pkg ] ++ entries;
    };

  withIcon =
    pkg: desktop: icon:
    pkgs.symlinkJoin {
      inherit (pkg) meta name;
      paths = [ pkg ];
      postBuild = ''
        rm $out/share/applications/${desktop}
        sed 's|^Icon=.*|Icon=${pkg}/${icon}|' ${pkg}/share/applications/${desktop} \
          > $out/share/applications/${desktop}
      '';
    };

  fixups = {
    neverball =
      pkg:
      withEntries pkg [
        (entry pkg "neverball" "Neverball" "share/neverball/data/icon/neverball.png")
        (entry pkg "neverputt" "Neverputt" "share/neverball/data/icon/neverputt.png")
      ];
    tuxpaint = pkg: withIcon pkg "tuxpaint.desktop" "share/tuxpaint/images/tuxpaint-icon.svg";
  };
in
pkg: (fixups.${lib.getName pkg} or lib.id) pkg
