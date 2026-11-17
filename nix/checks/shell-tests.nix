# The screen time and internet rules are plain logic, tested without a VM.
{ lib, pkgs, ... }:

let
  src = lib.fileset.toSource {
    fileset = lib.fileset.unions [
      ../../shell/tests
      (lib.fileset.fileFilter (file: file.hasExt "py") ../../shell/zoomies_shell)
    ];
    root = ../../shell;
  };
in
pkgs.runCommand "zoomies-shell-tests" { nativeBuildInputs = [ pkgs.python3 ]; } ''
  cd ${src}
  python3 -m unittest discover -s tests -v
  touch $out
''
