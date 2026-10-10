# ADR 004: Event-local activity dates

Status: Accepted

Each learning event stores UTC client time, server receipt time, the active
IANA timezone, and the derived local activity date.

Changing application timezone affects new events only. Historical daily
statistics and streaks are not retroactively regrouped, making reports stable
and tests deterministic.
