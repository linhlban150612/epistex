# Supervisor → Lead initial prompt

Use this template for a Human-authorized `create_agent(..., initialPrompt=...)`.
Fill it from the Human's request and inspected evidence; mark unknowns rather than inventing
constraints. This is startup context, not a Peer assignment or authority to create a Lead.
Discover workspace/provider/model/agent IDs through Paseo. Include the filled block in the
initial prompt, not just a link: the Supervisor's empty workspace need not hold project files.

```text
Project / repository / Paseo workspace: <verified identity>
Request type and authorized work: <read-only or implementation; explicit limits>

Outcome
- <observable behavior or result, not a preferred implementation>
- Done when: <observable acceptance check; mark unverified commands as proposed>

Verified constraints
- <binding constraint> | Source: <contract or inspected evidence> | May change: <authority>
- <fact checked> | Evidence: <path/lines or command and actual result>

Open assumptions
- <unverified claim> | How to check: <bounded investigation> | Impact if false: <affected work>
- <unresolved question; use unknown, not an invented answer>

Decided & who may reopen
- <current decision> | Rationale/evidence: <basis> | Decision owner: <Human or Lead>
  Reconsideration trigger: <new evidence or changed requirement>
  May revise: <Lead within delegated authority, or Human decision required>
- <if none, say none; do not turn a proposed mechanism into a binding requirement>

Coordination
- Read the project's AGENTS.md and WORKSPACE_PROTOCOL.md; reconcile conflicts before delegation.
- For REOPEN_REQUEST or DEPENDENCY_REQUEST, use the handling-reopen skill
  (.agents/skills/handling-reopen/SKILL.md); if unavailable, request the procedure before proceeding.
- Keep decision provenance here for authority resolution. Write neutral Peer briefs with
  reasons/evidence, without relaying Human quotes or using provenance to bias the Peer.

Your Supervisor agent ID is <this agent's agentId>. Ask the Supervisor questions with send_agent_prompt(<agentId>, ...).
```

Replace both routing placeholders with the actual Supervisor ID. Human-owned decisions require
an explicit Human answer, relayed by the Supervisor or given directly; the Supervisor does not
decide them. Open assumptions are investigation inputs, never silently promoted to MUST HOLD.
For projects using this template, make the `handling-reopen` skill available with the project
skills. Its procedure is also reachable through `examples/WORKSPACE_PROTOCOL.md`.
