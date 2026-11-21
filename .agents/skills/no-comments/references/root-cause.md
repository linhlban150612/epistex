# Root cause and redesign

Taken from the pstack `principle-fix-root-causes` and `principle-redesign-from-first-principles`
skills. They guide the fix. They do not permit a change outside the scope.

## Fix the root cause

Fix the fault, not the place where it showed. The root cause is the first place where the code
did something it must not do, or did not handle a state it must handle.

- Reproduce first. Ask "why" until the answer is a wrong decision in the code.
- Ask if the state behind the symptom is legitimate. If it is, handle it where the code broke. If
  it must not exist, a check there hides the bug: find what made the state. Guards, retries,
  swallowed errors, clamped values and discarded state are the usual ways to hide a bug.
- Fix the pattern. Find each place inside the scope with the same fault; report the places
  outside it.

## Redesign

Do not attach the change to the existing design. Design as if the requirement was there from the
start.

- Read each affected file and understand the current design.
- Ask what you would build from an empty file with this requirement.
- Carry the change through each reference: types, documents, examples.
