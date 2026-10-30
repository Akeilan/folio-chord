#!/bin/sh
# Builds folio-chord_<version>_all.deb from this tree: the Python app (app/) and its icons (share/).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(sed -n 's/^Version: //p' "$HERE/packaging/DEBIAN/control")"
APPV="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$HERE/app/folio_chord/__init__.py")"
[ "$VERSION" = "$APPV" ] || { echo "version mismatch: control $VERSION, app $APPV"; exit 1; }
OUT="${1:-$HERE}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -a "$HERE/packaging/root/." "$STAGE/"
mkdir -p "$STAGE/usr/lib/folio-chord" "$STAGE/usr/share/folio-chord"
cp -a "$HERE/app/folio_chord" "$STAGE/usr/lib/folio-chord/"
find "$STAGE/usr/lib/folio-chord" -name '__pycache__' -prune -exec rm -rf {} +
cp -a "$HERE/share/icons" "$STAGE/usr/share/folio-chord/"
mkdir -p "$STAGE/DEBIAN"
cp "$HERE/packaging/DEBIAN/"* "$STAGE/DEBIAN/"
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm" "$STAGE/DEBIAN/postrm" "$STAGE/usr/bin/folio-chord"
SIZE="$(du -sk "$STAGE" | cut -f1)"
sed -i "s/^Installed-Size: .*/Installed-Size: $SIZE/" "$STAGE/DEBIAN/control"
dpkg-deb --root-owner-group --build -Zxz "$STAGE" "$OUT/folio-chord_${VERSION}_all.deb" >/dev/null
echo "Built $OUT/folio-chord_${VERSION}_all.deb"
