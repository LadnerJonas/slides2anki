# Card task: $source

Write `$card_path` for the slide file `$source` in the lecture folder ($page_count pages). Read only this task file and the page images it names; do not open the PDF.
$previous
## Course
$course

## Output format
$card_format
Use exactly `"source": "$source"` and `"source_hash": "$source_hash"`.

## How to write good cards
- Cover every exam-relevant concept, definition, distinction, algorithm, proof idea or argument exactly once. No padding, no trivia (slide numbers, logistics, dates), no duplicates.
- Each card tests one idea and is understandable without the slides.
- Prefer understanding and application over verbatim recall.
$type_rules
- Set `figure` only when a diagram, plot, table or formula layout genuinely helps on the answer side.
- Formatting: Markdown (`**bold**`, `*italic*`, `` `code` ``, fenced code blocks, lists). Math: `\( … \)` inline and `\[ … \]` display; double the backslashes inside JSON strings.
$extra
## Finish
Run `slides2anki validate $card_path` and fix every reported issue until it passes.

## Slides
$material
