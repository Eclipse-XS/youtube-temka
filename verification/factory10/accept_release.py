"""Run authorized Factory 10 jobs in an isolated workspace and record release evidence."""
import argparse
from collections import Counter
from hashlib import file_digest
import json
import math
import os
from pathlib import Path
import platform
import shutil
from statistics import median
import sys
import time
from urllib.parse import urlsplit

from acceptance_metrics import evaluate


HERE = Path(__file__).resolve().parent
POSITIVE_CATEGORIES = {'npc_behavior', 'vehicle_crash', 'stunt_fail', 'ragdoll', 'physics_glitch',
                       'unexpected_survival', 'silent_visual_comedy'}
NEGATIVE_CATEGORIES = {'ordinary_driving', 'continuous_gunfire', 'camera_rotation', 'walking',
                       'scene_transition', 'routine_gameplay', 'loud_uneventful'}


def outcome(status, detail, **evidence):
    return {'status': status, 'detail': detail, **evidence}


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha256(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def index(records):
    result = {record['id']: record for record in records}
    if len(result) != len(records) or any(not isinstance(key, str) or not key for key in result):
        raise ValueError('Corpus and workload IDs must be unique, nonempty strings')
    return result


def interval(value):
    start, end = value
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= 86400):
        raise ValueError('Use valid nonnegative source intervals in seconds')
    return start, end


def inspect_corpus(corpus, root, mode):
    if corpus['schema_version'] != 1:
        raise ValueError('Unsupported corpus schema version')
    sources = index(corpus['sources'])
    jobs = [job for job in index(corpus['jobs']).values() if job['split'] == mode]
    for source in sources.values():
        if source['authorized'] is not True or not source['session']:
            raise ValueError(f"Source {source['id']} requires authorized use and a session identifier")
        if ('file' in source) == ('url' in source):
            raise ValueError(f"Source {source['id']} requires exactly one file or URL")
        if 'file' in source:
            path = (root / source['file']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError(f"Source {source['id']} is missing from the authorized corpus directory")
            source['path'] = path
        else:
            url = urlsplit(source['url'])
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError(f"Source {source['id']} requires an authorized HTTPS media URL")
    sessions = {}
    input_splits = {}
    for job in corpus['jobs']:
        for window in job['windows']:
            source = sources[window['source']]
            interval([window['start'], window['end']])
            sessions.setdefault(source['session'], set()).add(job['split'])
            identity = source.get('path', source.get('url'))
            input_splits.setdefault(identity, set()).add(job['split'])
    if any(splits >= {'development', 'acceptance'} for splits in [*sessions.values(), *input_splits.values()]):
        raise ValueError('Development and held-out acceptance must use separate files and sessions')
    for job in jobs:
        windows = job['windows']
        if job['kind'] not in {'shorts', 'longs', 'edit'} or not windows:
            raise ValueError(f"Unsupported or empty job {job['id']}")
        if job['kind'] == 'longs' and len({window['source'] for window in windows}) < 2:
            raise ValueError(f"Longs job {job['id']} needs two independent sources")
        if job['kind'] != 'longs' and len(windows) != 1:
            raise ValueError(f"Shorts job {job['id']} needs one source range")
        if job['kind'] == 'shorts' and not 1 <= job['k'] <= 20:
            raise ValueError(f"Shorts job {job['id']} needs a frozen K from 1 to 20")
    return sources, jobs


def held_out_requirements(corpus, sources, jobs):
    shorts = [job for job in jobs if job['kind'] == 'shorts']
    longs = [job for job in jobs if job['kind'] == 'longs']
    windows = [job['windows'][0] for job in shorts]
    participating = {window['source'] for window in windows}
    involved = {window['source'] for job in jobs for window in job['windows']}
    for source_id in involved:
        if sources[source_id].get('game') not in ('GTA V', 'GTA VI'):
            raise ValueError(f'Held-out source {source_id} must be authorized GTA V or GTA VI gameplay')
    for window in windows:
        related = [other for other in windows if other['source'] == window['source'] and other is not window]
        if any(max(other['start'], window['start']) < min(other['end'], window['end']) for other in related):
            raise ValueError('Held-out Shorts scan ranges must not overlap')
    positives = [record for record in index(corpus['positive_events']).values() if record['source'] in participating]
    negatives = [record for record in index(corpus['negative_examples']).values() if record['source'] in participating]

    def in_coverage(source, bounds):
        return any(window['source'] == source and window['start'] <= bounds[0] < bounds[1] <= window['end']
                   for window in windows)

    for event in positives:
        setup = interval(event['setup'])
        essential = interval(event['essential'])
        payoff = interval(event['payoff']) if event['payoff'] is not None else None
        covered = (setup, essential, payoff) if payoff else (setup, essential)
        full_span = (min(bounds[0] for bounds in covered), max(bounds[1] for bounds in covered))
        if not (in_coverage(event['source'], full_span) and setup[0] <= event['original_timestamp'] <= full_span[1]
                and essential[0] <= event['trigger'] < essential[1] and event['description'].strip()
                and all(isinstance(event[flag], bool) for flag in ('speech_necessary', 'reframing_risk',
                                                                 'low_motion_or_silent', 'delayed_payoff'))):
            raise ValueError(f"Incomplete held-out annotation {event['id']}")
    for item in negatives:
        if not in_coverage(item['source'], interval(item['interval'])):
            raise ValueError(f"Negative example {item['id']} is outside its held-out scan range")
    sessions = {sources[window['source']]['session'] for window in windows}
    long_sources = [{window['source'] for window in job['windows']} for job in longs]
    missing = []
    for passed, requirement in (
        (len(positives) >= 30, '30 independent positive annotations'),
        (len(negatives) >= 20, '20 negative annotations'),
        (POSITIVE_CATEGORIES <= {event['category'] for event in positives}, 'all positive categories'),
        (NEGATIVE_CATEGORIES <= {item['category'] for item in negatives}, 'all negative categories'),
        (len(sessions) >= 8 or len(windows) >= 8, 'eight independent sessions or intervals'),
        (sum(event['low_motion_or_silent'] for event in positives) >= 5, 'five silent or low-motion events'),
        (sum(event['delayed_payoff'] and bool(event['payoff']) for event in positives) >= 5, 'five delayed payoffs'),
        (sum(job['k'] for job in shorts) >= 10, 'ten automatic Shorts'),
        (any(not left.intersection(right) for i, left in enumerate(long_sources) for right in long_sources[i + 1:]),
         'two independent multi-source Longs jobs'),
        (any(job['kind'] == 'edit' for job in jobs), 'one edited rerender'),
        (any('url' in sources[source_id] for source_id in involved), 'one authorized remote-source workflow'),
    ):
        if not passed:
            missing.append(requirement)
    return positives, negatives, missing


def drive_available():
    def configured(key):
        return bool(os.environ.get(key) and Path(os.environ[key]).is_file())

    return (bool(os.environ.get('DRIVE_PARENT_ID')) and
            (configured('DRIVE_TOKEN_FILE') or
             (configured('DRIVE_OAUTH_TOKEN_FILE') and configured('DRIVE_OAUTH_CLIENT_FILE'))))


class Runner:
    def __init__(self, profile, sources, drive, output):
        from factory import config, pipeline, store
        from factory.models import JobRequest

        self.config = config
        self.pipeline = pipeline
        self.store = store
        self.request_type = JobRequest
        self.profile = profile
        self.sources = sources
        self.drive = drive
        self.output = output

    def prepare(self, workspace):
        self.config.DATA = workspace
        self.config.SCRATCH = workspace / 'scratch'
        self.config.DB = workspace / 'jobs.sqlite3'
        self.uploads = self.config.SCRATCH / 'uploads'
        self.uploads.mkdir(parents=True, exist_ok=True)

    def source(self, key):
        entry = self.sources[key]
        if 'url' in entry:
            return entry['url']
        original = entry['path']
        number = list(self.sources).index(key) + 1
        target = self.uploads / f'corpus-{number}{original.suffix.lower()}'
        if not target.is_file():
            try:
                os.link(original, target)
            except OSError:
                shutil.copyfile(original, target)
        return 'upload:' + target.name

    def request(self, job):
        longs = job['kind'] == 'longs'
        settings = {**self.profile['job_defaults'], **self.profile['longs' if longs else 'shorts'],
                    **job.get('settings', {})}
        sources = [{**{key: value for key, value in window.items() if key != 'source'},
                    'source': self.source(window['source']), 'source_id': f'source-{i}'}
                   for i, window in enumerate(job['windows'], 1)]
        if not longs:
            settings.update(start=sources[0]['start'], end=sources[0]['end'], count=job.get('k', 1))
        settings.update(source=sources[0]['source'], workflow='compilation' if longs else 'highlights',
                        sources=sources if longs else [], mode='longs' if longs else 'shorts',
                        destination='video' if longs else 'youtube_shorts', intervals=[], rights_confirmed=True,
                        publish_automatic=False, publish_channel=None, save_drive=self.drive and job.get('drive', False),
                        review_before_render=job['kind'] == 'edit')
        return self.request_type.model_validate(settings)

    def process(self, job_id):
        # Let the same persisted claim/retry/fencing logic drive local verification.
        for _ in range(self.config.AUTOMATIC_RETRIES + 1):
            state = self.store.get(job_id)
            delay = min(60.0, max(0, (state['result'].get('retry_at') or 0) - time.time()))
            if delay:
                time.sleep(delay)
            claim = self.store.claim('factory10-acceptance')
            if claim is None or claim['job']['id'] != job_id:
                raise RuntimeError('Expected job is not claimable in the isolated acceptance workspace')
            self.pipeline.process(claim)
            state = self.store.get(job_id)
            if state['state'] != 'QUEUED':
                return state
        return state

    def evidence(self, state):
        job_id, result = state['id'], state['result']
        root = self.config.SCRATCH / job_id
        details = {key: result.get(key) for key in ('signal_coverage', 'candidates', 'proposal_count', 'sources',
                                                     'narrative_plan', 'cache_hits', 'actual_duration',
                                                     'cloud_verified', 'publishing_state', 'failure')}
        details['outputs'] = [{key: item.get(key) for key in ('name', 'validation', 'duration', 'output_hash', 'hook')}
                              for item in result.get('outputs', [])]
        details['artifact_directory'] = root.relative_to(self.output).as_posix()
        for name, filename in (('render', 'reproducibility.json'), ('timeline', 'timeline.json')):
            path = root / filename
            if path.is_file():
                details[name] = load(path)
        details['operations'] = self.store.operations(job_id)
        return {'state': state['state'], 'error': state['error'], **details}

    def edit(self, state):
        job_id = state['id']
        plan = state['result']['edit_plan']
        edits = [{key: scene[key] for key in ('id', 'start_seconds', 'end_seconds', 'transition')}
                 for scene in plan['segments']]
        initial = self.store.edit_plan(job_id, plan['revision'], edits, None, approve=True)
        approved = self.process(job_id)
        if approved['state'] != 'READY':
            return approved, None
        first = self.evidence(approved)
        edits[0]['hook'] = {'text': 'FACTORY REVIEW', 'start': 0.5, 'end': 2}
        revision = self.store.edit_plan(job_id, initial['revision'], edits, None, preview=True)
        started = time.perf_counter()
        preview = self.process(job_id)
        preview_seconds = time.perf_counter() - started
        proxy = preview['result'].get('preview')
        if not proxy or preview['state'] != 'REVIEW':
            return preview, {'original': first}
        self.store.edit_plan(job_id, revision['revision'], edits, None, approve=True)
        started = time.perf_counter()
        final = self.process(job_id)
        return final, {'original': first, 'preview': proxy, 'preview_seconds': round(preview_seconds, 3),
                       'render_seconds': round(time.perf_counter() - started, 3)}

    def run(self, job):
        try:
            request = self.request(job)
            saved = self.store.create(request.model_dump())
            started = time.perf_counter()
            state = self.process(saved['id'])
            revision = None
            if job['kind'] == 'edit' and state['state'] == 'REVIEW' and state['result'].get('edit_plan'):
                state, revision = self.edit(state)
            seconds = round(time.perf_counter() - started, 3)
            evidence = self.evidence(state)
            ready = state['state'] == 'READY' and bool(evidence['outputs'])
            if request.save_drive:
                ready = ready and evidence['cloud_verified'] is True
            if job['kind'] == 'longs' and job['split'] != 'development':
                ready = ready and all(480 <= item['duration'] <= 900 for item in evidence['outputs'])
            if job['kind'] == 'shorts':
                ready = ready and len(evidence['outputs']) == job['k']
            if job['kind'] == 'edit':
                ready = ready and bool(revision and revision.get('preview'))
            if job['split'] == 'benchmark' and job['kind'] != 'edit':
                completed = any(item.get('model_type') == 'visual' and item['status'] == 'completed'
                                for item in (evidence.get('render') or {}).get('inference', []))
                cached = bool((evidence.get('cache_hits') or {}).get('candidate_discovery'))
                evidence['vision_inference_completed'] = completed
                ready = ready and (completed or cached)
            return outcome('PASS' if ready else 'FAIL', 'Automatic technical output check', job=job['id'],
                           kind=job['kind'], seconds=seconds, revision=revision, **evidence)
        except (OSError, RuntimeError, ValueError, KeyError, InterruptedError) as exc:
            return outcome('FAIL', 'Job setup or execution failed', job=job['id'], kind=job['kind'],
                           error_type=type(exc).__name__)


def check_workloads(jobs):
    kinds = Counter(job['kind'] for job in jobs)
    if kinds['shorts'] != 1 or kinds['longs'] != 1:
        raise ValueError('Use exactly one benchmark Shorts job and one benchmark Longs job')
    for job in jobs:
        seconds = sum(window['end'] - window['start'] for window in job['windows'])
        if job['kind'] == 'shorts' and (seconds != 1800 or job['k'] != 3):
            raise ValueError('Shorts benchmark requires 30 minutes of source and K=3')
        if job['kind'] == 'longs' and not 3600 <= seconds <= 5400:
            raise ValueError('Longs benchmark requires 60–90 minutes of selected source ranges')


def benchmark(runner, out, jobs, result, save):
    for job in jobs:
        if job['kind'] == 'edit':
            runner.prepare(out / 'benchmark-edits')
            result['jobs'].append(runner.run(job))
            save()
            continue
        measured = {'cold': [], 'warm': []}
        result['benchmarks'][job['id']] = measured
        for number in range(1, 4):
            runner.prepare(out / f"benchmark-{job['kind']}-cold-{number}")
            measured['cold'].append(runner.run(job))
            save()
        runner.prepare(out / f"benchmark-{job['kind']}-warm")
        measured['priming'] = runner.run(job)
        for _ in range(3):
            measured['warm'].append(runner.run(job))
            save()
        for condition in ('cold', 'warm'):
            entries = measured[condition]
            times = [entry['seconds'] for entry in entries if 'seconds' in entry]
            measured[f'{condition}_median_seconds'] = median(times) if len(times) == 3 else None
            measured[f'{condition}_max_seconds'] = max(times) if times else None
        limits = (1800, 2700) if job['kind'] == 'shorts' else (5400, 7200)
        cold = (measured['cold_median_seconds'], measured['cold_max_seconds'])
        passed = (all(entry['status'] == 'PASS' and entry.get('vision_inference_completed')
                      for entry in measured['cold']) and
                  all(value is not None and value <= limit for value, limit in zip(cold, limits)))
        result['checks']['D8.1' if job['kind'] == 'shorts' else 'D8.2'] = outcome(
            'PASS' if passed else 'FAIL', 'Absolute cold-cache time budget', median_seconds=cold[0], maximum_seconds=cold[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=HERE / 'ACCEPTANCE_CORPUS.json')
    parser.add_argument('--corpus-root', type=Path)
    parser.add_argument('--config', type=Path, default=HERE / 'STABLE_PROFILE.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('development', 'acceptance', 'benchmark'), default='acceptance')
    parser.add_argument('--hardware-profile', choices=('development', 'rtx3050-4gib'), default='rtx3050-4gib')
    parser.add_argument('--ollama', default=os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434'))
    parser.add_argument('--enable-drive', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ.update(PYTHON_DOTENV_DISABLED='1', FACTORY_DATA=str(out / 'initial'),
                      FACTORY_SCRATCH=str(out / 'initial' / 'scratch'), FACTORY_HOST_LOCK_DIR=str(out / 'locks'),
                      OLLAMA_URL=args.ollama)
    sys.path.insert(0, str(HERE.parents[1]))

    from factory.reproducibility import application_commit
    from factory.resources import gpu_status, memory_status
    from jsonfile import write_json_atomic

    result = {'schema_version': 1, 'mode': args.mode, 'commit': application_commit(), 'jobs': [], 'benchmarks': {},
              'checks': {}, 'hardware': {'os': platform.system(), 'release': platform.release(),
                                         'profile': args.hardware_profile, 'gpu': gpu_status(), 'memory': memory_status()}}
    checks = result['checks']

    def save():
        write_json_atomic(out / 'results.json', result, ensure_ascii=False)

    try:
        profile = load(args.config)
        os.environ['FFMPEG_ENCODER'] = profile['encoder']
        corpus = load(args.corpus)
        result['corpus_sha256'] = sha256(args.corpus)
        result['profile_sha256'] = sha256(args.config)
        root = (args.corpus_root or args.corpus.resolve().parent).resolve()
        sources, jobs = inspect_corpus(corpus, root, args.mode)
        positives, negatives, missing = held_out_requirements(corpus, sources, jobs) if args.mode == 'acceptance' else ([], [], [])
        checks['corpus'] = outcome('BLOCKED' if missing or not jobs else 'PASS',
                                   'Corpus prerequisites', missing=missing or ([] if jobs else ['configured jobs']))
        gpu = result['hardware']['gpu'] or {}
        target_gpu = 'RTX 3050' in gpu.get('name', '') and gpu.get('total_mib') == 4096
        target_status = 'PASS' if target_gpu else 'BLOCKED' if args.hardware_profile == 'rtx3050-4gib' else 'UNVERIFIED'
        checks['target_gpu_probe'] = outcome(target_status, 'Physical RTX 3050 4096 MiB detection')
        checks['drive'] = outcome('UNVERIFIED', 'Live Drive delivery has not run')
        run_drive = args.enable_drive and drive_available()
        if args.enable_drive and not run_drive:
            checks['drive'] = outcome('BLOCKED', 'A private DRIVE_PARENT_ID and authorized read-only credentials are required')
        if missing or not jobs or (args.hardware_profile == 'rtx3050-4gib' and not target_gpu and args.mode == 'benchmark'):
            save()
            return 2
        runner = Runner(profile, sources, run_drive, out)
        if args.mode == 'benchmark':
            check_workloads(jobs)
            benchmark(runner, out, jobs, result, save)
            if not target_gpu:
                for key in ('D8.1', 'D8.2'):
                    checks[key]['status'] = 'BLOCKED'
                    checks[key]['detail'] += ' on the target 4 GiB device'
        else:
            runner.prepare(out / 'jobs')
            ranked = []
            for job in jobs:
                evidence = runner.run(job)
                result['jobs'].append(evidence)
                if job['kind'] == 'shorts':
                    window = job['windows'][0]
                    candidates = (evidence.get('candidates') or [])[:job['k']]
                    ranked.extend({'source': window['source'], 'start': item['start_seconds'] + window['start'],
                                   'end': item['end_seconds'] + window['start']} for item in candidates)
                save()
            if args.mode == 'acceptance':
                result['fixed_k'] = {job['id']: job['k'] for job in jobs if job['kind'] == 'shorts'}
                result['detection'] = evaluate(ranked, positives, negatives)
                for key, metric, limit in (('D1.1', 'recall_at_k', .85), ('D1.2', 'precision_at_k', .75),
                                           ('D1.3', 'low_motion_recall', .80), ('D1.4', 'payoff_preservation', .95)):
                    value = result['detection'][metric]
                    checks[key] = outcome('UNVERIFIED' if value is None else 'PASS' if value >= limit else 'FAIL',
                                          metric, value=value)
                checks['human_editorial'] = outcome('BLOCKED', 'Independent timestamped Short and Longs reviews required')
        if run_drive:
            delivered_jobs = result['jobs'] + [entry for workload in result['benchmarks'].values()
                                               for label in ('cold', 'warm') for entry in workload[label]]
            verified = {job['kind'] for job in delivered_jobs if job.get('cloud_verified') is True}
            attempted = any(job.get('drive') for job in jobs)
            status = 'PASS' if {'shorts', 'longs'} <= verified else 'FAIL' if attempted else 'UNVERIFIED'
            checks['drive'] = outcome(status,
                                      'Private Short and Longs checksum verification', verified=sorted(verified))
        save()
    except (KeyError, TypeError, OSError, ValueError) as exc:
        checks['configuration'] = outcome('BLOCKED', str(exc))
        save()
        return 2
    print(out / 'results.json')
    failures = any(item['status'] == 'FAIL' for item in [*checks.values(), *result['jobs']])
    return 1 if failures else 2 if any(item['status'] == 'BLOCKED' for item in checks.values()) else 0


if __name__ == '__main__':
    raise SystemExit(main())
