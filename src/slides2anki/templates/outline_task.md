# Outline task

$action `outline.toml`: group the slide files into topics. Each topic becomes the Anki subdeck "$course::NN Title", numbered in list order.

```toml
[[topics]]
title = "Introduction"
files = ["Lectures/01_intro.pdf"]

[[topics]]
title = "Sorting Algorithms"
files = ["Lectures/02_sorting.pdf", "Lectures/03_sorting_continued.pdf", "Exercises/sheet02.pdf"]
```

Rules:
- Every file listed under "Files" must appear in exactly one topic, spelled exactly as given (paths are relative to the lecture folder).
- Folder and file names often reveal the structure (`Week 03/`, `Chapter 2`, `Lecture_05`). Material that is not a lecture (exercise sheets, solutions, tutorials) goes into the topic of the lecture it belongs to.
$keep- Follow the topic structure of the course context (a saved course page, syllabus or module description) when there is one; otherwise derive topics from the slides. A topic often matches one lecture, but may span several files.
- Titles: short (2 to 6 words), in $language, without numbering.
$labels- If the user asked to review the outline first, show it and wait for confirmation before continuing with card tasks.

## Current outline
$current

## Course context
$context

## Files
$files
