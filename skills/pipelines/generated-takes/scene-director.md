# Scene Director - Generated Takes Pipeline

## When To Use

Turn the approved proposal into takeable beats. This stage writes the exact still and
motion specification for every beat — nothing paid happens here, and every number a
later stage needs must be decided now.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | Artifact validation |
| Skill | `.agents/skills/runninghub-chain/SKILL.md` | Node maps, substrate and frame rules |
| Prior artifacts | `state.artifacts["proposal"]["proposal_packet"]` | Approved concepts, engine, delivery shape |

## Process

### 1. One Beat, One Take, One Still

Each beat is a single take with a single start still. If a beat needs two movements,
split it into two beats — the app animates one still per take.

For every beat record:

| Field | Meaning |
|---|---|
| `beat` | Beat index and its place in the arc |
| `still_prompt` | Qwen-Image-2.1 edit instruction (image1 = character, image2+ = item/scene) |
| `still_refs` | The reference images for that still, in slot order |
| `substrate` | The canvas the still is generated at — 1344x768 unless approved otherwise |
| `motion_prompt` | H3 motion direction |
| `frames` | Explicit integer, `frames / 24` = seconds, at most 362 |
| `steps` | 8 |
| `expected_output` | What the take should show when it lands |
| `beat_timing` | Where the trimmed take sits on the beat grid |

### 2. Neutral Poses Move, Pose-Matched Stills Do Not

A still already in the target pose has nowhere to go: the model holds it. Generate
start stills in a **neutral, arms-down, weight-centered pose** when the beat needs real
movement, and state that requirement in the still prompt. A deep pose belongs in the
motion prompt, not in the still.

### 3. Beat Grid Arithmetic

If the piece is cut to music, do the arithmetic now rather than in post:

```
103 BPM at 24 fps -> 24 x 60 / 103 = 13.98 fps/beat -> 14 frames per beat
4 beats -> 56 frames (2.33s)    8 beats -> 112 frames (4.67s)
16 beats -> 224 frames (9.33s)  24 beats -> 336 frames (14.0s)
```

Take lengths are chosen from the beat grid, then trimmed in post. Both 264 and 336
frame takes land close to their number but not exactly on it, which is expected.

### 4. Splitting Over-Length Beats

Anything over 362 frames becomes sequential takes of 362 frames or fewer, with the
split recorded in the plan — including how the last frame of one take feeds the
substrate of the next, since cover-crop drift across a split is visible.

### 5. Substrate Reality Check

The H3 canvas is taken from the input still:

- **1344x768 still** -> the take is exactly that framing.
- **Square still** -> the scene survives; edges are cover-cropped.
- **Portrait still** -> legs, feet, floor and any object at frame edge are lost.

If a beat needs portrait delivery, plan a 1344x768 take and pad or center-crop in
compose — never feed a portrait still and hope.

### 6. Still Review Order

Every still in this plan is fired at the assets gate **before** any take, and the user
sees the still contact sheet first. The still decides the motion quality; approving
them together with the takes hides the one decision the user can actually make cheaply.

### 7. Quality Gate

- every beat names its still, motion prompt, frames, and steps,
- every `frames` value is an explicit integer at or below 362,
- over-length beats are split with the seam planned,
- start stills are pose-neutral wherever the beat needs movement,
- the beat grid arithmetic is written down.

## Common Pitfalls

- Leaving `frames` unset. The app then reads its default 124 frames (~5.2s) silently.
- Specifying a beat that needs two movements as one take.
- Generating a still in the final pose and expecting motion from it.
- Feeding a portrait still into a landscape take and losing the frame edges.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval here approves the plan — not the spend. Paid runs are still gated per take
batch at the assets stage.
