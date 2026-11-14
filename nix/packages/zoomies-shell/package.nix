{
  gobject-introspection,
  gtk4,
  libmanette,
  libnotify,
  libxcrypt,
  python3Packages,
  wrapGAppsHook4,
}:

python3Packages.buildPythonApplication {
  build-system = [ python3Packages.setuptools ];
  buildInputs = [
    gtk4
    libmanette
  ];
  dependencies = [ python3Packages.pygobject3 ];
  # The admin service checks the PIN against /etc/shadow with crypt().
  makeWrapperArgs = [
    "--set-default ZOOMIES_LIBCRYPT ${libxcrypt}/lib/libcrypt.so.2"
    "--suffix PATH : ${libnotify}/bin"
  ];
  meta = {
    description = "Kid-friendly kiosk shell for Zoomies";
    mainProgram = "zoomies-launcher";
  };
  nativeBuildInputs = [
    gobject-introspection
    wrapGAppsHook4
  ];
  pname = "zoomies-shell";
  postInstall = ''
    # The README art sits on a card; the shell draws Zip straight on the sky.
    mkdir -p $out/share/zoomies
    sed 's|<rect width="600" height="640" rx="48" fill="#e9faf4"/>||' \
      ${../../../assets/mascot/zip.svg} > $out/share/zoomies/zip.svg
  '';
  pyproject = true;
  src = ../../../shell;
  version = "0.1.0";
}
