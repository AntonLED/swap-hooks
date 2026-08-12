"""One-level kappa sweep on the revised (2026-08-12) harness.

Runs `experiments.kappa_sensitivity` restricted to turnover 0.1x -- the
informed-heavy level (arbitrage ~half the volume on the pre-revision run),
i.e. the operating point most favourable to the adaptive policies. The full
five-level sweep is deferred until this level answers whether any adaptive
advantage exists at all post-revision.

Writes results/sensitivity/kappa.csv (the contaminated pre-revision sweep is
archived under results-uu-gas-unit-defect/sensitivity-pre-gasfix/).
"""

import experiments.kappa_sensitivity as ks

# Module level, not inside the guard: ProcessPoolExecutor children re-import
# this module under spawn, and the workers must see the same restriction.
ks.TURNOVER_MULTIPLES = (0.1,)

if __name__ == "__main__":
    frame = ks.run(workers=10)
    errors = frame["error"].notna().sum()
    print(f"\nerrors: {errors}")

    print("\n=== flow composition ===")
    print(ks.flow_composition(frame).to_string())

    print("\n=== static curve (mean net_result by level) ===")
    print(ks.static_curve(frame).to_string())

    print("\n=== paired vs MyHook@3000, per policy ===")
    tests = ks.analyse(frame)
    print(tests.to_string())
