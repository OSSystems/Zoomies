# Runs inside X, before Xfce starts, and gives a fresh home the Zoomies look.
# Each file is written only when missing, so a kid's own choices win.
# $wallpaper is set by the Nix wrapper.

config=${XDG_CONFIG_HOME:-$HOME/.config}
xfconf=$config/xfce4/xfconf/xfce-perchannel-xml
mkdir -p "$xfconf" "$config/gtk-3.0"

# xfdesktop keys the wallpaper by connector, which is only known once X runs.
if [ ! -e "$xfconf/xfce4-desktop.xml" ]; then
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<channel name="xfce4-desktop" version="1.0">'
    echo '<property name="backdrop" type="empty"><property name="screen0" type="empty">'
    for monitor in $(xrandr --listactivemonitors | awk 'NR > 1 { print $4 }'); do
      echo "<property name=\"monitor$monitor\" type=\"empty\">"
      for workspace in 0 1 2 3; do
        echo "<property name=\"workspace$workspace\" type=\"empty\">"
        echo "<property name=\"last-image\" type=\"string\" value=\"$wallpaper\"/>"
        echo '</property>'
      done
      echo '</property>'
    done
    echo '</property></property>'
    # The clouds drift over the whole desktop; icons would sit on top of
    # them, and the file manager is on the panel.
    echo '<property name="desktop-icons" type="empty"><property name="style" type="int" value="0"/></property>'
    echo '</channel>'
  } >"$xfconf/xfce4-desktop.xml"
fi

# The friendly font of the kids' screens. Settings left out here keep
# their system defaults.
if [ ! -e "$xfconf/xsettings.xml" ]; then
  cat >"$xfconf/xsettings.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xsettings" version="1.0">
  <property name="Gtk" type="empty">
    <property name="FontName" type="string" value="Andika 11"/>
    <property name="MonospaceFontName" type="string" value="Monospace 11"/>
  </property>
</channel>
XML
fi

# The panel's own settings would also replace its default layout, so its
# colours come from GTK instead.
if [ ! -e "$config/gtk-3.0/gtk.css" ]; then
  cat >"$config/gtk-3.0/gtk.css" <<'CSS'
.xfce4-panel.background {
  background-color: #1d3557;
  background-image: none;
  color: white;
}
.xfce4-panel.background button {
  color: white;
  border-radius: 8px;
}
.xfce4-panel.background button:hover,
.xfce4-panel.background button:checked {
  background-color: alpha(#f6ad34, 0.45);
  background-image: none;
}
CSS
fi

exec startxfce4
