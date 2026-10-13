---
name: runninghub
description: Run published RunningHub AI Apps and Workflow API tasks — the Qwen-Image-2.1 still stage and the DMAD MiniMax H3 motion stage of the runninghub chain, plus any app addressed by webappId. Use when generating or editing stills on RunningHub, animating a still with MiniMax H3, or reasoning about RH Coin vs wallet billing on that account.
---

# RunningHub

Requires a key in `.env`: `RUNNINGHUB_PERSONAL_KEY` (membership key, bills RH
Coins — the house default) with `RUNNINGHUB_API_KEY` (shared key, bills the
account wallet) as the fallback. The client is coin-first: the personal key wins
whenever both are present, and a wallet-billed run needs explicit approval.
Host defaults to
`https://www.runninghub.ai`; set `RUNNINGHUB_API_HOST=https://www.runninghub.cn`
for the mainland site.

RunningHub is an app host, not a model API: you run a published ComfyUI
application (`webappId`) and can only set the nodes its author exposed. Node
maps below are the contract — free `--info` probes verified them, and
`tests/contracts/test_runninghub_*.py` lock them in.

## Chain

| Stage | Tool | App | Billing |
|---|---|---|---|
| Still edit | `runninghub_image` | Qwen-Image-2.1 edit `2103143960360300545` | key-dependent |
| Motion | `runninghub_video` | DMAD MiniMax H3 `2106414322893619202` | key-dependent |

The still stage is reference-conditioned editing, not text-to-image: image1 is
the character reference and image2+ are the items or scenes being worked. Five
image slots and one prompt are exposed. The motion stage animates a start still —
run the still stage first for text-to-video work.

## Billing — coin-first

Billing follows the **key**, not the account: a personal (membership) key bills
RH Coins, a shared key bills the account wallet (~$0.7/h of GPU runtime,
measured at $0.0002/s). The client resolves `RUNNINGHUB_PERSONAL_KEY` first and
falls back to `RUNNINGHUB_API_KEY` — reading the shared key by default once billed
a whole take to the wallet while coins sat unused, so coin-first is enforced in
code. Use the personal key by default, never fire a paid take
without explicit approval, and report the receipt after every run. Task
receipts carry `consumeCoins` (coins path) or `consumeMoney` (wallet path);
failures before render cost nothing, so a rejected node map is always free.

Measured per-take costs:

| Take | Coins | Wallet |
|---|---|---|
| Qwen still (90-130s) | ~25 | ~$0.02 |
| H3 motion, steps=8 | ~9 fixed + ~0.24/frame | runtime x $0.0002/s |

## DMAD MiniMax H3 node map

Prompt `9:text`; images `19:image`-`27:image` (image1-9); videos `28:video`-`30:video`;
audios `31:audio`-`34:audio`; length `35:value` in frames (frames / 24 = seconds);
sampler `11:steps` (app default 4, **fire at 8**).

- **Frames are always set explicitly.** Omitting `35` reads the app default of
  124 frames (~5.2s).
- **Ceiling is 362 frames** (~15.1s at 24 fps): chunk longer pieces into
  sequential takes and assemble in post.
- Output is 1344x768 landscape, 24 fps, h264 with its own generated audio, in a
  MOV container that `runninghub_video` patches to MP4.
- **The output canvas follows the input still.** Feed a 1344x768 substrate
  (scale-fit with blurred fill) or expect cover-cropping; square stills keep the
  scene, portrait stills lose the frame edges.
- Frames are honoured closely but not exactly (336 requested came back as 345),
  so trim to the beat grid in post.
- Motion is decided by the input still: a still already in the target pose just
  holds the pose — start from a neutral pose when the take needs movement.

## Free inspection

Probe an app's exposed nodes before designing a call (never billed):

```bash
export RUNNINGHUB_API_HOST="https://www.runninghub.ai"
python3 ~/.agents/skills/runninghub/scripts/runninghub_app.py --info <webappId>
```
