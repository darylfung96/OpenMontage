# Publish Director - Generated Takes Pipeline

## When To Use

Deliver the master and close the books. This stage produces the export package, the
spend ledger, and the publish log — and it is where the run's coin spend is reconciled
against what was approved.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["compose"]["render_report"]`, `state.artifacts["compose"]["final_review"]` | Validated master |
| Prior artifacts | `state.artifacts["assets"]["asset_manifest"]` | Take receipts |

## Process

### 1. Assemble The Export Package

| Item | Notes |
|---|---|
| Master | Native 1344x768 landscape, the delivery of record |
| 9:16 derivative | Scale-fit plus pad, or the approved 1:1 crop |
| Poster | Held frame where the piece supports one |
| Receipts | One line per take: task id, coins, wallet charge |

Label each export by shape and intended use. A file named `final_v2.mp4` is not a
deliverable; `client-take-master-1344x768.mp4` is.

### 2. Reconcile The Spend Ledger

This is the step the pipeline exists to protect. For every take:

```
SPEND LEDGER
├── Still 01        25 coins    task 2107...282    $0.00
├── Take 01         74 coins    task 2107...970    $0.00
├── Take 02         67 coins    task 2107...115    $0.00
└── Total: 166 coins · wallet $0.00 (personal key)
```

Reconcile against the approved estimate from the proposal gate:

- **at or under estimate** — note it and move on;
- **over estimate** — say why (retake, longer take, extra still) rather than restating
  the total;
- **any wallet charge** — say it plainly. A wallet charge means a shared-key path was
  used, which required explicit approval; if it was not approved, that is a finding to
  report, not a line to bury.

### 3. Delivery Location

State the durable delivery path (the project output directory) explicitly. Cloud output
is ephemeral — a published piece lives in a location the user can point at later.

### 4. Publish Log

Write the publish log with: master path, derivative paths, spend ledger, delivery
location, and the date. Record the run's task ids — they are how a take is recovered or
queried later.

### 5. Quality Gate

- every export is labeled by shape and use,
- the spend ledger includes every take's receipt,
- any wallet charge is explained and was approved,
- the delivery location is explicit and durable.

## Common Pitfalls

- Shipping the master without the 9:16 derivative that the platform needs.
- A ledger that lists a total but no per-take receipts.
- Quietly absorbing a wallet charge into a round number.
- Delivering to a temporary path and calling it published.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Delivery, not generation, is what this gate
approves — the receipts are already spent and must be visible before the piece ships.
