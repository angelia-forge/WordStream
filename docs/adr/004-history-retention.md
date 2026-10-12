# ADR 004: Retain learning history after vocabulary deletion

Status: Accepted

Deleting a vocabulary removes the vocabulary, its entries, its study plan, and
the entries' review states in one service transaction. Database foreign keys
enforce the deletion graph:

- `StudyPlan.vocabulary_id` uses `ON DELETE CASCADE`.
- `Entry.vocabulary_id` uses `ON DELETE CASCADE`.
- `ReviewState.entry_id` uses `ON DELETE CASCADE`.
- `LearningEvent.entry_id` uses `ON DELETE SET NULL`.

Learning events are historical facts and remain after their source vocabulary
is deleted. Each event stores the term key, displayed term, vocabulary id,
vocabulary name, timezone, and local activity date as immutable snapshots.
Statistics and streak calculations read these event fields only; they never
join through the nullable entry reference.

This preserves historical totals and streaks while allowing the active study
state to be removed completely. Restoring deleted vocabularies, bulk deletion,
and user ownership are outside this decision.
