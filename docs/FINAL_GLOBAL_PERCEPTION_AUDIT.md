# Final global perception audit

Baseline: `rebuild/stable-baseline @ 392458f`. Prior checkpoint: 2451/2451 hardware-free.
Date: 2026-09-16. Inventory derived from productive code (`bot/`), not from history docs.
Tests/tools/workbench excluded from the productive inventory, used as evidence.

Three minimal productive findings were implemented in this audit (see §7);
everything else is classification-only.

## 1. Categories

- **G — GLOBAL LEGÍTIMO**: discovery, recovery, reorientation, session/trust
  boundary or genuinely open context. Keeping the full detector catalog is
  the correct contract.
- **S — SPECIALIZED**: temporal/raw-frame/OCR or bespoke polling logic whose
  unit of work is not the normal `ContextResolver` wait. Not forcible into
  `ScopeSpec` without redesigning the mechanism.
- **J — JUSTIFICADAMENTE GLOBAL**: known path, but the contract needs an
  open/complete contradiction vocabulary; scoping it would be pseudo-global
  or incorrect. Each J cites current tests/contracts, never "already audited".
- **DEFER**: known debt, consciously postponed: needs new physical evidence,
  new semantics or a transversal change not rentable now. Explicit motive below.
- **K — KNOWN TRANSITION CANDIDATE**: known context + known action + closed
  expected/retry/abort vocabulary, still global without sufficient
  justification. Target state is zero open K.
- **D — DUPLICATE / REUSE**: repeated perceptive work avoidable with already
  produced evidence. Target state is zero open local D.
- **BUG**: global analysis revealing or hiding an incorrect
  authorization/retry/abort contract. Target state is zero open BUG.

Close criterion: every frequent normal-path wait/transition with known
context and closed expected/retry/abort vocabulary uses scoped perception or
explicit evidence reuse; remaining global analyzes exist for real
discovery/recovery/reorientation, specialized temporal/raw logic, justified
open contradiction vocabularies, deliberate trust boundaries, or explicitly
documented deferred debt.

## 2. Detector counts (measured, `build_default_perception` = 95)

Global engine: **95** detectors. Scoped: claim **4**, open **6**,
completion/friends **3**, attendance **3**, slot/purchase **6**, summon
**17**, eligibility **5**, navigate scopes **5**, all lobby returns **77**,
rotation selection **2**. ms/frame per scope: **unknown** (no new
micro-benchmark in this audit; the integral benchmark reads
`perception.analyze_summary` events). Every `wait_until` polls, so one wait
costs 1 + N analyzes (N bounded by timeout/stable windows, unknown until
the benchmark — the count model below counts waits, not frames).

## 3. Master table

`site | caller/flow | phase | frequency | observer | reason global | class | action`

| site | caller/flow | phase | frequency | observer | reason global | class | action |
|---|---|---|---|---|---|---|---|
| `_clean_context_entry` initial observe + settled wait | ProductiveRuntime preconditions | entry probe | per ensure (~9/char) | global 95 | open context: 6 clean bases + unknown; session trust boundary | G | KEEP |
| `_recover_clean_context` second wait | ProductiveRuntime | recovery | only on timeout | global 95 | post-recovery reorientation | G | KEEP |
| `_navigate_to_lobby/guild/pets_manage/lobby_to_guild` initial observes | ProductiveRuntime | normalize | on normalize only | global 95 | acquired origin from open context | G | KEEP |
| `open_quick_menu` transitions | preconditions / rotation / zone | normalize/rotation | per normalize + 1/char | global 95 | menu overlay from open origin set; multi-base lineage | G | KEEP |
| rotation initial observe + precondition wait | Rotation | entry | per character | global 95 | multi-base QuickMenu-capable set, unknown okay to wait | G | KEEP |
| `rotation.open_character_select` | Rotation | R2-C | per character | global 95 | foreign bases must stay observable; small scope degrades foreign RESOLVED → UNKNOWN+menu and can authorize wrong retry | J | KEEP (justified §4) |
| rotation post-swipe wait | Rotation | R2-A | per swipe | scoped 2 | — | — | already scoped |
| rotation reobservation wait (UNKNOWN/AMBIGUOUS) | Rotation | retry path | only on retry | global 95 | recovery reorientation, authorizes no input | G | KEEP |
| `select_predecessor_character` / `confirm_character_selection` | Rotation | R1 + return | per character | scoped 2 / scoped 77 | — | — | already scoped |
| BattleModeZone enter hub wait (`after_sequence=0`) | WB / MW zone | entry | per zone visit | global 95 | deliberate session re-verify after precondition (KEEP_REOBSERVE) | G | KEEP |
| BattleModeZone leave `select_lobby` | WB / MW zone | return | per zone visit | scoped 77 | — | — | already scoped |
| flow `_initial_*` observes + precondition waits (BM/Daily/Mailbox/SendStamina/Guild) | flows | entry | per character, seed miss only | global 95 | trust boundary; seed reuse implemented | G | KEEP |
| Summon `_initial_manage` | SummonPetDaily | entry | per character | global 95, **now seed-reusing** | trust boundary; did not opt into seed | D→fixed §7 | IMPLEMENTED |
| Daily `_wait_for_daily_tab` polling observes | DailyQuests | tab-loop | per character when off-tab | global 95 | open blockers; small candidate yields false actionable; readiness ≠ safety | J | KEEP (justified §4) |
| Daily `OpenQuests` wait | DailyQuests | navigation | per character | scoped 6 | — | — | already scoped |
| Daily `ClaimAll` wait | DailyQuests | claim | when claimable | scoped 4 | — | — | already scoped |
| Daily progress-reward wait | DailyQuests | claim | when progress claimable | **was global 95, now scoped 4** | same scope + same abort as ClaimAll | K→fixed §7 | IMPLEMENTED |
| Daily `CloseDailyQuests` | DailyQuests | return | per character | scoped 77 | — | — | already scoped |
| BM `open`/slot/purchase/close + gold confirmation | BlackMarket | nav/claim | per character | scoped 7/6/6/77 + scoped 7 | — | — | already scoped |
| Mailbox open/claim/close | Mailbox | nav/claim/return | per character | scoped 5 / scoped 5 / scoped 77 | — | — | already scoped |
| SendStamina open/completion/close | SendStamina | nav/completion/return | per character | scoped 3 / scoped 3 / scoped 77 | — | — | already scoped |
| Guild initial + completion | GuildCheckIn | entry/completion | per character | global 95 + scoped 3 | initial is trust boundary w/ seed reuse | G | KEEP |
| Summon navigation/outcome/dismissal waits | SummonPetDaily | gameplay | per character | scoped 17 | — | — | already scoped |
| WB eligibility observe + badge wait | WorldBoss eligibility | eligibility | per character w/ WB | scoped 5 | — | — | already scoped |
| MW eligibility observe + badge wait | MonsterWave eligibility | eligibility | per character w/ MW | **was global 95, now scoped 5** | shares WB hub scope exactly | K→fixed §7 | IMPLEMENTED |
| WB activity hub waits (battle_modes, open_selector, select_available, entry settle, ack_previous_rewards, main) | WorldBossActivity | hub navigation | per character w/ WB | global 95 | open entry branches + popups + full contradiction vocabulary; resolver-complete subset ≈ full catalog | DEFER | NEEDS_EVIDENCE §5 |
| WB `run()` post-activity hub re-wait | WorldBossActivity | postcondition | per WB run | global 95 | session re-verify before hub return (KEEP_REOBSERVE) | G | KEEP |
| WB Raid Complete polling loop (manual `observe`) | WorldBossActivity | combat wait | per fight | global 95 | specialized confidence/stale/terminal polling, not a plain wait | S | KEEP (§6) |
| WB timer/sapphire reads, Auto Battle harvests/guards/baselines | facts / AutoBattle | combat support | per fight/flow | global 95 + raw frames | temporal/OCR/raw-frame mechanisms | S | KEEP, do not touch (§6) |
| MW activity waits (hub, entry normalize, sapphire-gated re-wait, ticket steps) | MonsterWaveActivity | hub/entry | per character w/ MW | global 95 | same family as WB hub waits (popups, branches, reliefs) | DEFER | NEEDS_EVIDENCE §5 |
| VerifiedTransition internal observes (retry-state, post-recovery) | all transitions | retry/recovery | only on retry | inherits caller scope | bounded retry evidence, never authorizes alone | G | KEEP |
| ObstructionRecovery observes | recovery | recovery | on portal CONFIRMED | global 95 | recovery reorientation | G | KEEP |
| Socket/EquipmentCombine/PetSummonSpace relief observes + waits | reliefs | relief | on relief trigger (rare) | global 95 | known-context but no scope exists; rare path | DEFER | NEEDS_EVIDENCE §5 |
| TapThroughAnimation any-frame waits | reliefs | relief | on relief trigger (rare) | global 95 | semantic-free frame pump (predicate always true) | S | KEEP + note §6 |
| SessionRunner postconditions (`current_satisfies_any`) + zone return checks | SessionRunner | postcondition | per flow + rotation | global 95 | deliberate re-observe trust boundary (KEEP_REOBSERVE) | G | KEEP |
| precondition → flow seed handoff | SessionRunner→flows | handoff | per flow | 0 analyzes on hit | explicit snapshot argument, no cache | — | reuse infra (BM/Daily/Mailbox/SendStamina/Guild/Summon) |

Normal-path transition detail (known transitions on global): only R2-C and
the Daily tab-loop remain global by justification (§4); WB/MW activity hub
waits are DEFERRED (§5), everything else scoped or trust-boundary G.

## 4. J justifications (re-verified against current code, not history)

**Daily tab-loop** (`daily_quests_flow.py` `_wait_for_daily_tab`, global 95,
polling `observe`): the post-tap state space is open — Daily
content-ready, Daily-active-but-loading (must wait passively, must not tap),
clean Quests off-tab (may tap once per sequence), UNKNOWN/AMBIGUOUS
(passive), contradictory RESOLVED (abort). A small scope (title+tab+rows)
cannot distinguish a foreign blocker popup from a loading list: both degrade
to "not ready", turning a must-abort into a must-wait-timeout (false
actionable / masked contradiction). Readiness detectors gate the open wait,
never safety. Contract pinned by `test_daily_tab_loop_semantics.py` and the
readiness suite. Re-audit trigger: only if the abort vocabulary becomes
closed (enumerated blocker set with evidence).

**Rotation R2-C** (`rotation.py` `open_character_select`, global 95,
`handoff.observe + _has_unexpected_character_select_transition`): the wait
must keep foreign bases observable — a scoped 2-detector engine degrades a
foreign RESOLVED screen to UNKNOWN+menu, which `handoff.allows` still
accepts, authorizing a bounded retry from a wrong context. The global abort
needs the full base/overlay catalog to fail fast. Pinned by
`test_rotation_r2c_global_justification.py` (scoped RESOLVED→UNKNOWN+menu
degradation + wrong-retry authorization). Re-audit trigger: only if the
handoff lineage changes.

## 5. Explicit DEFERs (no new physical evidence / transversal / rare path)

- **D_TRANSVERSAL-1** (kept): `FlowResult` → SessionRunner snapshot carry.
  Zone flows (WB/MW) cannot reuse the precondition snapshot because zone
  entry sends input afterwards; carrying the zone-entry snapshot across the
  eligibility/return checks needs a transversal snapshot-plumbing change.
- **D_TRANSVERSAL-2** (kept): `_navigate_to_guild` bool→snapshot
  trust-boundary change (same for `_navigate_to_lobby`/`_pets_manage` bool
  returns + `_navigate_and_verify` re-probe). The re-probe is the deliberate
  interaction-boundary verification; removing it needs transversal plumbing.
- **NEEDS_EVIDENCE-1**: WB activity hub waits (6 global waits/char). A
  resolver-complete scope (≈77 detectors, B2 precedent) would save ~20% on
  these waits only, and needs curated positive/negative/proximate physical
  evidence per wait. Combat/entry vocabulary (branches, popups, reliefs,
  raid-complete) stays open.
- **NEEDS_EVIDENCE-2**: MW activity waits (same rationale, shared hub).
- **NEEDS_EVIDENCE-3**: relief waits (socket/equipment-combine/pet-space).
  Rare/error path (relief trigger only); frequency × cost does not justify
  new scopes now.
- **Lobby <77 per-consumer scopes** (kept): needs structural/seasonal
  landmark work + new physical evidence. Not reopened: no contradiction found.

## 6. S confirmations (mechanism needs its logic, not ScopeSpec)

- Auto Battle `ensure_on`/`ensure_on_quick` (+ guards/baselines): temporal
  ON/OFF/UNKNOWN classifier over raw harvests; one full observation only
  confirms battle context. Touching it risks false-OFF taps (persistent
  setting). Closed correctness suite `test_auto_battle.py`.
- FactReader (`read_timer_remaining`, sapphires): OCR-over-ROI after
  any-RESOLVED gating; per-context scoping needs new evidence. Timer OCR
  explicitly out of scope for this audit.
- WB Raid Complete poll loop: bespoke confidence-max/stale-count/terminal
  contradiction polling; abort predicate needs full vocabulary (any fresh
  resolved non-raid state is terminal). Scoping risks hiding the terminal.
- TapThroughAnimation: predicate-true frame pump. Note (not action): a
  minimal/empty scope could serve it, but it runs only on rare relief paths;
  no infra change without evidence.

## 7. Implemented findings (local, demonstrated, small, no new evidence)

1. **D_LOCAL Summon seed** (`bot/summon_pet_daily_flow.py`): flow ignored the
   SessionRunner precondition snapshot (no `run_with_initial`), costing 1
   global observe per character. Added `run_with_initial` + seed-first
   `_initial_manage`, mirroring Guild/BM (same `_is_clean_manage` as the
   precondition verifier). Tests: reuse drives navigation past a
   would-be noop; bad seed falls back; optional-seed dispatch.
2. **K_SAFE Daily progress-reward** (`bot/daily_quests_flow.py`): the wait
   ran global while `DAILY_CLAIM_SCOPE` already covers its exact vocabulary
   (settle + progress-indicator absence, same abort predicate as ClaimAll;
   equivalence pinned in `test_daily_claim_scope.py`). Routed through
   `claim_observer` (95→4). Tests: updated readiness routing test + new
   progress-only routing test.
3. **K_SAFE MW eligibility** (`bot/productive_runtime.py`): check ran global
   while WB eligibility already scopes the identical hub vocabulary.
   Added `build_monster_wave_daily_eligibility` on the shared
   `WORLD_BOSS_ELIGIBILITY_SCOPE` (95→5) with distinct events. Tests: new
   `test_monster_wave_eligibility_scope.py` (19 hub + 6 foreign curated
   frames equivalence, wiring, fallback, generic-infra-only).

## 8. QuickMenu residual audit

Productive `QuickMenuHandoff.observe/allows` consumers: PR→Lobby,
PR→Guild, Rotation→CharacterSelect, BattleModeZone→Lobby. All verified
against current code: destination short-circuits to no-abort (and
invalidates, ending the lineage where appropriate); contradiction
(AMBIGUOUS / foreign RESOLVED / non-menu overlays) invalidates + aborts;
UNKNOWN+menu and tolerated origins wait passively; retries gated by
`allows`; `on_recovery=invalidate` + `recovery_after_action` blocks stale
lineage. No consumer with the old divergence (contractual post-input source
→ observe → false abort). WB selector/entry handoffs are a separate type
with the same fail-closed shape (destination-tolerant, UNKNOWN-passive).
**No change.**

## 9. D residual audit

Checked: VerifiedTransition final→observe (retry-path only, optimal);
precondition→flow initial (all PER_CHARACTER non-zone flows now seed-reuse;
zone flows correctly excluded — input intervenes); close→postcheck and
navigate→re-probe (deliberate KEEP_REOBSERVE boundaries); scoped
destination→global duplicate (session postcondition trust boundary).
**No new D.** BM initial reuse confirmed implemented.

## 10. BUG audit

For every wait/global: UNKNOWN never authorizes input (all preconditions
require RESOLVED-clean or handoff lineage); AMBIGUOUS never authorizes
(aborts or waits); foreign RESOLVED fast-aborts navigation waits and yields
session-fatal UNKNOWN in eligibility (same outcome scoped or global);
overlay-only menu authorizes only through handoff lineage;
post-action transients explicitly tolerated (hub-visible during select);
retryable vs tolerated separated (WB ack: `tolerated` + `retryable False`);
stale snapshots rejected by sequence checks
(`retry_state_not_fresh`, `stale_frame`, `after_sequence` baselines);
recovery invalidates provenance (`on_recovery`, `recovery_after_action`).
**0 BUG.**

## 11. Global analyze count model (per character, steady state, seeds hit)

Always-on globals: ~9 precondition entry observes + ~11–13 session
postcondition re-observes + zone enter/leave hub waits (2 visits when
WB+MW run) + rotation entry + R2-C wait. Per-flow: BM/Daily/Mailbox/
SendStamina/Guild/Summon initials ≈ 0 (seed hits); Daily tab-loop only when
off-tab; claim/completion/return waits scoped. Per-fight: WB combat polling
(S, most frames) + timer/facts (S). Retry/recovery globals: 0 on happy path.
Per-wait frame multipliers: **unknown** — the integral benchmark
(`perception.analyze_summary`) measures them. No invented timings.

## 12. Validation

- Direct + consumer tests for the 3 changes (§7), incl. curated-frame
  equivalence (19 MW hub + 6 foreign frames) and routing assertions.
- `git diff --check`: clean.
- Full hardware-free suite after the changes: **2459/2459 passed**
  (baseline 2451 + 8 new: 3 Summon seed, 1 Daily progress routing, 4 MW
  eligibility scope). Single full run for this audit; prior baseline not
  re-run per AGENTS.md.
- No evaluator/corpus run (no detector/ROI/asset/calibration change).
- No HIL (no physical/timing/geometry dependency; purely logical routing).

## 13. Verdict

**REFACTOR_COMPLETE = YES.** 0 K, 0 D-local and 0 BUG open. Remaining
globals are G (discovery/recovery/trust boundaries), S (temporal/raw/OCR),
J (Daily tab-loop, R2-C, both re-justified), or explicit DEFERs (§5).
STOP — next work is exclusively 28/28 + integral benchmark. Do not re-audit
these sites without a concrete code contradiction.
