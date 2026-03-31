# Dead Ends

Known approaches that don't work for this problem. Saves compute by preventing re-exploration.

The orchestrator checks this file before generating new experiments.
The research scout checks this file before proposing new approaches.
The tree designer populates this during initial design.

## Format

Each entry should include:
- **What** was tried
- **Why** it failed (metric, reason)
- **Source** (experiment ID, paper, prior lab)
- **Confidence** (high: tested 3+ times, medium: tested once, low: theoretical)

```
- **[Approach]**: Why it failed. Source: [experiment_id / paper / prior lab]. Confidence: [high/medium/low].
```

## Revival Conditions

Dead ends can be revived if:
- New data becomes available that changes the problem structure
- A complementary technique is discovered that addresses the failure mode
- The scoring metric changes (what failed under old metric might work under new one)

When reviving, add a note: `Revived cycle N: [reason]`

## Entries (delete examples and add your own)

- **[Approach X]**: Reason it failed. Source: experiment. Confidence: high.
- **[Approach Y]**: Reason it failed. Source: paper. Confidence: medium.

## How to Populate

1. **Tree designer** populates during initial design (from web search + domain knowledge)
2. **Orchestrator** adds entries as experiments fail during the lab run (auto, Step 7f)
3. **Research scout** checks before proposing (avoids known failures)
4. **Expansion scout** checks before proposing new branches
5. **Parent lab inheritance**: `bootstrap.py --inherit-from` copies parent dead ends

## Inherited Dead Ends

If this lab inherited from a parent, those entries appear below this line.
