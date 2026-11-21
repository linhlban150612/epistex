# Subagents

Taken from the Subagents section of the pstack `poteto-mode` skill.

- Spawn with the subagent tool of your harness. Do not set a model: the subagent runs on the
  model of the session.
- Give file paths and the scope, not copied file content.
- You own the subagent's work. Read its diff and write your own summary. Its report is a claim,
  not a result.
- A retry or a fix round goes to a new subagent. Give it the original scope, each later
  instruction, the report of the previous subagent and the failure by name. Continue an old
  subagent only when it holds state that is costly to move: uncommitted changes or a process
  that still runs.
- One subagent works on one scope at a time. When you run more than one (`arena.md`), give each
  its own Git worktree so they share no files.
