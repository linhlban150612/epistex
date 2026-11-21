# Arena

Taken from the pstack `arena` skill. Use it only when `architect.md` sends you
here: one attempt at a large or contested shape can fix the wrong design.

1. **Frame.** State the artifact that each candidate makes. Write 3 to 6 criteria that you can
   grade for this task. The candidates see the task, not the criteria.
2. **Fan out.** Spawn 2 or 3 subagents in one message (`subagents.md`), each in its own Git
   worktree, each with the same task. Each returns the artifact and a short rationale: the
   alternatives it considered and what it rejected. When a candidate returns nothing, continue
   with the others and say so.
3. **Pick a base.** Read each candidate from start to end. Grade each criterion; do not grade by
   general impression. Use the candidate that a later maintainer can extend most easily without
   breaking an invariant. On a tie, use the smaller interface.
4. **Graft.** Read each losing candidate one more time for the one or two parts worth moving into
   the base. Write each part into the base by hand so the result has one design. When the
   candidates agree on one shape, use it. When they differ widely, the frame was not specific:
   frame again and run again.
5. **Verify.** Verify the result as any other change: `setup/verify`, and a run of the changed
   path. A defect that the arena missed means a wrong frame or a missed graft; go back to that
   step.

Report the base and the reason, each graft with its source, what you rejected, the candidates
that returned nothing and the verification output. Remove the worktrees of the candidates.
