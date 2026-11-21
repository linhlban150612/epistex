# Why

Taken from the pstack `why` skill.

Answer from the record, not from the code. Read the commit that introduced the target and each
later change to it:

- `git log -S '<text>' -- <path>` finds the commits that added or removed the text.
- `git log -L <start>,<end>:<path>` gives the history of a line range.
- `gh pr list --search <sha> --state merged` finds the pull request and its discussion.

Cite what the authors wrote. Mark your own inference as an inference. Say what the record does
not answer. When the record is thin, read the canonical documents that `AGENTS.md` lists.
