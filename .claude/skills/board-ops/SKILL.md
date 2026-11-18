---
name: board-ops
description: Read and update the Agent Pipeline project board (GitHub Projects board 2). Use whenever you need to see what work exists, pick up a card, change a card's Status, set its Agent, Size or Priority field, or link issue dependencies.
---

# board-ops

The project board is the shared to-do list for every agent. Always change it with this script. Never call `gh project` directly: it needs internal IDs that are easy to get wrong.

Run every command from the repo root:

```
bash .claude/skills/board-ops/board.sh list                      # every card: number, status, agent, title
bash .claude/skills/board-ops/board.sh list "Ready"              # only cards in one column
bash .claude/skills/board-ops/board.sh show 12                   # one card's fields
bash .claude/skills/board-ops/board.sh add 12                    # put issue #12 on the board
bash .claude/skills/board-ops/board.sh move 12 "In progress"     # change Status
bash .claude/skills/board-ops/board.sh set 12 Agent backend      # set Agent, Size or Priority
bash .claude/skills/board-ops/board.sh block 12 9                # #12 is blocked by #9
bash .claude/skills/board-ops/board.sh blockers 12               # what blocks #12, and whether it's closed
bash .claude/skills/board-ops/board.sh child 6 12                # #12 becomes a sub-issue of #6
```

Names are case-sensitive. If you use a wrong one, the script prints the valid options. `block` and `child` are for the architect only.

## Columns, in order

Inbox → Needs info → Planned → Ready → In progress → In review → Done

## Which columns you may move a card into

| Agent | May move cards to |
|---|---|
| intake | Needs info, Planned |
| architect | Planned |
| db, backend, frontend, infra | In progress, In review |
| qa, reviewer | none (comment on the PR instead) |

- **Ready** means a human approved the card. Only a human moves cards there. The script refuses.
- **Done** happens automatically when the issue closes or its PR merges. Never move a card to Done yourself.
- Only start work on a card that is in **Ready** and whose blockers are all `closed` (check with `blockers`).
- When you start a card, move it to **In progress**. When your PR is open, move it to **In review**.

## Fields

- **Agent:** db, backend, frontend, infra, qa
- **Size:** S, M, L
- **Priority:** High, Medium, Low

## When something fails

If the script prints an error, stop and report the exact message. Don't work around it with raw `gh` commands.
