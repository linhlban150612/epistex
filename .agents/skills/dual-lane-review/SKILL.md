---
name: dual-lane-review
description: Independent two-lane review for complex or review-class tasks. Use when the Lead needs two read-only Peers from different model families to review the same frozen candidate blindly, then reconcile shared findings and divergences.
---

# Dual-Lane review

Two independent lanes review one frozen candidate so one reviewer's blind spot is caught by
the other.

## The rule

**The two Peers must belong to two different model families.** That is the only selection
rule; its purpose is independent judgment between the lanes. Unknown or ambiguous family
identity counts as the same family. No valid pair → report `BLOCKED`; never run one lane.

## When to use

- The task is classed **complex / review**: a large or cross-cutting candidate, a security- or
  lifecycle-sensitive change, or a review whose conclusion drives a hard-to-reverse decision.
- Creating the two Peers needs agent-creation authority: an implementation request covers it;
  a read-only review request needs explicit Human authorization — otherwise propose it.

## Steps

1. Open two read-only Peers (Architect or Scout) from different model families. Record each
   lane's model ID and family evidence.
2. Send both the same neutral brief on the same frozen candidate. Neither brief mentions the
   other lane; neither Peer sees the other's output until both have handed back. The brief
   assigns the test lane.
3. Findings both lanes raised independently are **high-confidence**.
4. Divergences — raised by one lane only, or contradictory — go to **blind cross-critique**:
   send each Peer the other's divergent findings framed as third-party, naming task, round and
   candidate. **At most 2 rounds.**
5. The Lead is the final arbiter: record anything still divergent as an unresolved finding.
   No third Peer, no tie-breaker. Archive both Peers when done.

Dual-Lane does not replace the Human review gate.
