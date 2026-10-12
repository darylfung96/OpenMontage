# Edit Director - Generated Takes Pipeline

## When To Use

After the takes land. Decide what is used, trim it to the beat grid, and prepare a shot
order for compose. This stage does no paid work: everything here is FFmpeg and
judgement.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["scene_plan"]["scene_plan"]`, `state.artifacts["assets"]["asset_manifest"]` | Beat plan and landing takes |
| Tools | `video_trimmer` | Beat-grid trims |

## Process

### 1. Watch Every Take Before Choosing

Watch each take end to end and record a verdict per beat:

- **hero** — motion works, framing holds, use it;
- **usable** — works after a trim, note where;
- **replace** — motion is pose-locked, drifts, or breaks framing; the still is the fix.

A take that only holds its pose is a still with a cost. Name it as such.

### 2. Trim To The Beat Grid

Takes land close to their requested length but not on it (336 frames can come back as
345). Trim to the beat grid with `video_trimmer`:

- compute the target from the frame count, not from wall-clock guessing,
- trim from the head when the movement starts late, from the tail when it settles early,
- keep the first and last frames clean of half-motion.

Never re-fire a take to correct a few frames. That is what this stage is for.

### 3. Native Audio Decisions

H3 takes carry generated audio. Decide per take:

- **keep** — ambience that supports the beat,
- **duck** — keep under a music bed at reduced level,
- **mute** — the beat is music-led and the take audio adds nothing.

Record the decision per take so compose does not have to guess.

### 4. Seams And Splits

For beats split across sequential takes, choose the join point where motion is lowest —
a held frame hides a seam. Note any frame-repeat or speed change used to land the join
on the grid.

### 5. Shot Order And Variants

Produce the final shot order with per-beat in/out points, and state which derivative
shapes the edit supports (9:16 pad, 1:1 crop) before compose builds them.

### 6. Quality Gate

- every beat maps to a selected take or a recorded replacement,
- every trim lands on the beat grid,
- audio decisions are recorded per take,
- seams and splits have a named join point.

## Common Pitfalls

- Choosing the take that downloaded first instead of the one that moves best.
- Re-firing paid takes to fix frame-count drift.
- Leaving native take audio in under a music bed without ducking.
- Cutting a split seam on the fastest frame of the movement.

---

No approval gate at this stage (`human_approval_default: false`). Make the decisions,
write the artifact, and continue to compose in the same run.
