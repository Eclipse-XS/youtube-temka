# Factory 10 release scorecard

**FACTORY_10_RELEASE_CANDIDATE_BLOCKED**

The [machine-readable scorecard](RELEASE_SCORECARD.json) retains the 61 frozen checks and their original weights. A check earns its full weight after all of its conditions are verified. Each of the ten domains must independently reach 85/100. The minimum is 0/100 and the mean of the ten verified domain scores is 8/100. Five P1 release gaps remain open. No P0 was observed.

- **D1–D5** are blocked by held-out GTA footage, independent event annotations and human editorial review. The Neverball exports and controlled tests establish technical behavior for parts of these domains.
- **D6** has verified mixed-source rendering and approved-revision replay. Full renderer acceptance requires the held-out outputs and the remaining decoded-media checks.
- **D7** has a successful local browser-to-export test, including manual text, a caption cue, an effect and a rendered proxy. Multi-source browser acceptance and the complete edit and failure matrix remain open.
- **D8** lacks production time and peak-resource measurements. The earlier matched timing came to an 8.2% cold-cache reduction and a 57.6% warm-cache reduction. [Performance observations](PERFORMANCE.md)
- **D9** has isolated recovery and cancellation regression coverage. The ten-job production pilot remains open. [Regression results](REGRESSION_RESULTS.md)
- **D10** requires three clean controller launches, physical 4 GiB testing, verified private Drive delivery and an isolated upgrade and rollback. [Deployment procedure](DEPLOYMENT_AND_ROLLBACK.md)

## Operator evidence

Run the [acceptance runner](accept_release.py) with the frozen manifest and stable configuration. See the [corpus format and review procedure](EDITORIAL_ACCEPTANCE.md) and the [target-machine commands](TARGET_HARDWARE.md). Keep raw reports and media in a private output directory. For every verified criterion record its input, procedure, observed result, evidence path and tested commit. Leave the release candidate blocked while any mandatory gate remains open.
