# Executive Producer - Generated Takes Pipeline

## When To Use

Use this pipeline for beat-led generated video where a still becomes a shot: character
beats, product spots, ASMR/scene pieces, reference-driven recreations, and any work
billed on the RunningHub coin chain. The unit of work is a **take** — one approved still
animated into one motion clip — and the deliverable is an assembled master.

Do not use it for narrated explainers (`animated-explainer`), talking-head footage
(`talking-head`), or pure motion graphics (`animation`). If the piece depends on a
script being spoken, route there instead.

## This Pipeline vs Authoring Your Own SVRun

Both routes run the same engine. `generated-takes` is the agent-orchestrated route:
propose, gate, generate takes, edit, compose, deliver — with receipts recorded per take.
The authored-SVRun route stays available for determinism and repeatability. Do not
rebuild this pipeline's gates inside a run; they are the control surface.

## Chain Contract (Binding)

Read `.agents/skills/runninghub/SKILL.md` before planning or firing anything. It owns
the node maps, limits, and measured costs. The rules that must not be broken:

- **Stills first, then motion.** `runninghub_image` (Qwen-Image-2.1 edit) produces the
  still; `runninghub_video` (DMAD MiniMax H3) animates exactly one still per take.
  Never fire a motion take against a still the user has not seen.
- **Frames are explicit, always.** `frames / 24` is the duration and the app's default
  of 124 frames is not a choice — it is an accident. The trained ceiling is 362 frames
  (~15.1s); longer pieces are split into sequential takes.
- **Steps are 8.** The app default of 4 is not the house setting.
- **Substrate is 1344x768.** The H3 canvas follows the input still, so anything else is
  cover-cropped. Scale-fit with blurred fill when the source is a different shape.
- **Takes are honoured approximately.** Trimming to the beat grid is post work, not a
  reason to re-fire a take.

## Billing Governance (Binding)

- **Coin-first.** Generate on the personal key. A shared key bills the account wallet —
  that path needs explicit user approval, per take, every time.
- **Report both lines after every run.** `COINS:` and `COST:` from the task receipt go
  into the asset manifest and the spend ledger. A take without a receipt is unrecorded
  spend, which is the one thing this pipeline exists to prevent.
- **Every paid batch is approved, including stills.** A still costs ~25 coins; the
  scene-plan gate approves the plan, not the spend.
- **Failures before render cost nothing.** A rejected node map is free; do not treat it
  as spend and do not re-fire blindly.
- **A timeout is not a failure to re-fire.** The tool returns the `taskId`; recover the
  running task instead of paying for it twice.
- **Insufficient balance stops the run.** Report the balance, the take that was
  rejected, and ask how to proceed. Never silently downgrade to the wallet.

## Stage Sequence

| Stage | Gate | What the gate reviews |
|---|---|---|
| proposal | approval | Engine per stage, coin estimate, delivery shape, beat grid, audio plan |
| scene_plan | approval | Per-beat still spec, motion prompt, frames, steps, substrate |
| assets | approval | Still batch approved, stills reviewed, then take batch approved; receipts recorded |
| edit | auto | Trim takes to the beat grid, hero take selection |
| compose | auto | Native audio vs music bed, captions, ffprobe validation |
| publish | approval | Master + derivatives, spend ledger reconciliation |

Approval is per gate and per take batch. An approval given at proposal does not
authorize firing takes at the assets gate, and a take batch approval covers only the
takes presented with it.

## Budget

`budget_default_usd: 0.50` guards **wallet** spend only — coins are tracked separately
in the spend ledger. The coin budget is the real constraint: roughly 25 coins per still
and `9 + 0.24 x frames` per take, so a six-take 264-frame piece is roughly 580 coins
including its stills. State that number at the proposal gate before asking for approval.

## Failure Handling

- `NODE_ERRORS` before render: free rejection. Fix the node map, re-present, re-fire
  only after approval.
- Timeout: recover by `taskId`; the work is still running and already paid for.
- Insufficient balance: stop, report, ask.
- Bad still (pose-locked, cropped, wrong subject): re-fire the still, not the take. The
  still is cheap and it decides the motion.
