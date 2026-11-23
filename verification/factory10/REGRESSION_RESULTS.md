# Factory 10 regression verification

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
