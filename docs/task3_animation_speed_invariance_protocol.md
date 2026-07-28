# Task 3 animation-speed invariance protocol

**Contract:** `TASK3_ANIMATION_SPEED_INVARIANCE_V1`  
**Evidence ID:** `OP_INTERACTIVE_REFERENCE_GUI_SPEED_V1`  
**Current state:** `IMPLEMENTED_NOT_EXECUTED`  
**Experiment:** `OperationalInteractive`  
**Claim ceiling:** one fixed scenario/configuration/seed/engine/commit only

## Question and estimand

The test asks whether changing the AnyLogic GUI execution mode changes the
simulation's **model-time result**. It does not ask which mode finishes sooner
in wall-clock time.

The compared evidence is:

- every ordered field in `run_manifest.csv`;
- every ordered traveller/event field in `entity_log.csv`, including arrival,
  queue, service, exit, routing, resource and random-draw fields; and
- every ordered field in `replication_kpis.csv`.

The comparison is exact string equality, not tolerance-based approximate
equality. File paths, filesystem times, capture times, screenshots, window
metadata and optional wall-clock elapsed time are capture provenance and are
excluded from the model-result comparison.

AnyLogic distinguishes real-time mode, where model time is mapped to real
time, from virtual-time mode, where the model runs as fast as possible with no
real-time mapping. The vendor documentation says virtual time is used where
animation is not required. This protocol therefore uses virtual time as the
third, animation-not-required execution condition; it does **not** claim that
the GUI rendered literally zero frames:

- [AnyLogic model time](https://anylogic.help/9/anylogic/running/model-time.html)
- [AnyLogic control panel](https://anylogic.help/9/anylogic/running/control-panel.html)

## Frozen output layout

Each GUI execution first writes to the existing interactive export directory:

```text
results/raw/anylogic_operational/
  INTERACTIVE_D100_SEC036_IMM021_U000_M100/
    LOCAL_WINDOW_HPP_BASE/
      replication_000/
        run_manifest.csv
        entity_log.csv
        replication_kpis.csv
```

Immediately after each run visibly reaches `Finished`, the staging command
copies that export into:

```text
results/raw/animation_speed_invariance/
  OP_INTERACTIVE_REFERENCE_GUI_SPEED_V1/
    01_gui_1x/
    02_gui_10x/
    03_gui_virtual_time/
```

Every mode directory contains the three CSVs, `capture_metadata.json`, and
`ui_finished.png`. Captures are immutable: staging refuses to overwrite a
mode directory. The next capture is also rejected unless all three source CSV
modification times advanced, preventing one completed export from being
mistakenly copied three times.

## Preconditions

1. Save the model, close all old run windows, and record the current Git
   commit:

   ```powershell
   $modelCommit = git rev-parse HEAD
   ```

2. Open:

   ```text
   simulation/anylogic/HTXCheckpointSimulationCLI/
     HTXCheckpointSimulationCLI.alp
   ```

3. Use `OperationalInteractive: OperationalCheckpointModel`.
4. Leave all five pre-run inputs at their canonical values:

   - demand multiplier `1.0`;
   - Security capacity `36`;
   - Immigration capacity `21`;
   - automation uptake `0.0`; and
   - automation multiplier `1.0`.

5. Use one privacy-safe operator role alias, such as `model_owner`; do not
   record a personal name.

## Three executions

Run and stage the modes in the exact order below. Set the speed while the
model is still `Idle`, then press Run. Do not change speed, pause, or edit an
input after the run begins.

### 1. GUI real-time scale 1x

Select real-time `x1`, run until `Finished`, and save a screenshot showing the
finished AnyLogic window and the `x1` control as:

```text
_work/animation_speed_invariance/gui_1x_finished.png
```

Then stage it before another run:

```powershell
.\.venv\Scripts\python.exe `
  -m src.analysis.validate_animation_speed_invariance stage `
  --mode GUI_1X `
  --operator-role model_owner `
  --model-git-commit $modelCommit `
  --ui-evidence _work\animation_speed_invariance\gui_1x_finished.png `
  --confirm-finished
```

### 2. GUI real-time scale 10x

Reopen the experiment, select real-time `x10` while `Idle`, run until
`Finished`, and save:

```text
_work/animation_speed_invariance/gui_10x_finished.png
```

Then:

```powershell
.\.venv\Scripts\python.exe `
  -m src.analysis.validate_animation_speed_invariance stage `
  --mode GUI_10X `
  --operator-role model_owner `
  --model-git-commit $modelCommit `
  --ui-evidence _work\animation_speed_invariance\gui_10x_finished.png `
  --confirm-finished
```

### 3. GUI virtual time

Reopen the experiment, select `Virtual` while `Idle`, run until `Finished`,
and save:

```text
_work/animation_speed_invariance/gui_virtual_finished.png
```

Then:

```powershell
.\.venv\Scripts\python.exe `
  -m src.analysis.validate_animation_speed_invariance stage `
  --mode GUI_VIRTUAL_TIME `
  --operator-role model_owner `
  --model-git-commit $modelCommit `
  --ui-evidence _work\animation_speed_invariance\gui_virtual_finished.png `
  --confirm-finished
```

## Validate and release gate

After all three captures:

```powershell
.\.venv\Scripts\python.exe `
  -m src.analysis.validate_animation_speed_invariance validate
```

The command returns non-zero unless:

- all three directories and five required artifacts per directory exist;
- the mode labels, commit, source directory, capture order and screenshots
  pass;
- all runs are `COMPLETE`, conservation passes, and no traveller is dropped;
- the scenario, configuration, seeds, engine build and model version match;
  and
- all ordered core fields are exactly equal.

Before three genuine runs exist, the only permitted state is
`IMPLEMENTED_NOT_EXECUTED`. Three complete captures with any mismatch become
`EXECUTED_VALIDATION_FAILED`, not accepted evidence. A `PASS` supports only
this bounded statement:

> For the registered interactive reference run, the exported model-time event
> trajectory and KPIs were identical at GUI 1x, GUI 10x and virtual time.

It does not establish wall-clock performance, every-scenario determinism, an
absence of every rendered frame in virtual mode, or input calibration.
