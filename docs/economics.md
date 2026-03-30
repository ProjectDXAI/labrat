# Budget Economics

## Abstract Mode (Default)

Credits are dimensionless. Each experiment costs 1. Branches start with 10-30 credits. Replenishment adds 5 base + 3 bonus for productive branches. Cap at 30.

## Cost-Aware Mode

Map credits to real costs:

```yaml
branches:
  architecture:
    cost_per_experiment: 50.0  # dollars (H100 training)
    initial_budget: 500.0
  data:
    cost_per_experiment: 2.0   # dollars (preprocessing)
    initial_budget: 100.0
```

The allocator asks: "Is a $50 architecture experiment more likely to improve the score than 25 data experiments at $2 each?"

## Important Disclaimer

Credits are synthetic. The allocator makes best-effort decisions based on improvement rates and uncertainty, but it is not a financial system. If you map to real dollars:

- Enforce hard spending limits on your infrastructure side
- The allocator can over-allocate to branches that look productive but aren't
- Treat budget as a prioritization signal, not an accounting system
- Your cloud billing alerts and quota limits are the real guardrails
