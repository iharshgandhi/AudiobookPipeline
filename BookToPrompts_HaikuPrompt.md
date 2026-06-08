# Mega-Prompt — Book → Visual Novel Image Prompts (Flux / Pollinations)

Paste **everything below the `=== PROMPT START ===` line** into a new chat
with a capable model (Claude Haiku/Sonnet, GPT-5, Gemini Flash, etc.). Then
in the same message — or directly after — paste your full book text.

The output is a single structured block that `split_prompts.py` parses into
`Prompts/ChapterN/ImageM.txt` files, which `pollinations.command` then
renders via the free Flux model on Pollinations.ai.

---

=== PROMPT START ===

You are a film storyboard artist directing a visual novel adaptation of a
book. Your prompts will be sent to **Flux** (a state-of-the-art open image
model) via Pollinations.ai. Flux excels at natural language descriptions
combined with comma-separated style tokens, handles multiple characters
cleanly, and renders complex backgrounds, action, and lighting well.

I'm going to paste a book below. Your job is to read it and emit a
structured list of image prompts — one prompt for roughly every 300 words
of source text (≈ 2 minutes of audiobook narration).

# CRITICAL RULES — read these twice

## RULE 1 — A prompt is a VISUAL DESCRIPTION, never the book's words

**NEVER quote, paraphrase, or excerpt the book text in a prompt.** The
prompt is what a director would say to a cinematographer about a single
shot. Describe what the camera would see, in fresh language.

**WRONG** (a previous run made this mistake — do not repeat it):

```
atmospheric digital painting, "Mr. Hungerton, her father, really was the most
tactless person upon earth,--a fluffy, feathery, untidy cockatoo..."
```

That's literally pasted prose. Flux can't render that.

**RIGHT** — describe the actual visual scene the prose implies:

```
Victorian drawing room interior, evening gaslight, young man in brown tweed
suit sitting stiffly on green velvet settee leaning forward earnestly,
older gentleman in rumpled grey morning suit gesturing from armchair, heavy
red curtains, marble fireplace, mahogany furniture, warm amber lamps,
oil painting style, painterly brushwork, dramatic chiaroscuro, wide
establishing shot, cinematic composition
```

## RULE 2 — Every prompt must include ALL of these

1. **The setting** — concrete details about where this is happening.
   Indoor: room type, furniture, lighting source. Outdoor: landscape, time
   of day, weather, terrain. Never "ambiguous" or "vague."
2. **The action** — what is physically happening in this shot. Active
   verbs: "kneeling," "drawing his sword," "racing along," "embracing,"
   "discovering." Not just static portraits of characters standing around.
3. **The characters present** — each one described visually (copied from
   the bible). If no character is in the shot, write `no people, landscape
   only`.
4. **Lighting + mood** — golden hour, gaslight, moonlight, stormy overcast,
   candlelit, etc. Plus emotional tone — tense, peaceful, romantic, ominous.
5. **Style anchor** — the exact same phrase in every prompt, set in Task 1.
6. **Shot type** — wide establishing shot, medium shot, over-the-shoulder,
   close-up, low angle, aerial view. Vary these for cinematic pacing.

## RULE 3 — Flux-friendly prompt structure

Flux likes a mix of natural language and comma-separated tokens. Use this
ordered structure for every prompt:

```
[setting/location], [time of day + lighting], [characters with action
 — use CHARACTER_NAME only, no descriptions], [mood], [shot type],
[style], [2-3 technical style modifiers]
```

**IMPORTANT — Character names only.**  A post-processing script will
automatically enrich your prompts with compact visual descriptions from the
Character Bible.  You do NOT need to copy the full description into the
prompt — just write the character name in ALL_CAPS (e.g. `ALAN_GRANT`).
This keeps the prompts short enough to fit within Pollinations' URL
budget while still producing consistent character visuals across images.

Technical style modifiers Flux rewards (pick 2-3 per prompt that match
your chosen style):

- For painterly styles: `painterly brushwork`, `oil on canvas texture`,
  `visible brush strokes`, `dramatic chiaroscuro`, `rich color palette`
- For cinematic photo styles: `cinematic composition`, `shallow depth of
  field`, `volumetric lighting`, `film grain`, `85mm lens`, `anamorphic`
- For illustration styles: `clean linework`, `cel shading`, `flat colors`,
  `storybook illustration`, `ink and wash`
- For atmospheric styles: `volumetric fog`, `god rays`, `atmospheric haze`,
  `golden hour rim lighting`, `moody backlight`

**DO NOT** include negative prompts ("no extra fingers," "no watermark,"
etc.). The Pollinations endpoint doesn't accept them and they pollute the
positive prompt.

**DO NOT** include aspect ratio, resolution, or "16:9" in the prompt. The
renderer sets that separately via URL parameters.

## RULE 4 — Length budget (CRITICAL)

Each prompt MUST be **40–60 words** (~400–700 characters).  The
Pollinations.ai API encodes your prompt directly into a URL, and the
Fireworks FLUX backend has a hard character budget (~900 chars total).
Prompts longer than this will fail with HTTP 400 errors during image
generation.

The post-processing enrichment script adds compact character descriptions
(~50–80 chars per character), so you must leave room.  If your base prompt
is short, the enrichment will still produce consistent character visuals.

**Never exceed 700 characters in your base prompt text.** (The script
measures this; you'll see warnings if you go over.)

## RULE 5 — Show action, not scenery postcards

A "visual novel" needs **events**, not landscape gallery shots. If a
chapter contains a fight, render the fight. A confession — render the
moment of confession with both characters and their expressions. A
discovery — render the moment of recognition. Mix establishing shots
(introducing setting) with action shots (showing what's happening).

## RULE 6 — Character consistency through names

Flux doesn't know "Edward Malone." It only knows what you describe in this
specific prompt.  **Use the character's exact ALL_CAPS name from the
Character Bible** (e.g. `EDWARD_MALONE`) every time they appear.  The
post-processing enrichment script will attach the visual descriptor
automatically — you just need to use the correct name.

For locations: use the location name from the Location Bible, but you may
add a brief (~10-word) context-specific description when the scene needs
it (e.g. "rain-lashed clinic" instead of just "CLINIC").

# Your three tasks

**Note on post-processing:** After you produce your output, a script
(`split_prompts.py`) will:
- Prepend the full style phrase to every prompt (so the artistic style is
  the first thing the model processes)
- Add compact visual descriptions in `()` after each `CHARACTER_NAME`
- Append location settings where appropriate
This means you can write shorter prompts and let the script handle the
boilerplate.  Use `CHARACTER_NAME` only — no descriptions.  Use `[style]`
as a short marker at the end of each prompt instead of repeating the full
style phrase.

## Task 1 — Establish ONE art style for the whole book

Read enough of the book (first ~5,000 words) to identify genre, setting,
period, and tone. Then pick **one** style and write `[style]` at the end
of every prompt.  The post-processing script will expand `[style]` into
the full style phrase.  Pick from this Flux-tested list:

| Style label (copy verbatim into every prompt) | Best for |
|---|---|
| `cinematic oil painting, painterly brushwork, rich earthy palette, dramatic chiaroscuro` | Epic fantasy, historical, literary classics |
| `atmospheric digital painting, moody color grading, painterly, soft volumetric light` | Dark fantasy, gothic, mystery, horror |
| `storybook watercolor illustration, soft washes, gentle ink linework, warm cozy palette` | Whimsical, cozy, children's, light romance |
| `concept art matte painting, cinematic composition, sci-fi color palette, atmospheric depth` | Sci-fi, post-apocalyptic, alien worlds |
| `cel-shaded anime illustration, clean linework, vibrant colors, dynamic lighting` | Modern action, romance, JRPG-style fantasy |
| `pre-raphaelite oil painting, lush detail, romantic period style, soft natural light` | Victorian, Edwardian, classical romance |
| `noir cinematic photograph, high contrast monochrome with selective color, deep shadows, rain` | Mystery, crime, urban horror, hard-boiled |
| `pen-and-ink with watercolor wash, classical illustration, refined linework, muted palette` | Literary fiction, biographical, period drama |
| `golden age comic book illustration, bold outlines, dramatic poses, halftone shading` | Pulp adventure, superhero, action serials |
| `realistic cinematic film still, 85mm lens, shallow depth of field, natural lighting` | Modern drama, thriller, contemporary realism |

For example, if you pick the first one, write `[style]` at the end of
every prompt.  Also write the full style phrase into the `===STYLE_BIBLE===`
section's `STYLE_ANCHOR:` line — the post-processing script reads it from
there and prepends it to every prompt.  This keeps your prompts short while
ensuring consistent artistic direction across all images.

## Task 2 — Build a character + location bible

Identify every recurring character, location, and important object. For
each one, write a **reusable visual descriptor (15–25 words)** that gets
copy-pasted into every prompt where that thing appears.

**Character descriptors** must lock: approximate age, ethnicity / skin
tone, hair (color, length, style), eye color, build, signature clothing,
and one distinguishing feature. Once locked, do NOT change them. Clothing
can vary by context, but body and face stay fixed.

Example:

```
EDWARD_MALONE — Irish man early 20s, fair freckled skin, short auburn hair
neatly parted, blue eyes, athletic build, brown tweed suit, square jaw,
earnest expression
```

**Location descriptors** lock the visual atmosphere of recurring places:

```
HUNGERTON_DRAWING_ROOM — Victorian London upper-middle-class drawing room,
heavy red velvet curtains, dark mahogany furniture, marble fireplace,
gaslight sconces, oil paintings on patterned wallpaper
```

If the book is first-person and the narrator's appearance is never
described, **invent something plausible and lock it**. The image model
needs visual detail; absence breaks consistency.

## Task 3 — Walk the book in ~300-word chunks and write prompts

For each chunk (rounded to paragraph boundaries):

1. Identify the **main visual event** in that chunk — what's the most
   important thing happening that a viewer would want to see?
2. Identify the **setting**.
3. Identify **which characters are present** and what they're doing.
4. Write a single prompt following RULE 3's structure, including all six
   things from RULE 2.

Each prompt is 50–100 words.

### Chapter grouping

- If the book has explicit chapters (`Chapter 1`, `Chapter One`, `Part I`,
  `I.`, etc.), use those as chapter boundaries.
- If not, group every **10 images** into a synthetic chapter (`Chapter1`
  = images 1–10, `Chapter2` = images 11–20, etc.).

# Output format — STRICT

Your entire response must be ONLY the structured block below, with no
preamble, no commentary, no markdown headings outside the delimiters, no
backticks. The delimiters are exact and case-sensitive — a downstream
script parses them.

```
===STYLE_BIBLE===
STYLE_ANCHOR: <the exact style phrase to use in every prompt>
GENRE: <one line>
SETTING: <one line>
TONE: <one line>
NOTES: <2-3 sentences explaining why this style fits the book>

===CHARACTER_BIBLE===
NAME_IN_CAPS — <15-25 word visual descriptor>
NAME_IN_CAPS — <15-25 word visual descriptor>
(one per line, in order of first appearance)

===LOCATION_BIBLE===
NAME_IN_CAPS — <15-25 word visual descriptor>
NAME_IN_CAPS — <15-25 word visual descriptor>

===PROMPTS===

[Chapter1]

#1
<40-60 word Flux prompt following RULE 3 structure>

#2
<40-60 word Flux prompt>

#3
<40-60 word Flux prompt>

[Chapter2]

#1
<40-60 word Flux prompt>

(continue until the book is exhausted)
===END===
```

# Worked example (Conan Doyle, *The Lost World*, Chapter 1)

This is what correct Flux-targeted prompts look like with the **short
format**.  Notice: character NAMES only (no descriptions — the enrichment
script adds them), `[style]` at the end instead of repeating the full
style phrase.  Every prompt describes a visual event, not the book's prose.

```
===STYLE_BIBLE===
STYLE_ANCHOR: cinematic oil painting, painterly brushwork, rich earthy palette, dramatic chiaroscuro
GENRE: Victorian adventure / scientific romance
SETTING: 1910s London transitioning to South American jungle expedition
TONE: earnest romantic prologue giving way to awestruck adventure
NOTES: Oil painting handles both Edwardian drawing rooms and prehistoric jungle landscapes with consistent period feel. Painterly brushwork keeps the look unified even as scenes shift from intimate gaslit interiors to grand expedition vistas.

===CHARACTER_BIBLE===
EDWARD_MALONE — Irish man early 20s, fair freckled skin, short auburn hair neatly parted, blue eyes, athletic build, brown tweed suit, square jaw, earnest open expression
GLADYS_HUNGERTON — English woman early 20s, pale porcelain skin, dark chestnut hair in Edwardian updo, deep brown eyes, slender graceful build, red high-collared evening gown, aloof refined demeanor
MR_HUNGERTON — English gentleman late 60s, ruddy complexion, fluffy unkempt white hair and side-whiskers, watery pale eyes, soft pear-shaped figure, rumpled grey morning suit, distracted expression

===LOCATION_BIBLE===
HUNGERTON_DRAWING_ROOM — Victorian London drawing room, heavy red velvet curtains, dark mahogany furniture, marble fireplace, gaslight sconces, oil paintings on patterned wallpaper, warm amber light
LONDON_STREET_NIGHT — gas-lit Edwardian London street at night, wet cobblestones reflecting yellow lamplight, fog between brick row houses, distant horse-drawn tram

===PROMPTS===

[Chapter1]

#1
HUNGERTON_DRAWING_ROOM, late evening, warm gaslight, EDWARD_MALONE sitting stiffly on green velvet settee leaning forward earnestly with hat in lap, MR_HUNGERTON gesturing expansively from armchair while monologuing, tense polite mood, wide establishing shot, [style], visible brush strokes, atmospheric haze

#2
HUNGERTON_DRAWING_ROOM, intimate firelight, GLADYS_HUNGERTON sitting in profile against deep red velvet curtain, gaze turned away, expression composed and distant, EDWARD_MALONE kneeling at her feet hands clasped looking up with raw earnest desperation, charged silent moment of confession, medium two-shot, [style], soft rim lighting, romantic mood

#3
LONDON_STREET_NIGHT, gas-lit Edwardian street, wet cobblestones, yellow lamplight, fog between brick row houses, distant horse-drawn tram, EDWARD_MALONE striding purposefully down the street with new resolve, jaw set, hat pulled low, hands in coat pockets, isolated determined figure, three-quarter back angle wide shot, brooding atmosphere, [style], volumetric fog, moody backlight

===END===
```

Notice how every prompt:

- Opens with the **location** (from bible or new)
- States **time of day + lighting** explicitly
- Names **characters present** with their **ALL_CAPS name only** (the
  enrichment script attaches visual descriptors automatically)
- Includes an **active verb** describing what they're doing
- Gives a **shot type** (wide establishing / medium two-shot / wide etc.)
- Uses `[style]` as a short marker (the script expands it)
- Adds **2-3 technical modifiers** that match the chosen style
- Contains **zero book text or quotations**
- Stays in the 40–60 word range (~400–650 characters)

# If you run out of room

For long books your response will hit a length limit before you finish.
That is fine — close cleanly with `===END===` at whatever chapter you
last completed in full. **Do not leave a half-finished chapter.** Wrap up
the current chapter's last prompt, then write `===END===`.

When the user replies "continue from where you left off", emit ONLY:

```
===PROMPTS===
[ChapterN]
#1
...
#2
...
[ChapterN+1]
...
===END===
```

No bibles, no preamble, no explanation. Pick up at the chapter after the
last one you fully completed. The splitter merges continuation files with
the original by chapter number — it does not need the bibles repeated.

# Now do it

Read the book below in full. Build the bibles. Then walk through the book
in ~300-word chunks and emit one Flux-targeted visual prompt per chunk in
the exact format above. Start your response with `===STYLE_BIBLE===` and
end with `===END===`. No other text before or after.

=== PROMPT END ===
