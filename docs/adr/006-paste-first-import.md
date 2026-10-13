# ADR 006: Paste-first vocabulary import

Status: Accepted

The primary import path is pasted delimited text because it works on desktop
and mobile without requiring file access. CSV and TSV uploads use the same
parser and validation pipeline.

Import is a two-step operation:

1. Preview parses headers, normalizes terms, reports row errors and duplicates,
   and returns a digest.
2. Confirm reparses the original input and requires the preview digest to
   match before writing the vocabulary and all accepted entries in one
   transaction.

The parser uses Python's CSV implementation so quoted delimiters, embedded
newlines, UTF-8 text, and an optional BOM are handled structurally. It rejects
missing required columns, empty accepted datasets, unsupported fields, and
inputs over the configured byte limit. Duplicate normalized terms are skipped
and reported rather than inserted.

Preview creates no persistent state. A failed confirmation rolls back the
whole import, so a vocabulary cannot be left partially populated.
