# Factory 10 regression verification

## Stable-candidate verification on 2026-11-25

- The Linux baseline at `ad163576e3037fbf883bd9b4f3cabb812ba7f124` passed 2,307 tests, skipped 66 and failed zero in 214.06 seconds. The existing worker image ran a tracked read-only snapshot with the documented Linux regression dependencies.
- Candidate `3a713c91885caed50c082d092fe99c1af3d16ab2` passed 2,313 Linux tests, skipped 66 and failed zero in 249.77 seconds. The latest code passed all 14 Factory 10 tests on Windows, including six new regressions for localized motion, black lead-ins, budget fairness and adaptive frame indices, overlapping source ranges, one-to-one detection scoring and the 100 ms A/V end-alignment check.
- The first run at `ac32ab0f2780e83d5b60e19a83cd7474eb28d122` passed 2,312, skipped 66 and failed one in 242.18 seconds. `test_resume_scan_reads_manifests_off_the_loop` recorded a 163 ms stall against a strict 150 ms limit while the isolated vision and browser workloads were active. The test and upstream queue implementation are identical to the baseline.
- After stopping the separate vision and browser workloads, the affected test passed in 2.41 seconds. The full repeat at the same `ac32ab0` revision passed 2,313, skipped 66 and failed zero in 208.51 seconds. The local logs are `scratch/f10-stable-regression-ac32ab0.log` and `scratch/f10-stable-regression-ac32ab0-isolated.log`.
- The dashboard production build and both CPU/GPU Compose configurations passed. ESLint for the changed Create page reported the same 12 pre-existing errors and two warnings at the baseline and candidate.
- The isolated Linux regression command pins the implementation SHA in the snapshot and reproducibility metadata.

```powershell
$factory10Commit = 'ac32ab0f2780e83d5b60e19a83cd7474eb28d122'
git archive --format=tar -o scratch/f10-stable-release-ac32ab0.tar $factory10Commit
$factory10Snapshot = (Resolve-Path scratch/f10-stable-release-ac32ab0.tar).Path
docker run --rm --user root --env PYTHON_DOTENV_DISABLED=1 --env FACTORY_BUILD_COMMIT=$factory10Commit --mount "type=bind,source=$factory10Snapshot,target=/snapshot.tar,readonly" --entrypoint sh youtube-temka-worker:latest -lc 'set -e; mkdir -p /tmp/repo /data/scratch; tar -xf /snapshot.tar -C /tmp/repo; cd /tmp/repo; python -m pip install -q --no-cache-dir -r requirements-billing.txt boto3==1.43.4 Pillow==13.0.0 google-genai==1.75.0 py3langid==0.3.0; python -m pytest -q factory_tests tests'
```

The representative ten-job pilot requires held-out local and remote gameplay and private Drive access. Predeclare the jobs in the manifest, run them consecutively with the final build and retain their outputs and final states. Include gameplay Shorts, multi-source Longs, captioned and silent inputs, a remote input, an edited rerender, and successful storage delivery. The current isolated Neverball run does not meet the production workload mix.

## Continuation verification

The current implementation was tested in the existing Linux Factory worker
image from a tracked repository snapshot at
`dbe0f229fb3276f074aa4de64abbdfc4a6d27e17`. The snapshot excludes local
secrets and host state. The full Linux run reported 2,307 passed, 66 skipped
and zero failed in 450.16 seconds. It includes the two previously blocked
subtitle API checks. The Factory dashboard build, edited editor lint and
Compose configuration passed.

```powershell
git archive --format=tar -o scratch/factory10-final-linux.tar dbe0f229fb3276f074aa4de64abbdfc4a6d27e17
$snapshot=(Resolve-Path scratch/factory10-final-linux.tar).Path
docker run --rm --user root --env FACTORY_BUILD_COMMIT=dbe0f229fb3276f074aa4de64abbdfc4a6d27e17 --mount "type=bind,source=$snapshot,target=/snapshot.tar,readonly" --entrypoint sh youtube-temka-worker:latest -lc 'set -e; mkdir -p /tmp/repo /data/scratch; tar -xf /snapshot.tar -C /tmp/repo; cd /tmp/repo; python -m pip install -q --no-cache-dir -r requirements-billing.txt boto3==1.43.4 Pillow==13.0.0 google-genai==1.75.0 py3langid==0.3.0; PYTHON_DOTENV_DISABLED=1 python -m pytest -q factory_tests tests'
```

## Earlier Factory 10 milestone

Run from the repository root with the Factory virtual environment.

```powershell
.venv/Scripts/python.exe -m pytest factory_tests -xq -p no:cacheprovider --basetemp scratch/f10-verified
.venv/Scripts/python.exe -m pytest factory_tests/test_factory10.py factory_tests/test_workflows.py -xq -p no:cacheprovider --basetemp scratch/f10-recheck
.venv/Scripts/python.exe -m compileall -q factory
docker compose config --quiet
Set-Location dashboard
npm run build -- --config vite.factory.config.js
```

The full Factory run passed 196 tests in 169.75 seconds. The focused Factory
run passed nine tests. It covers operation persistence and
attempts, cancellation, streamed model metrics, model budgets after retry,
rendering a full-range gameplay scan, visual evidence schema checks, reusable
word timings, compilation edit revisions, and restart recovery. The dashboard
production build, Compose configuration and Python compilation passed.

Five tests in `tests/test_caption_presets.py` passed. The Factory environment
initially lacked `boto3`. After installing the pinned dependency under the
ignored scratch directory and rerunning with the local `.env` disabled, two
app-level tests remained blocked by the upstream worker's POSIX-only `fcntl`
import on Windows.

An earlier run exposed a render-path import shadowing bug. The implementation
was corrected and tested again. Windows FastAPI TestClient needs permission to
use localhost sockets. Its fixture data lives in isolated scratch directories.
