# Formula Reconstruction

Use this reference when a page contains formulas.

## Inputs

Use the page-local files:

- `pages/page-XXX/page.png`: primary visual source.
- `pages/page-XXX/page.pdf`: exact PDF page if needed.
- `pages/page-XXX/task.md`: page instructions.
- `pages/page-XXX/page.md`: Markdown output to edit.

Do not rely on extracted PDF text for formula structure. The helper script no longer extracts or detects equations.

## Markdown Output

Write Pandoc-compatible LaTeX math directly in `page.md`.

Inline formula example:

```markdown
The predictor is $r_{13,t}$.
```

Display formula example:

```markdown
$$
r_{13,t} = \alpha + \beta r_{1,t} + \epsilon_t
$$
```

## Rules

- Use inline `$...$` and display `$$...$$` math.
- Do not define custom LaTeX macros; write formulas using standard LaTeX commands.
- Preserve subscripts, superscripts, fractions, summation/product limits, roots, hats, bars, tildes, primes, matrices, cases, and alignment from the image.
- Keep equation numbers as regular text beside or near the display formula when practical.
- Use standard LaTeX structures such as `\frac`, `\sum`, `\prod`, `\sqrt`, `\hat`, `\bar`, `\tilde`, `\begin{matrix}`, `\begin{pmatrix}`, `\begin{cases}`, and `\begin{aligned}`.
- If the image is ambiguous, write the best partial LaTeX and add `<!-- REVIEW: formula uncertainty on page XXX: ... -->`.
- If standard LaTeX cannot represent the visual structure faithfully, add `<!-- REVIEW: formula difficult on page XXX: ... -->` and explain what is difficult.

## Validation

Well-formed LaTeX is not enough; compare the rendered formula structure against the page image before marking the page complete.
