# labrats visual identity

## The Concept

The labrat system has two characters:

1. **The Orchestrator** -- a monolithic eye. Watches everything. Allocates budget. Judges results. Inspired by the 2001 monolith: a tall, narrow, impossibly dense slab with a single unblinking eye embedded in it. It doesn't move. It doesn't speak. It just watches and decides.

2. **The Labrats** -- small, busy, scurrying agents. Each branch gets a rat. Running rats have a tail wiggle. Idle rats sit still. They do the actual work: run experiments, collect data, report back to the eye.

## The Inline Rat

```
ᘛ⁐ᕐᐷ
```

That's four unicode characters: `U+1619 U+2050 U+1550 U+1437`. Renders as a tiny side-profile rat in monospace fonts. Works inline in tables, status bars, terminal output.

States:
```
idle:       ᘛ⁐ᕐᐷ
running:    ᘛ⁐ᕐᐷ~
done:       ᘛ⁐ᕐᐷ✓
failed:     ᘛ⁐ᕐᐷ✗
```

Use it next to branch names in the dashboard, in CLI output, in handoff docs. It's small enough to not be distracting but distinct enough to be recognizable.

## The Orchestrator Monolith

A tall narrow slab with an eye. Built from dither/density block characters only: `░▒▓█▀▄`. No regular ASCII. Feels carved from a single piece of dense material.

### Standard (fits in a header, ~18 lines tall)

```
          ▓████████████▓
          █            █
          █  ░▒▓██▓▒░  █
          █ ▒█▀    ▀█▒ █
          █ █ ▓████▓ █ █
          █ █ ██████ █ █
          █ █ ██████ █ █
          █ █ ▓████▓ █ █
          █ ▒█▄    ▄█▒ █
          █  ░▒▓██▓▒░  █
          █            █
          █            █
          █            █
          █            █
          █            █
          █            █
          ▓████████████▓
```

The slab is perfectly rectangular. The eye sits in the upper third -- it's watching, not centered. Below the eye is empty dark space. The density characters create a sense of depth: the eye has layers (░ outer glow, ▒ iris edge, ▓ iris, █ pupil) while the slab is solid █ walls with empty interior.

### Compact (for dashboard header, ~10 lines)

```
        ▓██████████▓
        █          █
        █ ░▒▓██▓▒░ █
        █ █ ████ █ █
        █ █ ████ █ █
        █ ░▒▓██▓▒░ █
        █          █
        █          █
        █          █
        ▓██████████▓
```

### Tiny (for favicon-scale or very small spaces, 6 lines)

```
    ▓████████▓
    █░▒▓██▓▒░█
    █ ██████ █
    █░▒▓██▓▒░█
    █        █
    ▓████████▓
```

## How They Work Together

```
         ▓██████████▓
         █          █
         █ ░▒▓██▓▒░ █          The eye watches.
         █ █ ████ █ █          It allocates budget.
         █ █ ████ █ █          It judges results.
         █ ░▒▓██▓▒░ █          It never blinks.
         █          █
         █          █
         █          █
         ▓██████████▓
              │
    ┌─────────┼─────────┐
    │         │         │
 ᘛ⁐ᕐᐷ~    ᘛ⁐ᕐᐷ~    ᘛ⁐ᕐᐷ
features   model    objectives
 running   running    idle
```

The monolith sits at the top. Rats scurry below, each assigned to a branch. Running rats have the tail wiggle. The monolith doesn't care about individual rats. It cares about results.

## Dashboard Integration

**Header**: Compact monolith (10-line version) floated left of the title. Title reads "LABRAT" with "labrats" in smaller muted text below.

**Branch table**: Each branch row has a `ᘛ⁐ᕐᐷ` (or `ᘛ⁐ᕐᐷ~` when running) next to the agent name.

**Status bar**: Bottom bar shows `ᘛ⁐ᕐᐷ × 3 running` or `all rats idle`.

**Experiment log**: Verdicts can optionally show `ᘛ⁐ᕐᐷ✓ PROMOTE` or `ᘛ⁐ᕐᐷ✗ REJECT`.

## Color Rules

None. Everything is black on white. The dither characters (░▒▓█) provide all the visual texture needed. The monolith is solid. The rats are line-drawn. No gradients, no color, no images.

## The Name

**labrat**: the system (how budgets flow, how branches compete).
**labrats**: the agents (the ones doing the actual experiments).

The monolith is the market. The rats are the researchers. The market doesn't do research. It funds research. The rats don't allocate budget. They spend it.
