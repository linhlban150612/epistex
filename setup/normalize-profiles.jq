# Run with --argjson catalog true for the backend catalog, false for live config.
# Only Epistex role profiles are normalized; provider definitions and state are untouched.
def epistex_role:
  .provider | capture("^(codex|claude|amp|agy|pi|omp|copilot|cursor|kiro|droid|devin)-(?<role>lead|peer|supervisor)$") | .role;

.agents.providers as $providers |
.daemon.agentProfiles |= map(
  . as $profile |
  ((try epistex_role catch null) // null) as $role |
  if $role == null then .
  elif ($catalog | not) and $providers[.provider].enabled == false then empty
  else
    .notes = (
      (if $role == "supervisor" then
         "Supervisor: observe Leads, clarify intent and support the Human. Do not implement, assign Peers or review/accept candidates."
       elif $role == "lead" then
         "Lead: frame scope, coordinate Peers, review evidence and accept work. Do not write project artifacts. Do not automatically create Peers on the Lead's backend provider; use Human-authorized alternatives or report BLOCKED."
       else
         "Peer: implement the assigned scope, verify results and hand off evidence. Do not delegate or accept project work."
       end) +
      (if $profile.thinkingOptionId != null then
         " Thinking setting: " + $profile.thinkingOptionId + "."
       else "" end) +
      " Model names and effort settings are not evidence of cost or speed. Before delegation, confirm project authorization and provider availability. Materialize provider/model as create_agent.provider; if model is absent, discover it with list_models first. Copy modeId to settings.modeId, thinkingOptionId to settings.thinkingOptionId, and featureValues to settings.features. Omit absent optional settings; never infer them. Supply the task in initialPrompt."
    )
  end
)
