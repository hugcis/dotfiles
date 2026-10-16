---
name: vetting-measured-results
description: Use when about to report, compare, or act on a number you measured, such as a speedup, regression, throughput, latency, job ETA, or eval score, and before claiming one model, config, or change beats another.
---

# Vetting Measured Results

A number is not a result until you can say what limits it and have ruled out that it
measured something other than the work. Answer each question with evidence from a run,
not from reading the code.

For a quick ballpark the user asked for, one run is enough. Still check questions 4 and 7
and say that it is one run. A choice between options is never a ballpark.

## Before running

- Write the claim you expect to make, in the words you would report: "checkpoint B
  solves 12 points more tasks than A on the 400-task suite", "the loader is 30% faster
  at p50". The questions test that sentence.
- Read the measurement script or eval config. Note what it times, counts, and skips.
- Check what else shares the machine or allocation. If you cannot remove the noise,
  interleave the sides so both see it, and say so.

## The questions

1. **Why not double?** Name the limiter: a core, a lock, I/O, the network, the queue,
   the load generator, or the simulator. Get it from a profile or system counters taken
   during a run you do not report, then map it to source. For job timing, separate
   queue wait, startup, compute, and I/O before blaming any one of them.
2. **Was each side tuned?** Run every side the way production runs it: same flags,
   batch sizes, caches, versions, data, decoding settings, and prompt format. If one side
   runs on defaults, you compared configurations, not implementations.
3. **Does it break a limit?** Do the arithmetic against bandwidth, cores, and the time
   the changed piece took. Removing a piece that takes 10% of the run can make it at most
   about 11% faster. A result past a limit measured a cache, a no-op, or a bug.
4. **Did anything error?** Count failures, timeouts, retries, skipped samples, and
   unparsable outputs, and check outputs are correct, not just present. State the
   denominator: an eval score over completed episodes is not a score over the suite.
5. **Does it reproduce?** Run each side several times, alternating A and B, and report
   the median and range. For evals, report the sample count and the spread across seeds
   or episodes. A gap smaller than the run-to-run spread is no measurable difference.
6. **Does it matter end to end?** Report a micro result as a share of the path a user
   waits on, at realistic sizes and concurrency.
7. **Did the work happen?** Confirm the timed region did the work: the request reached
   the server, the model ran on the intended checkpoint, the rows were written, the
   result was used. Lazy code, cached responses, and smoke configurations produce
   numbers for work that never ran.

## Report

- Lead with the verdict: better, worse, no measurable difference, or inconclusive.
- Give the number with its unit, run or sample count, range, denominator, and limiter.
- Call it inconclusive when you cannot name the limiter, a side ran untuned, or you could
  not check questions 4 and 7. Name the gap.
- Name exactly what was measured: commit, checkpoint, config, suite, and whether it was a
  smoke or a full run.

Adapted from pstack `benchmark-checklist` and `principle-explain-the-number` (MIT, Lauren Tan).
