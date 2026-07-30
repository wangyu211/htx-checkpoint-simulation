# Release-readiness audit

This gate checks whether one committed revision is self-consistent and passes
the repository release checks from a local Git clone without copying
restricted worktree material. It does not install dependencies, run AnyLogic,
reproduce private-video CV work, or establish cross-platform portability.

## In-worktree diagnostic

On Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe tools\precheck.py `
  --run-tests `
  --check-generator
```

On Linux or macOS:

```bash
.venv/bin/python tools/precheck.py --run-tests --check-generator
```

The generator check creates a temporary snapshot containing only paths
returned by `git ls-files`. It runs the source generator twice there. The
first pass must make no byte change, proving the tracked generated source is
current; the second pass must also make no byte change, proving idempotence.
The real worktree is never generated into by this check.

The release gate also fails on:

- missing compact evidence or required public artifacts;
- broken or untracked local Markdown links;
- case, Unicode-normalization, reserved-name, separator, or path-length
  hazards across ordinary Windows and Linux filesystems;
- absolute Windows paths in tracked text or Office archive members;
- README commands whose Python module, script, requirements file, or AnyLogic
  model input is missing or untracked;
- dependency files without exact `==` pins or with the two incompatible
  OpenCV packages mixed into one environment;
- restricted raw video, model weights, raw/intermediate output, virtual
  environments, or review-work paths in the tracked tree; and
- privacy-policy findings from the dedicated public-release scanner.

## Local Git clean-clone gate

Run this only after every intended release file has been committed:

```powershell
.\.venv\Scripts\python.exe tools\clean_clone_audit.py
```

The tool resolves `HEAD`, requires a clean source worktree, checks reachable
Git history for known restricted path classes, and creates an independent
local Git clone in a temporary directory. A Git clone transfers committed
content; it does not copy ignored worktree files such as:

- `data/raw/TestVidTask.mov`;
- `_work/` review sheets and videos;
- `models/*.onnx`, `models/*.pt`, and `models/*.pth`;
- `results/raw/` and `results/intermediate/`; or
- local virtual environments.

The clone reuses the invoking Python interpreter and its installed packages;
this is a clean Git-content check, not a clean-environment installation test.
Inside that clone, the tool runs the release gate with `--require-clean`, the
complete test suite, and the two-pass generator check. The temporary clone is
deleted after the report. Use `--clone-dir <empty-directory>` only when a
persistent clone is needed for manual inspection.

Diagnostic-only switches `--allow-dirty-source`, `--skip-tests`, and
`--skip-generator` are intentionally visible in the JSON report. A submission
candidate should use none of them.

## What this gate cannot prove

A local Windows pass does not prove that tests pass on a Linux host; execute
the same precheck in an actual Linux clone for that evidence. A local clone
does not prove that the eventual remote URL contains the same commit; after a
remote exists, compare its checked-out commit hash and rerun the gate there.
The audit does not execute AnyLogic GUI experiments, reconstruct ignored raw
entity ledgers, or validate claims that depend on private source video. Those
have separate evidence and review gates.
