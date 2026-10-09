#!/usr/bin/env sh
# Link this checkout into a Blender version's extensions directory (editable install).
#   ./scripts/install.sh 5.2              link into user_default
#   ./scripts/install.sh 5.2 --enable     ... and enable it (runs Blender in the background; close Blender first)
#   ./scripts/install.sh 5.2 --uninstall  remove the link (checkout untouched)
# Env: BLENDER_BIN (for --enable), BLENDER_CONFIG (override the per-user config root)
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"  # the checkout is the parent of scripts/
version="${1:-}"
action="${2:-}"
repo="user_default"
if [ -z "${BLENDER_CONFIG:-}" ]; then
  case "$(uname -s)" in
    Darwin) BLENDER_CONFIG="$HOME/Library/Application Support/Blender" ;;
    *)      BLENDER_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/blender" ;;
  esac
fi
if [ -z "$version" ]; then
  echo "usage: $0 <version> [--enable|--uninstall]"
  echo "versions with a config directory: $(ls "$BLENDER_CONFIG" 2>/dev/null | grep -E '^[0-9]+\.[0-9]+$' | tr '\n' ' ')"
  exit 1
fi
case "$version" in [0-9]*.[0-9]*) ;; *) echo "version must look like 5.2" >&2; exit 1 ;; esac
link="$BLENDER_CONFIG/$version/extensions/$repo/py2gn"

if [ "$action" = "--uninstall" ]; then
  if [ -L "$link" ]; then rm "$link"; echo "removed link $link (checkout untouched)"; exit 0; fi
  if [ -e "$link" ]; then echo "$link is a real directory; remove it in Blender's preferences" >&2; exit 1; fi
  echo "not installed: $link"; exit 0
fi

if [ -L "$link" ]; then
  if [ "$(readlink "$link")" = "$root" ]; then echo "already installed: $link -> $root"
  else echo "$link links to $(readlink "$link"); remove it first ($0 $version --uninstall)" >&2; exit 1; fi
elif [ -e "$link" ]; then
  echo "$link is a real directory; remove it in Blender's preferences first" >&2; exit 1
else
  mkdir -p "$(dirname "$link")"
  ln -s "$root" "$link"
  echo "linked $link -> $root"
fi

if [ "$action" = "--enable" ]; then
  "${BLENDER_BIN:-blender}" --background --python-exit-code 1 --python-expr \
    "import bpy; bpy.ops.extensions.repo_refresh_all(); assert bpy.ops.preferences.addon_enable(module='bl_ext.$repo.py2gn') == {'FINISHED'}; bpy.ops.wm.save_userpref()"
  echo "enabled bl_ext.$repo.py2gn"
fi
