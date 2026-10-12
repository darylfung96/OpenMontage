"""Known RunningHub AI Apps: node maps, limits, and measured costs.

An AI App exposes a fixed set of adjustable nodes. A node the app's author did
not expose cannot be set from the API, so these maps are the contract between
the provider tools and the published apps. Every map here was verified live
with a free ``--info`` probe and every cost was measured on real takes, not
copied from a pricing page -- see the notes on each block for dates.

The chain: Qwen-Image-2.1 edit produces stills, DMAD MiniMax H3 turns a still
into motion with its own generated audio. Billing follows the API key on the
call -- a personal key bills RH Coins, a shared key bills the account wallet.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Qwen-Image-2.1 edit -- still stage
# ---------------------------------------------------------------------------

QWEN_IMAGE_EDIT_APP_ID = "2103143960360300545"
QWEN_IMAGE_EDIT_PAGE = f"https://www.runninghub.ai/ai-detail/{QWEN_IMAGE_EDIT_APP_ID}"
QWEN_IMAGE_EDIT_PROMPT_NODE = ("479", "value")
# image1 is the character reference and image2 the item/scene being worked;
# the remaining slots take further references in order.
QWEN_IMAGE_EDIT_IMAGE_NODES = [
    ("470", "image"),
    ("477", "image"),
    ("475", "image"),
    ("2475", "image"),
    ("2476", "image"),
]
QWEN_IMAGE_EDIT_MAX_IMAGES = len(QWEN_IMAGE_EDIT_IMAGE_NODES)
QWEN_IMAGE_EDIT_MEASURED_COINS = 25.0  # 2026-10-04 paid take, personal key
QWEN_IMAGE_EDIT_MEASURED_WALLET_USD = 0.02  # shared-key take, measured earlier
QWEN_IMAGE_EDIT_RUNTIME_SECONDS = 130.0  # 90-130s across measured takes

# ---------------------------------------------------------------------------
# DMAD MiniMax H3 -- motion stage
# ---------------------------------------------------------------------------

DMAD_MINIMAX_H3_APP_ID = "2106414322893619202"
DMAD_MINIMAX_H3_PAGE = f"https://www.runninghub.ai/ai-detail/{DMAD_MINIMAX_H3_APP_ID}"
H3_MODEL_LABEL = "minimax-h3-dmad"
H3_PROMPT_NODE = ("9", "text")
H3_IMAGE_NODES = [(str(node), "image") for node in range(19, 28)]  # image1-9
H3_AUDIO_NODES = [(str(node), "audio") for node in range(31, 35)]  # audio1-4
H3_FRAMES_NODE = ("35", "value")
H3_STEPS_NODE = ("11", "steps")
H3_MAX_IMAGES = len(H3_IMAGE_NODES)
H3_MAX_AUDIOS = len(H3_AUDIO_NODES)

H3_FPS = 24
H3_MAX_FRAMES = 362  # trained ceiling; longer takes must be chunked
H3_DEFAULT_FRAMES = 124  # app default (~5.2s) -- always set frames explicitly
H3_APP_DEFAULT_STEPS = 4
H3_DEFAULT_STEPS = 8  # user decision 2026-10-04
H3_OUTPUT_SIZE = (1344, 768)  # vertical delivery is scale-fit + pad, not crop

# Measured 2026-10-05 / 2026-10-09 on paid takes at steps=8: roughly
# 9 fixed coins plus ~0.24 coins per frame -- short takes carry proportionally
# more overhead, so long takes are budgeted at fixed + per-frame.
H3_COST_FIXED_COINS = 9.0
H3_COST_COINS_PER_FRAME = 0.24

# Shared (wallet) billing measured at $0.7/h of GPU runtime.
WALLET_USD_PER_SECOND = 0.0002

H3_SUBSTRATE_NOTE = (
    "The H3 app takes its output canvas from the input still: feed a 1344x768 "
    "substrate (scale-fit with blurred fill) or non-16:9 framing is cover-cropped. "
    "Square stills keep the scene intact; portrait stills lose the frame edges."
)


def h3_estimated_coins(frames: int) -> float:
    """Coin estimate for a take, matching measured receipts."""
    return round(H3_COST_FIXED_COINS + H3_COST_COINS_PER_FRAME * int(frames), 1)


def h3_estimated_runtime_seconds(frames: int) -> float:
    """Wall-clock estimate; measured 264f in 5-6.5 min and 336f in 7.6 min."""
    minutes = 1.0 + 0.021 * int(frames)
    return round(minutes * 60.0, 1)


def h3_estimated_wallet_usd(frames: int) -> float:
    """Shared-key wallet estimate; a personal key bills coins instead."""
    return round(h3_estimated_runtime_seconds(frames) * WALLET_USD_PER_SECOND, 4)
