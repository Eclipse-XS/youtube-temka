# Factory 10 regression verification

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
