#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.flight-price-tracker.plist"
chmod +x "$ROOT/scripts/run-local.sh"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.flight-price-tracker</string>
  <key>ProgramArguments</key><array><string>$ROOT/scripts/run-local.sh</string></array>
  <key>StartInterval</key><integer>600</integer>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StandardOutPath</key><string>$ROOT/tracker.log</string>
  <key>StandardErrorPath</key><string>$ROOT/tracker.log</string>
</dict></plist>
PLIST
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Every 10 min. Log: $ROOT/tracker.log"
