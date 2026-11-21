---
name: benchmark-checklist
description: Peer procedure to vet a number you measured before you report it or act on it, such as a benchmark, speedup, regression, throughput, latency or eval result. Use before you run the measurement, and before you write the number in a handoff.
---

# Benchmark checklist

A number in a handoff is a claim. The Lead accepts it only when the handoff shows what limits the
number and that it measured the work. Answer each question with evidence from a run, not with a
guess from the code.

Run only the commands that the brief authorizes (`PEER.md` §Verification). When a question needs
a run that the brief does not authorize, do not run it: report the question as `not checked` and
name the command you need. A measurement that can outlast one tool call follows the
`waiting-on-long-jobs` skill.

## Before you run

- Write the claim you expect to make, in the words of the handoff: "export is 30% faster at p50
  on the 60k-row dataset". Write the decision that the number changes and the result that would
  change it. The questions test that sentence.
- Read the measurement script. Note what it times, what it counts and what it ignores.
- Check the machine: `uptime` for the load average, `nproc` for the core count. On a busy machine,
  alternate the sides so both see the same noise, and say so in the report.

## The questions

1. **Why not double?** Name the limiter: the resource or code path that bounds the result. Take
   it from a profile or from counters of a run that you do not report, because a profiler slows
   the work. A guess from the code is not a limiter. Watch the load generator too: if it
   saturates first, you measured the load generator. When a change did not move the number, find
   the limiter before you call the change useless.
2. **Was it tuned?** Run each side as production runs it: release build, production flags and
   environment, batching, connection pools, caches as warm or cold as production, the same
   versions and data. If one side runs on defaults, you compared configurations. A limiter that
   is a setting (a commit per row, a debug build, a missing index) means that side is untuned:
   do not pick a winner from that run.
3. **Did it break a limit?** Do the arithmetic. Compare bytes per second with disk and network
   bandwidth, operations per second with the cores, and the time saved with the time the changed
   piece took. A piece that takes 10% of the run can make the run at most about 11% faster. A
   result past a limit measured a cache, a no-op or a bug.
4. **Did it error?** Count failures and non-success results, and check that the outputs are
   correct, not only present. A rejection is often fast; a timeout or retry is slow. If the
   script does not count errors, report that as a gap; add the count only when the script is in
   your owned scope.
5. **Does it reproduce?** Run each side at least 5 times, alternating (A, B, A, B). Report the
   median and the range. A gap smaller than the run-to-run variation is no measurable difference.
6. **Does it matter?** Next to a micro result, measure the end-to-end path that a user waits on,
   with realistic data and concurrency, and give the micro result as a share of the whole.
7. **Did it even happen?** Confirm that the work ran inside the timed region: the request reached
   the server, the rows were written, the bytes were read, the result was used. Lazy code,
   skipped work and timeouts give numbers for work that did not happen.

For an eval result, questions 4, 5 and 7 become: did each run do the task, does the gap hold
across trials and models, and does the scenario matter.

When the brief asks only for a ballpark, one run is enough. Still answer questions 4 and 7, and
say that it is one run. A choice between options is never a ballpark.

## Report

Put this in the `Verification` cell of the handoff, with the commands and their real output:

- The verdict first: `faster`, `slower`, `no measurable difference` or `inconclusive`.
- The number with its unit, the run count, the range and the limiter: "p50 41 ms → 33 ms, median
  of 7 runs per side, range 32 to 35 ms after, bound by JSON parsing on one core".
- One line for each question: the evidence, or `not checked` with the reason.

The verdict is `inconclusive` when you claim a difference but cannot name the limiter, when one
side ran untuned, or when question 4 or 7 is `not checked`. Name the gap in `Unknown / risk`.
