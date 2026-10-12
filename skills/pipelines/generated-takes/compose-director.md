# Compose Director - Generated Takes Pipeline

## When To Use

Assemble the approved edit into the master: stitch the trimmed takes, balance native take
audio against the music bed, add captions or overlays if the delivery calls for them, and
validate the output. No paid work here.

## Runtime Routing (HARD RULE)

Render by `edit_decisions.render_runtime`, and only that value:

- `"ffmpeg"` — straight take concat with native audio via `video_compose`/
  `video_stitch`. The default for a take montage with no designed overlays.
- `"hyperframes"` — the approved delivery has designed work over the takes: kinetic
  titles, HTML/GSAP overlays, caption treatments, registry shader transitions. The
  takes play as native video elements in the HyperFrames composition; build in
  `projects/<id>/hyperframes/` and read `skills/core/hyperframes.md` first.
- `"remotion"` — only when the environment has it installed, realistically for
  `remotion_caption_burn` on caption-led deliveries. Check
  `video_compose.get_info()["render_engines"]` before promising it.

If the approved runtime is unavailable at render time, **stop and escalate** — re-open
the proposal stage and surface the constraint. Silently substituting Ken Burns stills or
a different runtime is a governance violation, per AGENT_GUIDE.md → "Present Both
Composition Runtimes (HARD RULE)".

Pass `proposal_packet`/`brief` into `video_compose.execute()` so runtime-swap detection
can see the deviation.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json`, `schemas/artifacts/final_review.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["edit"]["edit_decisions"]`, `state.artifacts["assets"]["asset_manifest"]` | Shot order and landing media |
| Tools | `video_compose`, `audio_mixer` (required); `video_stitch`, `subtitle_gen`, `audio_enhance`, `color_grade`, `pixabay_music`, `music_library` | Assembly |

## Process

### 1. Stitch The Takes

Use `video_stitch` or `video_compose` per the edit decisions. Takes are h264/aac at
1344x768 24 fps; keep the native frame rate — frame-rate conversion is where these
pieces start to look wrong.

Frame-repeat or freeze to land a seam on the grid rather than resampling the whole
timeline.

### 2. Audio Balance

- **Native take audio** — each H3 take carries its own ambience. Keep it at full level
  when it is the piece's sound, duck it under a music bed when it is not.
- **Music bed** — `music_library` first, then `pixabay_music` (both free). Generated
  music only if the proposal approved it.
- **Ducking** — music under native audio, not the reverse. A music bed that fights the
  take audio is the most common failure in this pipeline.
- **Narration** — if narration was planned, mix it last, and check it against the take
  ambience rather than only against the music.

Use `audio_mixer` for the stems, `audio_enhance` only where the source needs repair.

### 3. Captions And Overlays

Optional. When the delivery needs them, `subtitle_gen` writes subtitles and overlays are
authored per the active style playbook. Keep text inside safe zones — the H3 canvas
follows the input still, so a framing change mid-piece moves the safe area with it.

### 4. Master And Derivatives

Build the master first, then derivatives:

- **master** — native 1344x768 landscape,
- **9:16 derivative** — scale-fit with black pad (background is pure black in these
  takes, so pads are invisible), or a 1:1 crop for feed formats,
- **poster** — a held frame from the final beat when the edit supports one.

### 5. Validate

Run ffprobe on every export and record in the render report: duration, resolution, frame
rate, codecs, file size. A master that ffprobe cannot read is not a deliverable.

### 6. Quality Gate

- native audio and the music bed are balanced, not fighting,
- captions and overlays sit inside safe zones,
- the master passes ffprobe validation at the approved shape,
- derivatives are labeled by shape and use.

## Common Pitfalls

- Resampling frame rate to fix a seam instead of repeating frames.
- Mixing music over native audio the beat was built around.
- Exporting only the master and leaving derivatives implicit.
- Skipping ffprobe because the file plays in a browser.

---

No approval gate at this stage (`human_approval_default: false`). Compose, validate, and
carry the render report forward to publish.
