#!/usr/bin/env bash
# board-ops: move cards on the Agent Pipeline board without touching GitHub node IDs.
#
# Usage:
#   bash .claude/skills/board-ops/board.sh list [Status]
#   bash .claude/skills/board-ops/board.sh show <issue>
#   bash .claude/skills/board-ops/board.sh add  <issue>
#   bash .claude/skills/board-ops/board.sh card <issue> <Status> [Agent] [Size] [Priority]   (everything in one go)
#   bash .claude/skills/board-ops/board.sh move <issue> "<Status>"
#   bash .claude/skills/board-ops/board.sh set  <issue> <Field> <Option>
#   bash .claude/skills/board-ops/board.sh block <issue> <blocker>   (issue is blocked by blocker)
#   bash .claude/skills/board-ops/board.sh blockers <issue>          (list what blocks an issue)
#   bash .claude/skills/board-ops/board.sh child <parent> <issue>    (make issue a sub-issue of parent)
#   bash .claude/skills/board-ops/board.sh limits                    (GitHub API budget left)
#
# Locally it uses your gh login. In GitHub Actions, set GH_TOKEN to the PROJECT_TOKEN secret.

set -euo pipefail
shopt -s inherit_errexit  # stop inside $(...) too, not just at the top level

OWNER="${BOARD_OWNER:-mphomaaga}"
PROJECT="${BOARD_PROJECT:-2}"
REPO="${BOARD_REPO:-mphomaaga/lab-booking}"

# Columns only a human (or a GitHub workflow) may move a card into.
HUMAN_ONLY="Ready Done"

# Board field IDs rarely change, so they're cached to save GitHub API calls.
CACHE_DIR="${BOARD_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/board-ops}"
CACHE_MINUTES=30

die() { echo "board: $*" >&2; exit 1; }

# Names go into lookups, so only allow plain characters.
check_name() {
  [[ "$1" =~ ^[A-Za-z0-9\ _-]+$ ]] || die "invalid name '$1' (letters, digits, spaces, - and _ only)"
}

check_issue() {
  [[ "$1" =~ ^[0-9]+$ ]] || die "issue must be a number, got '$1'"
}

# Runs gh. On a rate-limit error, says when GitHub's budget resets and stops.
ghx() {
  local errf
  errf="$(mktemp)"
  if gh "$@" 2>"$errf"; then rm -f "$errf"; return 0; fi
  if grep -qi "rate limit" "$errf"; then
    rm -f "$errf"
    die "GitHub rate limit hit. $(limits_line). Stop and report this; don't retry."
  fi
  cat "$errf" >&2; rm -f "$errf"
  return 1
}

limits_line() {
  gh api rate_limit --jq '.resources.graphql
    | "GraphQL budget: \(.remaining) of \(.limit) left, resets \(.reset | todate)"' 2>/dev/null \
    || echo "couldn't read the GitHub rate limit"
}

cached() {  # cached <file> <gh args...>: prints a cached gh result, refreshing it when stale
  local f="$CACHE_DIR/$1"; shift
  mkdir -p "$CACHE_DIR"
  if [[ ! -s "$f" || -n "$(find "$f" -mmin +"$CACHE_MINUTES" 2>/dev/null)" ]]; then
    if ! ghx "$@" > "$f.tmp"; then rm -f "$f.tmp"; exit 1; fi
    mv "$f.tmp" "$f"
  fi
  cat "$f"
}

fields_json() {
  cached "fields-$OWNER-$PROJECT.json" project field-list "$PROJECT" --owner "$OWNER" --format json
}

project_id() {
  cached "project-$OWNER-$PROJECT.id" project view "$PROJECT" --owner "$OWNER" --format json --jq '.id'
}

# lookup <what> <field> [option]: what = field | option | options
lookup() {
  fields_json | python3 -c '
import json, sys
what, field = sys.argv[1], sys.argv[2]
d = json.load(sys.stdin)
f = next((x for x in d["fields"] if x["name"] == field), None)
if what == "field":
    print(f["id"] if f else "")
elif what == "option":
    print(next((o["id"] for o in (f or {}).get("options", []) if o["name"] == sys.argv[3]), ""))
else:
    print(", ".join(o["name"] for o in (f or {}).get("options", [])))
' "$@"
}

# Adds the issue to the board if needed and prints its item ID.
# Adding an issue that's already on the board just returns its existing item.
item_id() {
  local id
  id="$(ghx project item-add "$PROJECT" --owner "$OWNER" \
    --url "https://github.com/$REPO/issues/$1" --format json --jq '.id')"
  [[ -n "$id" ]] || die "could not find or add issue #$1"
  echo "$id"
}

# Checks a field/option pair and prints "fieldId optionId".
resolve() {
  local field="$1" option="$2" fid oid
  check_name "$field"; check_name "$option"
  fields_json > /dev/null  # fetch (or reuse) the field list first, so errors surface cleanly
  fid="$(lookup field "$field")"
  [[ -n "$fid" ]] || die "no field called '$field' on board $PROJECT"
  oid="$(lookup option "$field" "$option")"
  [[ -n "$oid" ]] || die "'$option' is not an option of $field. Valid: $(lookup options "$field")"
  echo "$fid $oid"
}

check_status_allowed() {
  for col in $HUMAN_ONLY; do
    if [[ "$1" == "$col" && "${BOARD_HUMAN:-}" != "1" ]]; then
      die "only a human moves cards to $col (merged PRs move cards to Done automatically)"
    fi
  done
}

edit() {  # edit <itemId> <fieldId> <optionId>
  local pid
  pid="$(project_id)"
  ghx project item-edit --id "$1" --project-id "$pid" \
    --field-id "$2" --single-select-option-id "$3" > /dev/null
}

# The REST id (not the number) of an issue, needed by the dependency and sub-issue APIs.
issue_db_id() {
  ghx api "repos/$REPO/issues/$1" --jq '.id'
}

cmd="${1:-}"
case "$cmd" in
  list)
    status="${2:-}"
    [[ -z "$status" ]] || check_name "$status"
    ghx project item-list "$PROJECT" --owner "$OWNER" --limit 300 --format json \
      --jq ".items[] | select(\"$status\" == \"\" or .status == \"$status\")
            | \"#\(.content.number // \"-\")\t\(.status // \"-\")\t\(.agent // \"-\")\t\(.title)\""
    ;;
  show)
    [[ $# -eq 2 ]] || die "usage: show <issue>"
    check_issue "$2"
    ghx project item-list "$PROJECT" --owner "$OWNER" --limit 300 --format json \
      --jq ".items[] | select(.content.number == $2 and .content.repository == \"$REPO\")
            | {issue: .content.number, title, status, agent, size, priority}"
    ;;
  add)
    [[ $# -eq 2 ]] || die "usage: add <issue>"
    check_issue "$2"
    item_id "$2" > /dev/null
    echo "#$2 is on the board"
    ;;
  card)
    [[ $# -ge 3 && $# -le 6 ]] || die "usage: card <issue> <Status> [Agent] [Size] [Priority]"
    check_issue "$2"; check_status_allowed "$3"
    # Check every name before changing anything, so a typo can't leave a half-set card.
    p="$(resolve Status "$3")"
    pairs=("$p")
    names=("Status=$3")
    extras=("${@:4}")
    fields=(Agent Size Priority)
    for i in "${!extras[@]}"; do
      field="${fields[$i]}"; value="${extras[$i]}"
      [[ -n "$value" ]] || continue
      p="$(resolve "$field" "$value")"
      pairs+=("$p"); names+=("$field=$value")
    done
    iid="$(item_id "$2")"
    for p in "${pairs[@]}"; do edit "$iid" ${p% *} ${p#* }; done
    echo "#$2: ${names[*]}"
    ;;
  move)
    [[ $# -eq 3 ]] || die "usage: move <issue> \"<Status>\""
    check_issue "$2"; check_status_allowed "$3"
    p="$(resolve Status "$3")"
    iid="$(item_id "$2")"
    edit "$iid" ${p% *} ${p#* }
    echo "#$2: Status -> $3"
    ;;
  set)
    [[ $# -eq 4 ]] || die "usage: set <issue> <Field> <Option>"
    check_issue "$2"
    [[ "$3" != "Status" ]] || die "use 'move' to change Status"
    p="$(resolve "$3" "$4")"
    iid="$(item_id "$2")"
    edit "$iid" ${p% *} ${p#* }
    echo "#$2: $3 -> $4"
    ;;
  block)
    [[ $# -eq 3 ]] || die "usage: block <issue> <blocker>"
    check_issue "$2"; check_issue "$3"
    [[ "$2" != "$3" ]] || die "an issue can't block itself"
    bid="$(issue_db_id "$3")"
    [[ -n "$bid" ]] || die "issue #$3 not found"
    ghx api -X POST "repos/$REPO/issues/$2/dependencies/blocked_by" -F issue_id="$bid" > /dev/null
    sleep 1  # GitHub rate-limits rapid dependency creation
    echo "#$2 is blocked by #$3"
    ;;
  blockers)
    [[ $# -eq 2 ]] || die "usage: blockers <issue>"
    check_issue "$2"
    ghx api "repos/$REPO/issues/$2/dependencies/blocked_by" \
      --jq '.[] | "#\(.number)\t\(.state)\t\(.title)"'
    ;;
  child)
    [[ $# -eq 3 ]] || die "usage: child <parent> <issue>"
    check_issue "$2"; check_issue "$3"
    sid="$(issue_db_id "$3")"
    [[ -n "$sid" ]] || die "issue #$3 not found"
    ghx api -X POST "repos/$REPO/issues/$2/sub_issues" -F sub_issue_id="$sid" > /dev/null
    sleep 1
    echo "#$3 is now a sub-issue of #$2"
    ;;
  limits)
    limits_line
    ;;
  *)
    sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
    [[ -z "$cmd" || "$cmd" == "help" ]] || exit 1
    ;;
esac
