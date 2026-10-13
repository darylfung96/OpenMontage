# Asset Director - Generated Takes Pipeline

## When To Use

Fire the approved plan: stills first, then motion takes, with per-take approval and a
recorded receipt for every paid run. This is the only stage in the pipeline that spends
money, and the only one where the order of operations is non-negotiable.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact validation |
| Skill | `.agents/skills/runninghub-chain/SKILL.md` | Node maps, limits, billing behaviour |
| Prior artifacts | `state.artifacts["scene_plan"]["scene_plan"]` | The take list, frames, stills, steps |
| Tools | `runninghub_image`, `runninghub_video` | The chain |

## Process

### 1. Stills First — Approve The Still Batch, Then Show It

The still batch is a paid run and gets its own approval, exactly like a take batch.
Nothing fires on the strength of the scene-plan gate.

Present the still batch:

```
STILL BATCH — ask for approval
├── Beat 1 still: character + jar, neutral pose — est. ~25 coins
├── Beat 2 still: character + jar, turned three-quarter — est. ~25 coins
└── Total: ~75 coins · wallet $0.00 expected
```

Fire only the approved stills through `runninghub_image`:

- image1 is the character reference, image2+ are the items or scenes being worked.
- Up to five references per still; a local path is uploaded automatically.
- Pass the beat's `still_prompt` verbatim from the scene plan.

Then **end the turn with the still contact sheet**. No motion take fires until the user
has seen the stills. A still is ~25 coins; a bad still animated is ~25 coins plus a
wasted take, and the take is what makes the mistake expensive.

### 2. Present The Take Batch, Then Fire It

Before any take, present the exact batch:

```
TAKE BATCH — ask for approval
├── Beat 1: 264 frames, steps 8, still still_01.png — est. ~72 coins
├── Beat 2: 264 frames, steps 8, still still_02.png — est. ~72 coins
├── Beat 3: 336 frames, steps 8, still still_03.png — est. ~90 coins
└── Total: ~234 coins · wallet $0.00 expected
```

Fire only what was approved in that batch. A take count and a beats-per-video
agreement is not approval; the specific batch is.

### 3. Call The Chain Correctly

`runninghub_video` takes:

- `prompt` — the beat's motion direction,
- `reference_image_path` (or URL) — the approved still,
- `frames` — the explicit integer from the scene plan (never omitted),
- `steps` — 8.

The tool warns when a start still is off 16:9; treat that warning as a stop-and-look,
not as noise. It also patches the MOV container to MP4 — no re-encode is needed or
wanted.

### 4. Record Every Receipt

After each paid run — stills and takes alike — write into the asset manifest:

- `task_id`, coins consumed (`COINS:`), wallet charge (`COST:`), billing mode,
- the output path and probed duration/resolution,
- the requested vs returned frame count when they differ.

A take without a receipt is unrecorded spend. If the receipt is missing, query the task
by `taskId` rather than re-firing it.

### 5. Failure Handling

| Failure | Action |
|---|---|
| `NODE_ERRORS` before render | Free. Fix the node map, re-present, re-fire only after approval |
| Timeout | Recover by `taskId` — the take is running and already paid for |
| Insufficient balance | Stop the batch. Report balance, the rejected take, and ask |
| Bad motion (pose-locked, drift) | Re-fire the **still** first; the still decides the motion |
| Returned frames off by a few | Not a failure. Trim in post at the edit stage |

### 6. Fallback Engines

If RunningHub is unavailable or the coin balance cannot cover the batch, offer the
approved alternative from the proposal — `image_selector` for stills, `video_selector`
for motion (Gemini Omni, Veo). Never substitute silently, and never route to a wallet
path to keep a batch moving.

### 7. Quality Gate

- the still batch was approved before any still fired,
- stills were reviewed before any take fired,
- every take in the batch was explicitly approved before it ran,
- every paid run has a recorded receipt,
- the manifest lists files that actually exist on disk,
- any fallback engine use was approved and recorded.

## Common Pitfalls

- Firing stills on the strength of the scene-plan approval. They are paid.
- Firing takes and stills in one batch. The still is the cheap decision point.
- Treating a coin estimate as an approval.
- Re-firing a timed-out take. It is already running and already paid for.
- Letting a portrait still through because the still looked good as a still.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). Each paid batch —
stills or takes — is its own approval: present the batch, checkpoint with
`status="awaiting_human"`, and **END YOUR TURN**. Do not fire a second batch on the
strength of the first batch's approval, even when the first batch succeeded cleanly.
