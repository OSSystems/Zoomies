# Runs inside X, before Xfce starts, and gives a fresh home the Zoomies look.
# The look is written only when missing, so a kid's own choices win; how
# the session and the windows behave is written every time.
# $wallpaper is set by the Nix wrapper.

config=${XDG_CONFIG_HOME:-$HOME/.config}
xfconf=$config/xfce4/xfconf/xfce-perchannel-xml
mkdir -p "$xfconf"

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

# The shelf replaces the panel, which also goes from homes made before it.
cat >"$xfconf/xfce4-session.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-session" version="1.0">
  <property name="sessions" type="empty">
    <property name="Failsafe" type="empty">
      <property name="IsFailsafe" type="bool" value="true"/>
      <property name="Count" type="int" value="4"/>
      <property name="Client0_Command" type="array"><value type="string" value="xfwm4"/></property>
      <property name="Client0_Priority" type="int" value="15"/>
      <property name="Client0_PerScreen" type="bool" value="false"/>
      <property name="Client1_Command" type="array"><value type="string" value="xfsettingsd"/></property>
      <property name="Client1_Priority" type="int" value="20"/>
      <property name="Client1_PerScreen" type="bool" value="false"/>
      <property name="Client2_Command" type="array">
        <value type="string" value="Thunar"/>
        <value type="string" value="--daemon"/>
      </property>
      <property name="Client2_Priority" type="int" value="30"/>
      <property name="Client2_PerScreen" type="bool" value="false"/>
      <property name="Client3_Command" type="array"><value type="string" value="xfdesktop"/></property>
      <property name="Client3_Priority" type="int" value="35"/>
      <property name="Client3_PerScreen" type="bool" value="false"/>
    </property>
  </property>
</channel>
XML

# Apps fill the screen with a title strip holding only a close button;
# nothing shrinks, moves or hides them. One workspace, so an app cannot
# vanish to another one.
cat >"$xfconf/xfwm4.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfwm4" version="1.0">
  <property name="general" type="empty">
    <property name="borderless_maximize" type="bool" value="true"/>
    <property name="button_layout" type="string" value="|C"/>
    <property name="double_click_action" type="string" value="none"/>
    <property name="restore_on_move" type="bool" value="false"/>
    <property name="theme" type="string" value="Zoomies"/>
    <property name="title_alignment" type="string" value="left"/>
    <property name="title_font" type="string" value="Andika Bold 14"/>
    <property name="titleless_maximize" type="bool" value="false"/>
    <property name="workspace_count" type="int" value="1"/>
  </property>
</channel>
XML

exec startxfce4
