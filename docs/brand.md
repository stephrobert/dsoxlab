# The mark

**Language:** [English](./brand.md) · [Français](./brand.fr.md)

![dsoxlab](assets/brand/dsoxlab-lockup-light.svg)

A flask, and a prompt inside it. The flask is the lab: something declared,
prepared, thrown away and prepared again. The prompt is what actually runs in
it. Two shapes, one idea, and it is the project's whole argument drawn rather
than written: a lab is not a document you read, it is an environment that
executes and that something checks.

The wordmark splits `dsox` from `lab` in colour. `dsoxlab` is not a word anyone
has seen before, and seven glyphs in one ink read as a blur; the break gives the
eye the two halves it needs.

## What was deliberately left out

An earlier proposal drew the flask surrounded by servers, a code editor, a
container cube and rising bubbles, in gradients with a drop shadow, over a
spaced-out `DEVOPS TRAINING, EXECUTED` baseline. None of it survived, for
reasons worth recording so they are not reintroduced.

**Five subjects is four too many.** That sheet proved it against itself: its own
favicons kept the flask and dropped everything else. Servers, editor and cube
only existed at a size nobody ever sees the logo at.

**Gradients, shadows and highlights do not survive anything.** Not single ink,
not print, not 16 pixels. On that sheet's own black version, the `>_` vanished,
and the `>_` is the only part carrying meaning.

**A baseline you cannot read signs nothing.** In thin, widely tracked capitals
it had already turned to grey mush on the horizontal variant, at a size where
the logo is still large.

What was kept is what was good: the flask with a prompt in it, and the two-tone
split of the name.

## Files

Everything is in [`assets/brand/`](assets/brand/). **The SVG files are the
source**; the PNG files derive from them and are regenerated, never edited.

| File | Use |
|---|---|
| `dsoxlab-lockup-light.svg` | the default, on light backgrounds |
| `dsoxlab-lockup-dark.svg` | on dark backgrounds; the blue lifts, it is not the same blue |
| `dsoxlab-lockup-mono.svg` | single ink, inherits `currentColor` |
| `dsoxlab-icon.svg` / `dsoxlab-icon-dark.svg` | the mark alone, from 24px up |
| `dsoxlab-icon-mono.svg` | the mark alone, single ink, for favicons and terminals |


### PNG, for what does not take vectors

[`assets/brand/png/`](assets/brand/png/) holds rasterised versions for the
places that refuse SVG: GitHub's social preview, a slide, a platform thumbnail,
a README rendered by a tool without SVG support.

| File | Size | Use |
|---|---|---|
| `dsoxlab-icon-256/512/1024.png` | square, transparent | avatars, thumbnails, packaging |
| `dsoxlab-icon-dark-512/1024.png` | square, transparent | the same, on dark backgrounds |
| `dsoxlab-lockup-light-1024/2048.png` | 1024×215, 2048×429 | slides, articles |
| `dsoxlab-lockup-dark-1024/2048.png` | idem | the same, on dark backgrounds |
| `dsoxlab-social-preview.png` | 1280×640 | GitHub Settings → Social preview |
| `dsoxlab-social-preview-dark.png` | 1280×640 | the same, dark variant |

Regenerate them with `python3 scripts/generer-png-marque.py` rather than
exporting by hand. The script rasterises **at the target resolution** through
`-density`: `convert file.svg -resize 1024x` would rasterise at the 48-pixel
viewBox first and then enlarge that bitmap, which is blurry and obvious at 100%.

## How it is embedded, and why that way

GitHub switches on the reader's theme through `<picture>`, which is the
supported mechanism:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/dsoxlab-lockup-dark.svg">
  <img src="docs/assets/brand/dsoxlab-lockup-light.svg" alt="dsoxlab" width="240">
</picture>
```

**The wordmark is outlines, not text**, and that is what makes this safe. An SVG
carrying `<text font-family="Poppins">` renders in whatever the reader's browser
happens to have — Helvetica, Arial, DejaVu — because GitHub serves it no
webfont, and a lockup set in the wrong grotesque reads as a mistake. The seven
glyphs are Poppins SemiBold converted to curves, so the file is self-contained:
the same rendering on GitHub, in a slide, in a PDF, on a machine that has never
heard of the typeface.

Poppins is under the SIL Open Font License. Only these seven glyph shapes travel
in this repository, never the font.

## Using it

- **Clear space**: the height of the flask's neck on every side. Nothing enters it.
- **Smallest sizes**: 24px for the lockup, 20px for the icon. Below that the
  `>_` closes up and only the flask survives, which is still recognisable but no
  longer says what the mark means.
- **The prompt is thinner than the flask**, on purpose: the container and what
  runs in it do not carry the same weight. Redrawing both at the same stroke
  width flattens the mark.
- **On dark backgrounds, use the dark file.** `#2563EB` is crisp on white and
  closes up on navy, which is why there are two.

Do not recolour the mark to a single ink except through `dsoxlab-*-mono.svg`, do
not separate the flask from the prompt, do not set the wordmark in another
typeface, do not add a baseline, and do not add effects: a shadow on a
three-stroke mark reads as a rendering bug.

## Editing it

The geometry is constrained by two clearances that are computed rather than
eyeballed, and the first draft violated both:

- at `y=27` the left wall of the flask occupies up to `x=17.1`, so the chevron
  starts at `x=20`;
- the base occupies from `y=39` down, so the underscore sits at `y=35` and no
  lower.

Move either shape by hand and the mark starts touching itself, which is exactly
what the first version did. **Regenerate the wordmark rather than retyping it**:
the curves come from Poppins SemiBold through fontTools and are not editable as
text. The icon files carry no text at all and can be edited directly.

## Two things this repository cannot version

- **The social preview setting.** The image itself is versioned, at
  `assets/brand/png/dsoxlab-social-preview.png`; what cannot be is the setting
  that points GitHub at it. Upload it by hand: Settings → Social preview.
- **The account avatar**, which GitHub takes from the owner, not the repository.

## Licence

**The name *dsoxlab* and the logo are not covered by the Apache 2.0 licence**
that covers the code. They may be used to refer to this project — in an article,
a talk, a comparison, a list of tools — without asking. They may not be used as
the mark of a fork, a product or a service, or in a way that suggests the
project endorses something it does not.

This is the ordinary split for an open-source project, and it is stated here
because a reader who wants to do the right thing should not have to guess.
