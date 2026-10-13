# Demo Walkthrough

This walkthrough exercises the complete acceptance path in a mobile-width
browser.

## Sample Data

Open `/vocabularies/import`, keep the paste tab selected, enter the vocabulary
name `Travel essentials`, and paste:

```text
term|meaning|type|pos|phonetic|example|tags
itinerary|行程|word|noun|/aɪˈtɪnəreri/|Our itinerary starts tomorrow.|travel
check in|办理入住|phrase|||We need to check in before six.|hotel
carry-on|随身行李|word|noun|/ˈkæri ɒn/|Keep medicine in your carry-on.|airport
in order to|为了|phrase|||Leave early in order to avoid traffic.|travel
```

Select **解析预览**, review the accepted rows, and select **确认导入**.

## Configure

From the vocabulary detail page:

1. Open **配置陪读计划**.
2. Set daily new words to `4`.
3. Set daily reviews to `10`.
4. Set automatic switching to `5` seconds.
5. Save the plan.

## Study

Select **开始陪读**. The player shows the term, meaning, example, position, and
speech status.

- **暂停/继续** preserves the remaining interval.
- **重来** records `again` and schedules the item three positions later, or at
  the end when fewer positions remain.
- **上一个** reviews display history without moving persisted progress back.
- **下一个** records `seen` and advances.
- **结束** flushes pending results before returning to the vocabulary.

Speech failures switch the player to silent mode without stopping automatic
progress.

![Mobile study player](assets/mobile-study.png)

## Verify Statistics

Open `/statistics` and select `Travel essentials`. Confirm:

- today's learned count is distinct by normalized term;
- both `seen` and `again` count as learned;
- due reviews reflect current review state;
- the streak uses the configured timezone;
- total entries reflects the current non-deleted vocabulary.

The automated version of this path is
`tests/e2e/test_vocabulary_import.py::test_mobile_study_player_full_flow`.
