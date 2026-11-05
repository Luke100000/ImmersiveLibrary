#!/bin/sh
# Clones or updates the Pixel Perfection block and item textures, which the furniture viewer draws sprites with.
# A pack only holds the textures it overrides and the newest revision dropped some that older game versions
# still use, so revisions are stacked like resource packs, later ones winning.
#     scripts/fetch_textures.sh
set -eu

cd "$(dirname "$0")/.."

repository=https://github.com/NovaWostra/Pixel-Perfection-Chorus-Eddit.git
cache=.cache/pixel-perfection.git
target=static/vendor/pixel-perfection
# Oldest first, c42000e is the last revision before textures were renamed for 26.1
revisions="c42000e main"

if [ ! -d "$cache" ]; then
    git clone --bare --filter=blob:none --quiet "$repository" "$cache"
else
    git -C "$cache" fetch --quiet origin main:main
fi

rm -rf "$target"
mkdir -p "$target"
for revision in $revisions; do
    git -C "$cache" archive "$revision" assets/minecraft/textures/block assets/minecraft/textures/item | tar -x -C "$target"
done

# The viewer only requests sprites listed here, mapped to whether they have a .mcmeta
cd "$target/assets/minecraft/textures"
find block item -maxdepth 1 -name '*.png' | sed -n 's/^\([a-z]*\/[a-z0-9_]*\)\.png$/\1/p' | sort | while read -r sprite; do
    [ -f "$sprite.png.mcmeta" ] && meta=true || meta=false
    printf '"%s":%s\n' "$sprite" "$meta"
done | paste -sd, | sed 's/.*/{&}/' > ../../../index.json
