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
    # Neverball and Neverputt size their drawing once, right after making
    # the window, and ignore resizes, so they draw in a corner of the
    # screen-sized window they get. In their own fullscreen mode they take
    # the size of the screen, but their high-DPI mode asks the window, which
    # is still at its first size then. Both are forced, whatever an earlier
    # session saved, since their settings survive the home reset.
    neverball =
      pkg:
      let
        fullscreen = pkg.overrideAttrs (old: {
          postPatch = (old.postPatch or "") + ''
            substituteInPlace share/video.c \
              --replace-fail 'video_mode(config_get_d(CONFIG_FULLSCREEN),' 'video_mode(1,' \
              --replace-fail 'config_get_d(CONFIG_HIGHDPI)     ? 1 : 0' '0'
          '';
        });
      in
      withEntries fullscreen [
        (entry fullscreen "neverball" "Neverball" "share/neverball/data/icon/neverball.png")
        (entry fullscreen "neverputt" "Neverputt" "share/neverball/data/icon/neverputt.png")
      ];
    tuxpaint = pkg: withIcon pkg "tuxpaint.desktop" "share/tuxpaint/images/tuxpaint-icon.svg";
  };
in
pkg: (fixups.${lib.getName pkg} or lib.id) pkg
