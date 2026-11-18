---
name: spec
description: The one spec format every project plan is turned into, whoever wrote the plan. Use when writing, updating or reading a project spec.
---

# Project spec

Every plan, whether it's a client email, a PM document or a developer checklist, becomes a spec in exactly this format. The architect agent builds from the spec alone, so anything missing here gets guessed later.

## Source tags

Tag every item in sections 3–10 with where it came from:

- `[plan]`: stated in the plan
- `[answer]`: stated by a human in a reply on the issue
- `[default]`: taken from the house defaults in `CLAUDE.md`

Nothing else is allowed. If you can't tag an item, it doesn't go in the spec. It goes in Open questions.

## Template

```markdown
🤖 Intake agent: spec v<N>

**Status:** <Needs info | Complete>, <X> blocking questions, <Y> non-blocking
**Plan written by:** <client | project manager | developer | mixed>, for information only

## 1. Summary
<two or three sentences: what it is, who it's for, the problem it solves>

## 2. Users and roles
| Role | What they can do | Source |

## 3. User stories
| ID | As a… I can… so that… | Priority (Must/Should/Could) | Source |

## 4. Acceptance criteria
<for every Must story: testable bullets, each with a source tag>

## 5. Business rules
<every number, limit, time and rule, each with a source tag. Write numbers, not "a few">

## 6. Data
| Entity | Key fields | Source |

## 7. Screens
| Screen | Who uses it | What's on it | Source |

## 8. Platform and stack
<platform, backend, database, frontend, login method, each with a source tag>

## 9. Out of scope
<bullets, each with a source tag>

## 10. Open questions
| # | Question | Why it matters | Blocking? | Suggested answer |

## 11. Changes since last version
<only from v2 on: what changed and which answer changed it>
```

## Rules

- **Check every section for every plan.** Don't change what you look for based on who wrote the plan. Clients usually skip the technical side, PMs skip the data, developers skip users and "done", but any plan can be missing anything.
- **Blocking question:** the architect can't design without the answer. That covers anything affecting the data model, a business rule, login, or whether a feature is in scope. **Non-blocking:** there's a safe answer to suggest.
- **Every question gets a suggested answer,** so a human can reply "accept the suggestions".
- **Contradictions are always blocking.** Quote both versions and ask which is right. Never pick one.
- **Vague words aren't requirements.** "Soon", "easy", "fast" and "not fancy" either become a measurable rule (via a question) or are left out.
- **A feature needing something the house doesn't have** (email, SMS, payments): blocking question, and suggest moving it to Out of scope.
- **Status is Complete only with zero blocking questions.** Non-blocking questions can stay. Their suggested answers count as accepted when a human moves the card to Ready.
