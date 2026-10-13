# ADR 007: Daily statistics and timezone snapshots

Status: Accepted

Daily learning statistics combine historical event facts with current study
state. The two groups deliberately use different data sources:

- Today's learned count is the number of distinct `LearningEvent.term_key`
  values whose stored `activity_date` equals today's date.
- A streak is calculated from distinct stored event activity dates. Today is
  the starting date when active; otherwise yesterday is the starting date.
- Due reviews count current `ReviewState` rows joined to existing `Entry` rows
  where `next_review_at <= now`.
- Total entries count current `Entry` rows.

When an outcome is accepted, the service reads the singleton
`AppSetting.timezone` in the same transaction as the event write. It converts
the accepted `occurred_at` instant to that IANA timezone and stores both the
timezone name and resulting local `activity_date` on the event. A later
settings change affects only new events. Historical dates are never
recalculated.

Today's date is calculated using the current database setting. This means a
timezone change can select a different current date, while every event remains
assigned to the date captured when it was written.

Vocabulary filtering follows the same split. Historical metrics filter by the
vocabulary id in `LearningEvent.vocabulary_snapshot`; live metrics filter
existing entries. A deleted vocabulary id remains a valid statistics filter:
historical learned counts and streaks remain available, while due reviews and
total entries are zero. The web selector lists only existing vocabularies.

All instants are compared in UTC. Natural-day boundaries, including daylight
saving transitions, are delegated to the standard IANA timezone database.
