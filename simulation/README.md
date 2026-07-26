# Simulation implementation

## Selected primary engine

AnyLogic PLE 8.9.9 for Windows x64 is the selected primary engine, subject to
the technical smoke gate below. The installed build is
`8.9.9.202607020720` with its bundled Eclipse Adoptium Java 17.0.9. The final
ALPX model and engine-specific run notes will live in
`simulation/anylogic/`.

The official installer is available from:

<https://www.anylogic.com/files/anylogic-ple-8.9.9.x86_64.exe>

AnyLogic PLE is used solely as a personal, non-production skills
demonstration. It remains governed by AnyLogic's software license agreement;
this repository does not grant operational, commercial, or research reuse
rights for the engine or model.

## Gate before model commitment

The minimum prototype must demonstrate:

1. two input samples × three stochastic replications;
2. explicit `scenario_id`, `input_sample_id`, `replication_id`, and seed lineage
   in every exported row;
3. entity and replication CSV output with fixed schemas;
4. repeat execution of one manifest produces identical output;
5. different replication IDs produce different stochastic draws;
6. serial export is race-free; parallel execution, if used, writes one file per
   run before deterministic aggregation; and
7. the documented GUI and `AnyLogic.exe -r <model.alp> <experiment>` paths are
   tested rather than assumed.

The gate is time-boxed. If repeatable batch execution, correct export, or seed
lineage cannot be verified, the implementation switches to the open-source
fallback while preserving `docs/task2_system_design.md` and the same data
contract.

## Open-source fallback

The fallback is a Python event-driven engine with a lightweight browser UI. It
must still provide:

- the two-stage Security → Immigration DES;
- genuinely separate and pooled Immigration queues;
- finite resources, technology mixture, and additional checks;
- reset/re-run controls, a primitive 2D state view, and dashboard;
- identical parameter/scenario keys and output schemas; and
- replicated experiments, verification tests, and result figures.

Fallback is an implementation decision, not a reduction in the research
design.
