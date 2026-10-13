# Proposal Director - Generated Takes Pipeline

## When To Use

The opening stage. Turn the request into an approved production plan: concepts, the
engine per stage, the take list shape, the beat grid, and a cost estimate in coins that
the user can actually decide on.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/proposal_packet.schema.json` | Artifact validation |
| Skill | `.agents/skills/runninghub-chain/SKILL.md` | Chain node maps, limits, measured costs |
| Skill | `skills/pipelines/generated-takes/executive-producer.md` | Billing and approval rules |
| Tools | none at this stage | Nothing here is paid |

## Process

### 1. Classify The Source Reality

- `still_led` — the default: subject/character references exist or will be generated.
- `reference_driven` — a supplied clip defines look and motion; analyze it before
  proposing (see `video_analysis_brief` in the reference-input tools).
- `asset_supported` — user-supplied stills or footage carries some beats.

Record `source_mode` and `motion_required: true` in the proposal metadata. This pipeline
exists to generate motion; a still-only deliverable belongs in a different pipeline.

### 2. Propose Two Or Three Beat Structures

Each option differs in **beat structure**, not just wording — for example: a single
sustained take, a three-beat escalation, or a six-beat montage with one hero take.
State the beat count, the target duration, and the shape of each beat.

Deliver it plainly:

```
OPTION A — three beats, 11s, escalating
├── Beat 1 (264 frames, 11.0s): character lifts the jar, neutral start pose
├── Beat 2 (264 frames, 11.0s): turn to camera, product label reads clean
└── Beat 3 (264 frames, 11.0s): settle, hold, end frame usable as a poster
Takes: 3 motion + 3 stills · Est. ~292 coins · ~20 min render
```

### 3. Choose The Engine Per Stage

Default is the coin chain. Record the choice explicitly — later stages must not
substitute silently.

| Stage | Default (coins) | Alternative (approved per use) |
|---|---|---|
| Stills | `runninghub_image` — Qwen-Image-2.1 edit | `google_imagen` or any `image_selector` provider |
| Motion | `runninghub_video` — DMAD MiniMax H3, steps=8 | `gemini_omni_video`, `veo_video` via `video_selector` |
| Narration (optional) | `tts_selector` | — |
| Music | `music_library` then `pixabay_music` (free) | generated music only if approved |

Use an alternative when RunningHub is unavailable, the coin balance cannot cover the
plan, or the user explicitly wants a different look. A hybrid plan (Qwen stills, Veo
motion) is allowed — say so per stage rather than implying one engine throughout.

### 4. Delivery Shape

- **Canvas:** 1344x768 landscape is native. 9:16 is scale-fit plus black pad or a 1:1
  crop — never a portrait crop of a landscape take. State which one.
- **Duration:** `frames / 24`, capped at 362 frames per take. Anything longer is
  explicitly split into sequential takes and assembled.
- **Beat grid:** if the piece is musical, give the BPM and the frame count per beat
  (103 BPM at 24 fps is exactly 14 frames per beat). Trimming to that grid is planned
  in post; takes are never re-fired to chase a frame count.

### 5. Runtime Selection (HARD RULE)

A take-based piece still has to pick its composition runtime, and the choice is not
silent. Read `skills/meta/animation-runtime-selector.md`,
`skills/core/hyperframes.md`, and `AGENT_GUIDE.md` → "Present Both Composition
Runtimes (HARD RULE)".

**MANDATORY workflow — present both runtimes, don't default:**

1. Query `video_compose.get_info()["render_engines"]`. Only present the runtimes the
   environment actually has (`ffmpeg` and `hyperframes` in a bare install; `remotion`
   needs its Node dependencies).
2. Present the real options with brief-specific fit:
   - **ffmpeg** — straight take concat with native audio. The right answer for a pure
     take montage with music and no designed overlays. Fast, deterministic, no Node.
   - **HyperFrames** — when the delivery needs designed work over the takes: kinetic
     titles, HTML/GSAP overlays, caption treatments, registry shader transitions.
     Takes play as native video elements inside the composition.
   - **Remotion** — only when installed; realistically `remotion_caption_burn` for
     caption-led deliveries.
3. Recommend one with rationale tied to the deliverable, then **wait for explicit
   approval** before writing `render_runtime` anywhere.
4. Log a `render_runtime_selection` decision in `decision_log` with every runtime in
   `options_considered`, and `rejected_because` on the ones not chosen.

A runtime named in the proposal is a commitment. If it turns out to be unavailable at
compose time, stop and escalate — do not silently downgrade the piece.

### 6. Audio Plan

H3 takes arrive with their own generated audio. Decide how that is used:

1. **Native take audio** — acceptable for ambience-led pieces; keep it and mix music
   under it.
2. **Music bed** — `music_library` first, then `pixabay_music`. Both are free.
3. **Narration** — `tts_selector`. If narration is the spine of the piece rather than a
   layer, say so at the gate: the explainer pipeline is the better route.

Record the chosen source in `proposal_packet.metadata.audio_plan`.

### 7. Cost Estimate (Mandatory)
Quote coins and the wallet-equivalent guard, from measured rates:

```
COST PLAN
├── Stills: 3 x ~25 coins = ~75 coins
├── Motion: 3 takes x (9 + 0.24 x 264) = ~217 coins
├── Total: ~292 coins (~140x the daily login earn)
└── Wallet guard: $0.00 expected; $0.50 budget cap if a wallet path is approved
```

State the billing rule in the packet: **paid runs fire only on explicit per-take
approval**, and a wallet path is never used implicitly.

### 8. Quality Gate

- engine choice is explicit per stage,
- a composition runtime was presented and approved, with the selection logged,
- the coin estimate covers every still and take,
- the delivery shape respects the 362-frame ceiling,
- the beat grid and audio plan are resolved,
- the per-take approval requirement is written down, not assumed.

## Common Pitfalls

- Planning a 20-second single take. The ceiling is 362 frames; split it.
- Quietly planning the wallet path because the coin balance looks thin.
- Proposing six beats when the budget fits three.
- Treating stills as free. They are ~25 coins each and they decide the motion quality.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate, and it does not
authorize firing takes.
