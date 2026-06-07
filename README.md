# New Audio Book Pipeline

Turn an English public-domain novel into Hindi MP4 audiobooks with
AI-generated visuals and multi-voice character narration — all from
numbered double-click `.command` files.

```
EnglishSource/*.txt  ──(AI chat)──▶  HaikuOutput/*.txt  ──▶  1_split  ──▶  Prompts/
                                                                              │
                                                                      2_generate  ──▶  Images/
                                                                                         │
EnglishSource/*.txt  ──(AI chat)──▶  HindiTagged/*_tagged.txt  ──▶  3_strip  ──▶  HindiClean/
                                        │                                           │
                                  4b_multi  ──▶  AudioMulti/              4a_single  ──▶  AudioSingle/
                                        │                                           │
                                  5b_merge  ──▶  Videos/<ch>_multi.mp4    5a_merge  ──▶  Videos/<ch>_single.mp4

                                                      6_clean  ──▶  wipe everything except source
```

- **Audio synthesis**: Microsoft Edge TTS (free, cloud)
- **Image generation**: Pollinations.ai → Flux (free, with your token)
- **Video encoding**: ffmpeg + Apple Silicon VideoToolbox (hardware GPU)
- **Translation**: manual AI chat paste (DeepSeek / Claude / GPT)
- No local AI model. No torrents. No GPU downloads.

---

## Folder Layout

```
NewAudioBookPipeline/
├── setup.command                       ← double-click ONCE
├── 1_split_prompts.command             ← image prompts from AI reply
├── 2_generate_images.command           ← Pollinations → PNGs
├── 3_strip_tags.command                ← remove character tags from Hindi
├── 4a_convert_single.command           ← single-voice Hindi audio
├── 4b_convert_multi.command            ← multi-voice Hindi audio (characters)
├── 5a_merge_single.command             ← single-voice MP3 + PNGs → MP4
├── 5b_merge_multi.command              ← multi-voice MP3 + PNGs → MP4
├── 6_clean_all.command                 ← delete everything, start fresh
├── README.md                           ← this file
├── .gitignore                          ← git tracking rules
├── config.json                         ← settings (safe to commit — no keys)
├── config.example.json                 ← reference copy for new setups
├── config.local.json                   ← YOUR API key (gitignored — never committed)
├── character_voices.txt                ← character → voice mapping
├── BookToPrompts_HaikuPrompt.md        ← AI prompt for image generation
├── translation_mega_prompt.md          ← AI prompt for Hindi translation
├── .venv/                              ← Python deps (created by setup)
├── scripts/                            ← Python implementation (hidden)
│
├── EnglishSource/                      ← YOU drop English chapter .txt files
├── HaikuOutput/                        ← YOU drop AI's prompt reply .txt
├── HindiTagged/                        ← YOU drop AI-translated tagged chapters
├── Prompts/                            ← GENERATED: per-chapter ImageN.txt
├── Images/                             ← GENERATED: per-chapter ImageN.png
├── HindiClean/                         ← GENERATED: tag-free Hindi chapters
├── AudioSingle/                        ← GENERATED: single-voice MP3s
├── AudioMulti/                         ← GENERATED: multi-voice MP3s
└── Videos/                             ← GENERATED: final MP4s
```

You only ever touch **EnglishSource/**, **HaikuOutput/**, **HindiTagged/**,
and **Videos/**.

---

## First-Time Setup

**Double-click `setup.command` once.** It will:

1. Install Homebrew (if missing)
2. Install ffmpeg via Homebrew
3. Create a Python virtual environment (`.venv/`) with `edge-tts`, `requests`, `Pillow`
4. Create `config.json` with default settings (safe to commit)
5. Ask for your Pollinations API key → saved to `config.local.json` (gitignored)
6. Create `character_voices.txt` with the NARRATOR line
7. Create all working folders

After setup finishes, you're ready to process a book.

---

## Step-by-Step Pipeline

### Prepare Your English Book

Drop your English public-domain novel into `EnglishSource/` as one `.txt` file
**per chapter**:

```
EnglishSource/
├── chapter_01.txt
├── chapter_02.txt
├── chapter_03.txt
...
```

File naming matters — they are sorted alphabetically and mapped to
`[Chapter1]`, `[Chapter2]`, etc. in the AI output. Use `chapter_01.txt`,
`chapter_02.txt`, … (zero-padded, two digits) for best results.

---

### Step 1 — Generate Image Prompts via AI

1. Open `BookToPrompts_HaikuPrompt.md`
2. Copy **everything** from `=== PROMPT START ===` to `=== PROMPT END ===`
3. Paste into a new chat with Claude Haiku / Sonnet / GPT / DeepSeek
4. In the **same message**, paste your full English book text
5. The AI will output a structured block
6. Save the AI's **entire** reply as a `.txt` file in `HaikuOutput/`
   - Name it anything: `haiku_reply.txt`, `prompts.txt`, etc.
   - If the AI runs out of tokens, save the partial reply, ask it to continue,
     and save the continuation as a second `.txt` — the splitter merges them

7. **Double-click `1_split_prompts.command`**
   - Parses the AI reply → `Prompts/chapter_01/Image1.txt`, `Image2.txt`, …
   - One prompt file per image, organized by chapter

---

### Step 2 — Generate Images via Pollinations.ai

**Double-click `2_generate_images.command`**

- Reads every `Prompts/<chapter>/ImageN.txt`
- Calls Pollinations.ai (Flux model) using your token from `config.json`
- Writes `Images/<chapter>/ImageN.png`
- **Resumable**: skips any image that already exists
- **Fix a bad image**: delete the offending `.png` and re-run — only that one
  is regenerated
- **Ctrl+C safe**: re-run to resume where you left off

---

### Step 3 — Translate Chapters to Hindi via AI

1. Open `translation_mega_prompt.md`
2. Copy the entire prompt
3. Paste into a new AI chat (DeepSeek recommended; Claude/GPT works too)
4. Send **one English chapter at a time**
5. The AI produces TWO files per chapter:
   - `chapter_NN_tagged.txt` — Hindi with character voice tags
     (e.g., `<Alice>"तुम कौन हो?"</Alice>`)
   - `chapter_NN.txt` — same Hindi, no tags (plain reading version)
6. Save the **tagged** file to `HindiTagged/chapter_NN_tagged.txt`
7. The AI will also grow `character_voices.txt` as new characters appear —
   add those lines to your project's `character_voices.txt`

**Important**: You only need to save the `_tagged.txt` files to `HindiTagged/`.
The clean version is generated automatically in the next step.

---

### Step 3 (Auto) — Strip Character Tags

**Double-click `3_strip_tags.command`**

- Reads every `HindiTagged/*_tagged.txt`
- Removes all `<CharacterName>...</CharacterName>`, `<pause>`, `<pause:NNN>` tags
- Writes clean Hindi to `HindiClean/chapter_NN.txt`
- Skips files that already have a clean copy (use `--force` to overwrite)

---

### Step 4a — Single-Voice Audio

**Double-click `4a_convert_single.command`**

- Reads each `HindiClean/chapter_NN.txt`
- Synthesizes Hindi speech via Microsoft Edge TTS using **one voice**
  (default: `hi-IN-MadhurNeural` — male, native Hindi)
- Writes `AudioSingle/chapter_NN.mp3`
- Chunks text by sentences (~2800 chars), synthesizes up to 4 chunks in parallel
- **Resumable**: skips chapters whose `.mp3` already exists

---

### Step 4b — Multi-Voice Audio (Character Narration)

**Double-click `4b_convert_multi.command`**

- Reads each `HindiTagged/chapter_NN_tagged.txt`
- Parses `<CharacterName>...</CharacterName>` tags
- Each character speaks in their assigned voice from `character_voices.txt`
- All untagged text (narration, minor characters) is read by the NARRATOR voice
- Inserts natural pauses between speakers, after headings, at paragraph breaks
- Writes `AudioMulti/chapter_NN.mp3`
- **Resumable**: skips existing `.mp3` files

Steps 4a and 4b are independent — run them in any order, or only the one you need.

---

### Step 5a — Merge Single-Voice Audio + Images → Video

**Double-click `5a_merge_single.command`**

For each chapter that has both images and single-voice audio:
`Images/<chapter>/*.png` + `AudioSingle/<chapter>.mp3` → `Videos/<chapter>_single.mp4`

---

### Step 5b — Merge Multi-Voice Audio + Images → Video

**Double-click `5b_merge_multi.command`**

For each chapter that has both images and multi-voice audio:
`Images/<chapter>/*.png` + `AudioMulti/<chapter>.mp3` → `Videos/<chapter>_multi.mp4`

---

**Video features (both 5a and 5b):**
- Audio duration is split evenly across all images
- Random "diffusion/merge"-style crossfade transitions between images
  (fade, dissolve, pixelize, hblur, radial, circle open/close, smooth
  directional wipes, etc.)
- Encoded with Apple Silicon `h264_videotoolbox` (hardware GPU)
- Default 2.5 Mbps bitrate (configurable in `config.json`)
- 30 fps, AAC 192k audio, `faststart` for streaming

**Requires**: Apple Silicon Mac (M1/M2/M3/M4) with ffmpeg from Homebrew.

Steps 5a and 5b are independent — run whichever matches the audio you generated.

---

### Step 6 — Clean Everything, Start Fresh

**Double-click `6_clean_all.command`**

Deletes all generated content:
- `Prompts/`, `Images/`, `HindiClean/`
- `AudioSingle/`, `AudioMulti/`, `Videos/`
- `HaikuOutput/`, `HindiTagged/`

**Preserves**:
- `EnglishSource/` — your English chapters are never deleted
- All scripts, `.command` files, `config.json`, `character_voices.txt`
- Both mega-prompt files, `README.md`

You must type `DELETE` to confirm. After cleanup, you're back to a fresh
pipeline state — ready for a new book or a re-run.

---

## `character_voices.txt` — How It Works

The file maps each character to a voice + pitch + rate:

```
NARRATOR = (Madhur, 0, 0)
Alice    = (Swara, 5, 10)
Bob      = (Madhur, -6, -3)
```

- **NARRATOR** is required — it reads all text outside character tags
- **Character names** must match the tags in `*_tagged.txt` exactly
  (case-insensitive)
- **Voice** can be a short alias (e.g. `Madhur`) or a full Edge TTS name
  (e.g. `hi-IN-MadhurNeural`)
- **pitchHz**: +5 = slightly higher voice, -6 = deeper
- **rate%**: +10 = faster, -5 = slower

The translation AI will suggest character assignments as it encounters new
characters. Add them to this file and they'll be used in the next run of
step 4b.

Available voices are listed in the comments inside `character_voices.txt`.

---

## `config.json` — Key Settings

Settings are loaded in three layers (later overrides earlier):

| Priority | File | Tracked? | Purpose |
|---|---|---|---|
| 1 (base) | `config.json` | ✅ git | Default settings shared by everyone |
| 2 (local) | `config.local.json` | ❌ gitignored | Your Pollinations API key + personal overrides |
| 3 (env) | `POLLINATIONS_API_KEY` | ❌ env var | Override token without touching any file |

`config.local.json` only needs one field — your key:

```json
{
  "pollinations_token": "sk_your_key_here"
}
```

You can also add any other setting from the table below to override the
defaults. The environment variable `POLLINATIONS_API_KEY` takes highest
priority — useful for CI/CD or when you don't want a file at all.

| Setting | Default | What it does |
|---|---|---|
| `pollinations_token` | `""` (from `config.local.json`) | Your Pollinations secret key (`sk_...`) |
| `poll_model` | `flux` | Image model (flux / turbo) |
| `poll_width` × `poll_height` | 1280 × 720 | Output image resolution |
| `poll_gap_sec` | 0.5 | Seconds between API calls — secret keys have no rate limits |
| `video_bitrate_mbps` | 2.5 | Target video bitrate |
| `video_fps` | 30 | Video frame rate |
| `transition_duration_sec` | 1.0 | Crossfade duration |
| `transition_styles` | [fade, dissolve, …] | Random xfade pool |
| `chunk_chars` | 2800 | Characters per TTS chunk |
| `parallel_chunks` | 4 | Concurrent TTS syntheses |
| `gap_same_ms` | 220 | Pause between same-speaker spans |
| `speaker_gap_ms` | 420 | Pause when speaker changes |
| `heading_gap_ms` | 750 | Pause after chapter heading |
| `paragraph_gap_ms` | 450 | Pause at paragraph break |
| `narrator_voice` | `hi-IN-MadhurNeural` | Default narrator |

Edit `config.json` directly to tune these values.

---

## Requirements

- **macOS** on Apple Silicon (M1/M2/M3/M4)
- **Homebrew** (installed automatically by `setup.command`)
- **ffmpeg** with `h264_videotoolbox` (installed automatically)
- **Python 3.10+** (installed automatically if missing)
- Internet connection (for Edge TTS, Pollinations, and AI chat)

---

## Quick Reference Card

| Step | Command | Input | Output | AI Required? |
|---|---|---|---|---|
| Setup | `setup.command` | — | `.venv/`, configs, folders | No |
| 1 | `1_split_prompts.command` | `HaikuOutput/*.txt` | `Prompts/<ch>/Image*.txt` | Yes (manual) |
| 2 | `2_generate_images.command` | `Prompts/` | `Images/<ch>/Image*.png` | No (API auto) |
| 3 | `3_strip_tags.command` | `HindiTagged/*_tagged.txt` | `HindiClean/<ch>.txt` | No |
| 4a | `4a_convert_single.command` | `HindiClean/` | `AudioSingle/<ch>.mp3` | No (cloud TTS) |
| 4b | `4b_convert_multi.command` | `HindiTagged/` | `AudioMulti/<ch>.mp3` | No (cloud TTS) |
| 5a | `5a_merge_single.command` | `Images/` + `AudioSingle/` | `Videos/<ch>_single.mp4` | No |
| 5b | `5b_merge_multi.command` | `Images/` + `AudioMulti/` | `Videos/<ch>_multi.mp4` | No |
| 6 | `6_clean_all.command` | — | deletes all generated | No |

---

## Git / GitHub Notes

A `.gitignore` file excludes all generated folders, the Python virtual
environment, macOS metadata, IDE config files, and **`config.local.json`**
(where your API key lives).

**`config.json` is safe to commit** — it contains no secrets. Your API key
goes in `config.local.json`, which is gitignored. New contributors run
`setup.command`, enter their own key, and a local `config.local.json` is
created automatically.

If your key was ever committed to git history, rotate it at
[enter.pollinations.ai](https://enter.pollinations.ai/) and update your
`config.local.json`.

### Setting up on a new machine

```bash
git clone <repo-url>
cd NewAudioBookPipeline
# Double-click setup.command — enter your Pollinations sk_ key when asked
# That's it. config.local.json is created locally and never committed.
```

### Rate Limiting

`sk_` (secret) keys have **no rate limits** per the Pollinations docs.
The `poll_gap_sec` default is 0.5 seconds — images generate as fast as
possible. If you're using an anonymous/public key, increase this to
16+ seconds in your `config.local.json`.

---

## Troubleshooting

**"ffmpeg not found"**
→ Double-click `setup.command` — it installs ffmpeg via Homebrew.

**"h264_videotoolbox not found"**
→ You're not on Apple Silicon, or your ffmpeg is outdated.
`brew upgrade ffmpeg` and re-run.

**"ModuleNotFoundError: No module named 'edge_tts'"**
→ Double-click `setup.command` — it creates `.venv/` with all dependencies.

**Pollinations returns HTTP 429**
→ Rate-limited. The script auto-retries with backoff. Reduce `poll_gap_sec`
in `config.json` to 16+ seconds if you don't have a token.

**Audio sounds wrong / garbled**
→ Edge TTS occasionally returns empty or partial audio. The script retries
up to 3 times per chunk. If a specific chapter consistently fails, try
reducing `chunk_chars` in `config.json` to 1500.

**"No such file or directory" when double-clicking a .command file**
→ Right-click → Open With → Terminal. Or run `chmod +x *.command` in
Terminal from the project folder.
