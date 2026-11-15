{
  librsvg,
  python3,
  stdenvNoCC,
}:

stdenvNoCC.mkDerivation {
  buildPhase = ''
    runHook preBuild
    mkdir out
    python3 render.py ${../../../assets/mascot/zip.svg} ${../../../assets/mascot/zip-flying.svg} zoomies.script out
    runHook postBuild
  '';
  installPhase = ''
    runHook preInstall
    theme=$out/share/plymouth/themes/zoomies
    mkdir -p $theme
    cp out/* $theme
    cat > $theme/zoomies.plymouth <<EOT
    [Plymouth Theme]
    Name=Zoomies
    Description=Zip dashes through the sky while the system boots
    ModuleName=script

    [script]
    ImageDir=$theme
    ScriptFile=$theme/zoomies.script
    EOT
    runHook postInstall
  '';
  meta.description = "Zoomies boot splash: Zip dashing through the sky";
  nativeBuildInputs = [
    librsvg
    python3
  ];
  pname = "zoomies-splash";
  src = ../../../splash;
  version = "0.1.0";
}
