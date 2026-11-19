# GRUB draws only bitmaps and its own font format, so the wallpaper, the
# rounded boxes and Andika are converted at build time.
{
  andika,
  grub2,
  imagemagick,
  python3,
  resvg,
  runCommand,
  zoomies-splash,
}:

runCommand "zoomies-grub-theme"
  {
    nativeBuildInputs = [
      grub2
      imagemagick
      python3
      resvg
    ];
  }
  ''
    mkdir $out
    cp ${./theme.txt} $out/theme.txt
    wallpaper=${../../../../../assets/wallpaper/older.svg}
    python3 ${./background.py} $wallpaper menu.svg ${../../../../../assets/mascot/zip.svg}
    resvg -w 1920 menu.svg $out/background.png
    # While Zoomies loads, the splash's first frame, so that Zip seems to
    # come up from below onto the picture already on the screen.
    cp ${zoomies-splash}/share/zoomies-splash/first-frame.png $out/loading.png
    # The firmware leaves the screen black; these bring the picture up from
    # there. GRUB decodes and stretches each one, which paces the fade, so
    # they are small: dark and short-lived, nobody sees their detail.
    for step in 1 2 3 4 5 6 7; do
      magick $out/loading.png -resize 480x -fill black -colorize $((100 - step * 100 / 8))% \
        PNG24:$out/fade-$step.png
    done

    # Latin with accents and the arrows in the hint, to keep the fonts small.
    ranges=0x20-0x7E,0xA0-0x24F,0x2190-0x2193
    font() {
      grub-mkfont -r $ranges -s $2 -o $out/andika-$1-$2.pf2 ${andika}/share/fonts/truetype/Andika-''${1^}.ttf
    }
    font regular 24
    font bold 24
    font bold 48

    # GRUB stretches the middle piece and keeps the corners, so a rounded
    # box is cut into a 3x3 grid. Its PNG reader takes only 8-bit RGB(A), not
    # the grey or palette files ImageMagick would pick for plain colours.
    box() {
      local name=$1 colour=$2 radius=$3 side=$(($3 * 3))
      magick -size ''${side}x$side xc:none -fill "$colour" \
        -draw "roundrectangle 0,0 $((side - 1)),$((side - 1)) $radius,$radius" box.png
      local i=0
      for piece in nw n ne w c e sw s se; do
        magick box.png -crop ''${radius}x$radius+$(((i % 3) * radius))+$(((i / 3) * radius)) +repage \
          PNG32:$out/''${name}_$piece.png
        i=$((i + 1))
      done
    }
    box menu "rgba(255,255,255,0.8)" 24
    box select "#1d3557" 12
  ''
