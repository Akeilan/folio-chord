#!/bin/bash
# Folio Chord release checks: engine tests, UI tests, desktop themes and command walk (source, on
# 22.04), the .deb, then the installed package on 22.04, 22.04 without LibreOffice and 24.04, and a
# Wayland pass on 24.04.   XD=<X display> tools/release.sh
set -u
R=/home/claude/folio-chord
XD=${XD:-95}
V=$(sed -n 's/^Version: //p' $R/packaging/DEBIAN/control)
/home/claude/mounts.sh >/dev/null 2>&1
pgrep -x Xvfb -a | grep -q ":$XD " || { rm -f /tmp/.X$XD-lock /tmp/.X11-unix/X$XD; setsid -f Xvfb :$XD -screen 0 1600x1000x24 -nolisten tcp </dev/null >/dev/null 2>&1; sleep 1; }
UI=${UI_TESTS:-ui_library.py ui_play.py ui_net.py ui_cd.py ui_more.py ui_shared.py ui_cast.py ui_classic.py ui_backlog8.py}
ENGINE="test_engine.py test_net.py test_more.py test_sharing.py test_cast.py test_backlog8.py"
# C8-39: a suite that dies or never finishes prints nothing; say so instead of passing in silence
judge() {  # name: reads the suite's output on stdin
  out=$(cat); echo "$out" | grep -E '^FAIL|UI all|UI FAILS|Traceback|WALK|checks, |all passed'
  echo "$out" | grep -qE 'UI all passed|all passed|^[0-9]+ checks, 0 failed' || echo "FAIL $1 did not finish"
}
mkdir -p /srv/jammy/src/chord && rsync -a --delete --exclude .git $R/ /srv/jammy/src/chord/
if [ -z "${INSTALLED_ONLY:-}" ]; then
echo "== engine"
for t in $ENGINE; do
  chroot /srv/jammy bash -c "cd /src/chord; timeout 900 python3 tests/$t 2>&1" | judge $t
done
echo "== ui (source)"
for u in $UI; do
  echo $u
  chroot /srv/jammy bash -c "cd /src/chord; DISPLAY=:$XD UI_TIMEOUT=600 dbus-run-session -- sh tests/run_ui.sh $u 2>&1" | judge $u
done
echo "== X2-01 desktop themes"
chroot /srv/jammy bash -c "cd /src/chord; DISPLAY=:$XD UI_TIMEOUT=400 sh tests/theme_run.sh 2>&1 | grep -E '^--|^FAIL|UI all|Traceback'"
echo "== walk"
rm -f /srv/jammy/tmp/chord-command-walk.tsv
chroot /srv/jammy bash -c "cd /src/chord; DISPLAY=:$XD UI_TIMEOUT=900 WALK_OUT=/tmp/chord-command-walk.tsv sh tests/run_ui.sh command_walk.py 2>&1 | grep -E 'WALK|^FAIL|Traceback|not available'"
# a walk that hangs prints nothing at all, so say so rather than passing in silence
[ -s /srv/jammy/tmp/chord-command-walk.tsv ] || echo "FAIL the command walk did not finish"
mkdir -p $R/docs; cp /srv/jammy/tmp/chord-command-walk.tsv $R/docs/command-walk.tsv 2>/dev/null
fi
echo "== deb"
sh $R/build-deb.sh /home/claude/out && ls -la /home/claude/out/folio-chord_${V}_all.deb
echo "== X4-05: against the app it replaces"
bash /home/claude/folio-suite/tools/compare-release.sh folio-chord /home/claude/folio-chord /home/claude/out/folio-chord_${V}_all.deb || \
  echo "X4-05 FAILED: this candidate shows less than the app it replaces"
for m in ${MACHINES:-/srv/jammy /srv/nolo /srv/noble}; do
  cp /home/claude/out/folio-chord_${V}_all.deb $m/tmp/
  flock /home/claude/.dpkg.lock chroot $m bash -c "DEBIAN_FRONTEND=noninteractive apt-get install --reinstall -y -q /tmp/folio-chord_${V}_all.deb >/tmp/chord-install.log 2>&1 || tail -5 /tmp/chord-install.log; dpkg -l folio-chord | tail -1 | awk '{print \$1, \$3}'; folio-chord --version"
  rm -rf $m/tmp/chordtests; mkdir -p $m/tmp/chordtests; cp -r $R/tests/* $m/tmp/chordtests/
  echo "== installed in $m"
  for t in $ENGINE; do
    chroot $m bash -c "cd /tmp/chordtests; export PYTHONPATH=/usr/lib/folio-chord; timeout 900 python3 $t 2>&1" | judge "$t ($m)"
  done
  for u in $UI command_walk.py; do
    chroot $m bash -c "cd /tmp/chordtests; DISPLAY=:$XD UI_TIMEOUT=900 dbus-run-session -- sh run_installed.sh /tmp/chordtests/$u 2>&1" | judge "$u ($m)"
  done
  chroot $m bash -c "cd /tmp/chordtests; DISPLAY=:$XD UI_TIMEOUT=600 sh theme_run.sh run_installed.sh 2>&1 | grep -E '^--|^FAIL|UI all|Traceback'"
done
echo "== Wayland (Weston) on 24.04"
cp /home/claude/folio-suite/tests/wl.sh /srv/noble/tmp/wl.sh
chroot /srv/noble bash -c "cd /tmp/chordtests; DISPLAY=:$XD UI_TIMEOUT=900 /tmp/wl.sh sh -c 'sh run_installed.sh /tmp/chordtests/ui_play.py; sh run_installed.sh /tmp/chordtests/ui_shared.py; sh run_installed.sh /tmp/chordtests/ui_classic.py; sh run_installed.sh /tmp/chordtests/ui_backlog8.py; sh theme_run.sh run_installed.sh' 2>&1 | grep -E '^-- |^FAIL|UI all|UI FAILS|Traceback'"
exit 0
