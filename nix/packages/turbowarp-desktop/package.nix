{
  electron,
  fetchurl,
  lib,
  makeWrapper,
  stdenvNoCC,
}:

let
  version = "1.17.1";
  # The app itself is JavaScript and runs on any Electron of the major it
  # was made for; only the bundled Electron differs between the archives.
  # Each system still takes its own, so the app reports the right build.
  sources = {
    aarch64-linux = {
      arch = "arm64";
      hash = "sha256-GUMC8PfpanAoxIzecNZSDrq4YFD6a5/y14cgLjd/aZA=";
    };
    x86_64-linux = {
      arch = "x64";
      hash = "sha256-9pGrw1ul8d4U2JRYK0h91/TWPcKG2LOasOm6vCj0Yu0=";
    };
  };
  source =
    sources.${stdenvNoCC.hostPlatform.system}
      or (throw "turbowarp-desktop: unsupported system ${stdenvNoCC.hostPlatform.system}");
in
stdenvNoCC.mkDerivation {
  inherit version;
  installPhase = ''
    runHook preInstall
    # The app finds its window icon next to app.asar.
    mkdir -p $out/share/turbowarp-desktop
    cp resources/app.asar resources/icon.png $out/share/turbowarp-desktop
    install -Dm644 resources/icon.svg \
      $out/share/icons/hicolor/scalable/apps/org.turbowarp.TurboWarp.svg
    install -Dm644 linux-files/org.turbowarp.TurboWarp.mime.xml \
      $out/share/mime/packages/org.turbowarp.TurboWarp.xml
    install -Dm644 linux-files/org.turbowarp.TurboWarp.metainfo.xml \
      $out/share/metainfo/org.turbowarp.TurboWarp.metainfo.xml
    # Scratch is for making games and stories, so it sits with the creative
    # apps rather than with programming tools.
    mkdir -p $out/share/applications
    sed -e '/^#/d' \
      -e "s|^Exec=[^ ]*|Exec=$out/bin/turbowarp-desktop|" \
      -e 's|^Categories=.*|Categories=Development;Graphics;|' \
      linux-files/org.turbowarp.TurboWarp.desktop \
      > $out/share/applications/org.turbowarp.TurboWarp.desktop
    # Updates come with the system, not from the app's own checker.
    makeWrapper ${lib.getExe electron} $out/bin/turbowarp-desktop \
      --add-flags $out/share/turbowarp-desktop/app.asar \
      --set TW_DISABLE_UPDATE_CHECKER 1 \
      --set TW_DIST_ID nix
    runHook postInstall
  '';
  meta = {
    description = "Scratch mod with a compiler, dark mode and addons, as a desktop app";
    homepage = "https://desktop.turbowarp.org/";
    license = lib.licenses.gpl3Only;
    mainProgram = "turbowarp-desktop";
    platforms = builtins.attrNames sources;
    sourceProvenance = [ lib.sourceTypes.binaryBytecode ];
  };
  nativeBuildInputs = [ makeWrapper ];
  pname = "turbowarp-desktop";
  src = fetchurl {
    inherit (source) hash;
    url = "https://github.com/TurboWarp/desktop/releases/download/v${version}/TurboWarp-linux-${source.arch}-${version}.tar.gz";
  };
}
