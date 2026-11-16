#!/usr/bin/env bash
# board-ops: move cards on the Agent Pipeline board without touching GitHub node IDs.
#
# Usage:
#   bash .claude/skills/board-ops/board.sh list [Status]
#   bash .claude/skills/board-ops/board.sh show <issue>
#   bash .claude/skills/board-ops/board.sh add  <issue>
#   bash .claude/skills/board-ops/board.sh move <issue> "<Status>"
#   bash .claude/skills/board-ops/board.sh set  <issue> <Field> <Option>
#
# Locally it uses your gh login. In GitHub Actions, set GH_TOKEN to the PROJECT_TOKEN secret.

set -euo pipefail

OWNER="${BOARD_OWNER:-mphomaaga}"
PROJECT="${BOARD_PROJECT:-2}"
REPO="${BOARD_REPO:-mphomaaga/lab-booking}"

# Columns only a human (or a GitHub workflow) may move a card into.
HUMAN_ONLY="Ready Done"

die() { echo "board: $*" >&2; exit 1; }

# Names go into jq filters, so only allow plain characters.
check_name() {
  [[ "$1" =~ ^[A-Za-z0-9\ _-]+$ ]] || die "invalid name '$1' (letters, digits, spaces, - and _ only)"
}

check_issue() {
  [[ "$1" =~ ^[0-9]+$ ]] || die "issue must be a number, got '$1'"
}

project_id() {
  gh project view "$PROJECT" --owner "$OWNER" --format json --jq '.id'
}

# Prints the board item ID for an issue in $REPO, or nothing if it isn't on the board.
item_id() {
  gh project item-list "$PROJECT" --owner "$OWNER" --limit 1000 --format json \
    --jq ".items[] | select(.content.number == $1 and .content.repository == \"$REPO\") | .id"
}

field_id() {
  gh project field-list "$PROJECT" --owner "$OWNER" --format json \
    --jq ".fields[] | select(.name == \"$1\") | .id"
}

option_id() {
  gh project field-list "$PROJECT" --owner "$OWNER" --format json \
    --jq ".fields[] | select(.name == \"$1\") | .options[]? | select(.name == \"$2\") | .id"
}

option_names() {
  gh project field-list "$PROJECT" --owner "$OWNER" --format json \
    --jq ".fields[] | select(.name == \"$1\") | [.options[]?.name] | join(\", \")"
}

# Adds the issue to the board if it isn't there yet; prints its item ID.
ensure_item() {
  local id
  id="$(item_id "$1")"
  if [[ -z "$id" ]]; then
    id="$(gh project item-add "$PROJECT" --owner "$OWNER" \
      --url "https://github.com/$REPO/issues/$1" --format json --jq '.id')"
  fi
  [[ -n "$id" ]] || die "could not find or add issue #$1"
  echo "$id"
}

set_option() {
  local issue="$1" field="$2" option="$3" fid oid iid pid
  check_issue "$issue"; check_name "$field"; check_name "$option"
  fid="$(field_id "$field")"
  [[ -n "$fid" ]] || die "no field called '$field' on board $PROJECT"
  oid="$(option_id "$field" "$option")"
  [[ -n "$oid" ]] || die "'$option' is not an option of $field. Valid: $(option_names "$field")"
  iid="$(ensure_item "$issue")"
  pid="$(project_id)"
  gh project item-edit --id "$iid" --project-id "$pid" \
    --field-id "$fid" --single-select-option-id "$oid" > /dev/null
  echo "#$issue: $field -> $option"
}

cmd="${1:-}"
case "$cmd" in
  list)
    status="${2:-}"
    [[ -z "$status" ]] || check_name "$status"
    gh project item-list "$PROJECT" --owner "$OWNER" --limit 1000 --format json \
      --jq ".items[] | select(\"$status\" == \"\" or .status == \"$status\")
            | \"#\(.content.number // \"-\")\t\(.status // \"-\")\t\(.agent // \"-\")\t\(.title)\""
    ;;
  show)
    [[ $# -eq 2 ]] || die "usage: show <issue>"
    check_issue "$2"
    gh project item-list "$PROJECT" --owner "$OWNER" --limit 1000 --format json \
      --jq ".items[] | select(.content.number == $2 and .content.repository == \"$REPO\")
            | {issue: .content.number, title, status, agent, size, priority}"
    ;;
  add)
    [[ $# -eq 2 ]] || die "usage: add <issue>"
    check_issue "$2"
    ensure_item "$2" > /dev/null
    echo "#$2 is on the board"
    ;;
  move)
    [[ $# -eq 3 ]] || die "usage: move <issue> \"<Status>\""
    for col in $HUMAN_ONLY; do
      if [[ "$3" == "$col" && "${BOARD_HUMAN:-}" != "1" ]]; then
        die "only a human moves cards to $col (merged PRs move cards to Done automatically)"
      fi
    done
    set_option "$2" "Status" "$3"
    ;;
  set)
    [[ $# -eq 4 ]] || die "usage: set <issue> <Field> <Option>"
    [[ "$3" != "Status" ]] || die "use 'move' to change Status"
    set_option "$2" "$3" "$4"
    ;;
  *)
    sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
    [[ -z "$cmd" || "$cmd" == "help" ]] || exit 1
    ;;
esac
