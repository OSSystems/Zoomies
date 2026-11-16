# Translations

The screens' text is marked with `_()` (or `ngettext()` for plurals) in
`zoomies_shell/`. After changing it, regenerate the template and merge it into
each translation:

```sh
cd shell
xgettext --language=Python --keyword=_ --keyword=N_ --keyword=ngettext:1,2 \
  --from-code=UTF-8 --add-comments=Translators: --no-location \
  -o po/zoomies.pot zoomies_shell/*.py
for po in po/*.po; do msgmerge --update --no-fuzzy-matching "$po" po/zoomies.pot; done
```

To add a language, copy `po/zoomies.pot` to `po/<locale>.po`, translate it,
and add its locale to `i18n.supportedLocales` in
`nix/modules/nixos/platform/common.nix` and its pack to Firefox's
`languagePacks` in `nix/modules/nixos/zoomies/older.nix`.
