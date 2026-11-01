#!/bin/bash
# One scheduled /naukri-run: the launchd plist calls this with morning or evening.
# Everything here works without the model: the gates run before `claude` so a
# blocked fire costs nothing, the spend and time caps sit outside the model, and
# a run that dies is closed and raises a notification.
# Overrides: NAUKRI_RUN_BUDGET (USD), NAUKRI_RUN_TIMEOUT (seconds), NAUKRI_CHROME_WAIT (seconds).
set -u

slot="${1:?usage: run.sh morning|evening}"
project="$(cd "$(dirname "$0")/../.." && pwd)"
data="${JOBTOOL_ROOT:-$project}/data"
budget="${NAUKRI_RUN_BUDGET:-14}"
limit="${NAUKRI_RUN_TIMEOUT:-5400}"
when="$(date +%Y%m%d-%H%M)"
log="$data/logs/$slot-$when.json"

notify() {
  osascript -e "display notification \"$1\" with title \"Naukri run ($slot)\"" >/dev/null 2>&1 || true
}

cd "$project" || exit 1
mkdir -p "$data/logs" "$data/runs"
find "$data/logs" -type f -name '*.json' -mtime +30 -delete

# NAUKRI_LEAN comes from run-settings.json inside claude; the check needs it here too.
gate="$(NAUKRI_LEAN=1 python3 scripts/jobtool.py start "$slot" --check 2>&1)"
code=$?
if [ "$code" -eq 3 ]; then
  echo "$gate" > "$data/runs/$when-$slot-blocked.md"
  case "$gate" in *cooldown*|*corrupt*) notify "$gate" ;; esac
  exit 0
elif [ "$code" -ne 0 ]; then
  notify "jobtool failed: $gate"
  echo "$gate" >&2
  exit 1
fi

if ! pgrep -xq "Google Chrome"; then
  open -a "Google Chrome"
  sleep "${NAUKRI_CHROME_WAIT:-20}"
fi

# alarm survives exec, so the signal reaches claude itself rather than caffeinate.
caffeinate -i perl -e 'alarm shift; exec { $ARGV[0] } @ARGV or die "exec: $!"' "$limit" \
  claude -p "/naukri-run $slot" --chrome \
  --settings "$project/profile/run-settings.json" \
  --model claude-opus-5-5 --effort high \
  --permission-mode dontAsk --permission-prompts none \
  --max-budget-usd "$budget" \
  --output-format json < /dev/null > "$log" 2>> "$data/logs/$slot.err"
code=$?

summary="$(python3 - "$log" <<'PY'
import json, sys
try:
    r = json.load(open(sys.argv[1]))
    print(f"cost {r.get('total_cost_usd', '?')} denials {len(r.get('permission_denials') or [])}")
except (OSError, ValueError):
    print("cost ? denials ?")
PY
)"
reaped="$(python3 scripts/jobtool.py reap 2>&1)"
echo "$when $slot exit $code $summary $reaped" >> "$data/logs/runs.log"

if [ "$code" -ne 0 ] || [ "$reaped" != "clean" ]; then
  notify "Run died (exit $code, $reaped). Log: $log"
fi
case "$summary" in *"denials 0"|*"denials ?") ;; *) notify "Tools were denied: $summary" ;; esac
cooldown="$(python3 scripts/jobtool.py cooldown show 2>&1)"
case "$cooldown" in "no cooldown") ;; *) notify "$cooldown" ;; esac
exit "$code"
