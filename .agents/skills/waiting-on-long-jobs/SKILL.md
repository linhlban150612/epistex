---
name: waiting-on-long-jobs
description: Peer procedure for a command that can run longer than one tool call, such as a build, test suite, benchmark, training run, migration or deploy. Use before starting such a job, and before ending a turn while a process you started is still running.
compatibility: Requires nohup and GNU coreutils tail (`tail --pid`); BSD and macOS tail do not have it.
---

# Waiting on long jobs

The end of your turn is your handoff: the delivery plugin sends your last message to the Lead, and
nothing wakes you when a background job finishes. A turn that ends with "the job is running, I will
report when it is done" leaves the Lead with no result and no event to wait for. So a job is
either finished inside the turn, or handed over with what the Lead needs to follow it.

## Start the job so it can be followed

Start it detached, with its output in a file, and record the PID:

```bash
nohup <command> > <log> 2>&1 & echo $!
```

Put the log outside tracked files. Do not start a second copy to see more output; read the log.

## Wait inside the turn

Block on the job with a command, not with a sleep loop of your own design and not with a timer,
schedule or heartbeat:

```bash
tail --pid=<pid> -f /dev/null    # returns when the process exits
```

If your shell tool has a time limit per call, repeat the blocking call; each call is one wait, and
the turn stays open. Between calls, read the tail of the log and stop the job when it has clearly
failed. When the process exits, read the exit status and the log before you report: an exit is not
a pass.

## When the job cannot finish in the turn

Use this only when the wait is longer than your turn can hold, or the brief gives a time limit.
Return the six-cell handoff with `Outcome: partial` and put in it:

- the exact command, the PID and the host it runs on;
- the absolute log path and its last lines;
- what result means pass and what means fail;
- in `Ownership`: that the process is still running and still yours.

Do not report the job's result as a fact before it exists, and do not release ownership while your
process runs. The Lead decides the next round; you do not schedule your own return.

## Before any handoff

Check every PID you recorded with `kill -0 <pid>`: exit 0 means the process still runs. A detached
job is not a child of your current shell, so a child-process listing does not show it. Each process
you started is finished, stopped by you, or listed in the handoff as above.
