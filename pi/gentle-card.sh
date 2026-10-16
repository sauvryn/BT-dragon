#!/bin/bash
# Gentler on the memory card: the system log lives in the Pi's memory instead of on the card.
# Run by install.sh and update.sh; safe to run again. To undo it:
#   sudo rm /etc/systemd/journald.conf.d/bt-dragon.conf && sudo systemctl restart systemd-journald
#
# Why: a memory card wears out with writing, and the system log (journalctl) is written all
# day. In memory, it's still there for "journalctl -u bt-dragon" until the Pi switches off,
# but nothing is written to the card. The old log on the card is deleted too: it may hold
# lines from older versions of Harald that logged more than they should have.
set -e
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/bt-dragon.conf <<'EOF'
# BT Dragon: keep the system log in memory (RAM), not on the memory card.
[Journal]
Storage=volatile
RuntimeMaxUse=16M
EOF
systemctl restart systemd-journald || true
if [ -d /var/log/journal ]; then
  rm -rf /var/log/journal
  echo "(The system log is now kept in memory; the old copy on the card has been deleted.)"
fi
