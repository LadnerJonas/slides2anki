```json
{
  "source": "<slide file path as given>",
  "source_hash": "<hash as given>",
  "cards": [
$examples
  ]
}
```

Fields:
- `id`: short kebab-case slug, unique within the file and stable: keep the id when you only reword a card.
- `type`: one of $types.
- `question`: one focused question, understandable without the slides.
- `options` (single/multi): 3 to 6 options, labelled A, B, C, … in order.
- `correct`: a letter for `single`, a list of letters for `multi`.
- `answer` (open): the expected answer, concise but complete.
- `explanation`: why the answer is right; for choice cards also why the main distractors are wrong.
- `pages`: the slide pages (1-based) the card is based on.
- `figure` (optional): one page number whose slide image is shown on the answer side.
- `tags` (optional): list of strings.
