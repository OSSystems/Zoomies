# The template must list every string the screens show, and each
# translation must compile, so a new string never ships untranslatable.
{ lib, pkgs, ... }:

let
  # The notes in po/README.md change nothing this checks.
  src = lib.fileset.toSource {
    fileset = lib.fileset.unions [
      (lib.fileset.fileFilter (file: file.hasExt "py") ../../shell/zoomies_shell)
      (lib.fileset.fileFilter (file: file.hasExt "po" || file.hasExt "pot") ../../shell/po)
    ];
    root = ../../shell;
  };
in
pkgs.runCommand "zoomies-translations"
  {
    nativeBuildInputs = [ pkgs.gettext ];
  }
  ''
    cd ${src}
    xgettext --language=Python --keyword=_ --keyword=N_ --keyword=ngettext:1,2 \
      --from-code=UTF-8 --add-comments=Translators: --no-location \
      -o $TMPDIR/zoomies.pot zoomies_shell/*.py
    if ! diff <(grep -v POT-Creation-Date $TMPDIR/zoomies.pot) <(grep -v POT-Creation-Date po/zoomies.pot); then
      echo "po/zoomies.pot is out of date; regenerate it as described in shell/po/README.md" >&2
      exit 1
    fi
    for po in po/*.po; do
      msgfmt --check -o /dev/null "$po"
      msgcmp "$po" po/zoomies.pot
    done
    touch $out
  ''
