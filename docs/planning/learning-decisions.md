# Learning Decisions Reserved for Later Stages

These accepted product decisions are retained for future implementation and do
not authorize business code in Stage 0.

## Binary Leitner outcomes

Automatic read-along records `seen` by default and lets the learner select
`again`. The review intervals are 1, 3, 7, 14, and 30 days.

Retries reuse the same session item at the queue tail. Attempts accumulate,
but each session item creates one final learning event. Each presentation has
a unique attempt id; the server deduplicates those ids and derives the attempt
count.

## Event-local activity dates

Each learning event stores UTC client time, server receipt time, the active
IANA timezone, and the derived local activity date.

Changing application timezone affects new events only. Historical daily
statistics and streaks are not retroactively regrouped.
