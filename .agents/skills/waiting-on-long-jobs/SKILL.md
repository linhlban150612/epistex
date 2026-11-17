---
name: waiting-on-long-jobs
description: Peer procedure for a command that can run longer than one tool call, such as a build, test suite, benchmark, training run, migration or deploy. Use before starting such a job, and before ending a turn while a process you started is still running.
compatibility: Requires nohup, pkill and GNU coreutils tail (`tail --pid`); BSD and macOS tail do not have it.
---

# Waiting on long jobs

The end of your turn is your handoff: the delivery plugin sends your last message to the Lead, and
nothing wakes you when a background job finishes. A turn that ends with "the job is running, I will
report when it is done" leaves the Lead with no result and no event to wait for. So a job is
either finished inside the turn, or handed over with what the Lead needs to follow it.

Paseo can list an agent's background tasks above the composer and keep the agent marked Running.
That indicator is for the Human. It does not keep your turn open and it sends nothing to the Lead
when the job ends, so it does not replace the wait or the handoff below.

## Start the job so it can be followed

Start it detached, with its output in a file and its exit code in a second file, and record the
PID:

```bash
nohup sh -c '<command>; echo $? > <log>.exit' > <log> 2>&1 & echo $!
```

Put the log outside tracked files. Do not start a second copy to see more output; read the log.

Use this form, not the backend's own background feature (a `run_in_background` shell, a monitor, a
background terminal). The native feature gives no PID, log path and exit-code file that the Lead
can read from outside your session, and its completion can start a turn the Lead did not ask for.

## Wait inside the turn

Block on the job with a command, not with a sleep loop of your own design and not with a timer,
schedule or heartbeat:

```bash
tail --pid=<pid> -f /dev/null    # returns when the process exits
```

If your shell tool has a time limit per call, repeat the blocking call; each call is one wait, and
the turn stays open. Between calls, read the tail of the log and stop the job when it has clearly
failed. The PID is the `sh` wrapper's: stop the job with `pkill -P <pid>`, which ends the command
and lets the wrapper write the exit code. `kill <pid>` ends only the wrapper and leaves the command
running.

When the process exits, read `<log>.exit` and the log before you report: an exit is not a pass,
and a missing `<log>.exit` means the wrapper was killed, not that the job passed.

## When the job cannot finish in the turn

Use this only when the wait is longer than your turn can hold, or the brief gives a time limit.
Return the six-cell handoff with `Outcome: partial` and put in it:

- the exact command, the PID and the host it runs on;
- the absolute log path and its last lines, and that the exit code will be in `<log>.exit`;
- what result means pass and what means fail;
- in `Ownership`: that the process is still running and still yours.

Do not report the job's result as a fact before it exists, and do not release ownership while your
process runs. The Lead decides the next round; you do not schedule your own return.

## Before any handoff

Check every PID you recorded with `kill -0 <pid>`: exit 0 means the process still runs. A detached
job is not a child of your current shell, so a child-process listing does not show it. Each process
you started is finished, stopped by you, or listed in the handoff as above.
