# Factory 10 performance observations

Both runs used `python -m verification.check_v9`, the same generated media and
request settings, CPU libx264, and the same Windows machine. Each run was one
observation and shared the host with tests. The edited run measured the local
normalization refactor and initial telemetry. Subsequent caption, validation
checkpoint and manifest changes were tested separately.

- 900-second compilation: 293.22 seconds baseline and 275.11 seconds with the new path, about 6.2% less elapsed time in these runs. Both outputs validated at 900 seconds.
- Connected story: 7.75 seconds baseline and 10.26 seconds with the new path. Both produced parts of 5.67, 5.50 and 5.67 seconds.
- Windows reported 16.31 GB installed memory. Start and end available-memory readings were 4.93 and 5.76 GB on baseline, and 4.92 and 7.10 GB on the edited run. These snapshots do not provide job peaks.
- The detected GPU was an RTX 3050 Laptop GPU with 6,144 MiB VRAM. The benchmark used the CPU encoder. Docker's Linux engine was unavailable. Target GPU and container peaks remain unmeasured.

Machine-local reports can be reproduced in ignored `verification/test-output`.
The observed compilation improvement does not establish a median reduction or
reach the 30% target. Matched text-model workload reduction and real-gameplay
editorial comparisons remain unmeasured.
