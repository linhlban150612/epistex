# Architect

Taken from the pstack `architect` skill.

Before you write code, trace each part of the kit that the change touches. Then sketch two
different shapes for it: types, signatures and module boundaries. Use the shape where each piece
of state has one owner, each task has one way to do it, and a caller must know least. When the
same workaround occurs again, redesign; do not patch.

For a large or contested design, do not sketch alone: use `arena.md`.
