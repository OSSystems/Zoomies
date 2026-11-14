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
    for art in ${../../../assets/mascot}/*.svg; do
      sed 's|<rect [^>]*fill="#e9faf4"/>||' "$art" > $out/share/zoomies/$(basename "$art")
    done
  '';
  pyproject = true;
  src = ../../../shell;
  version = "0.1.0";
}
