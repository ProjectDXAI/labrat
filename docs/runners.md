# Running `labrat` With Agents

`labrat` is built first for **Claude Code** and **Codex**.

Both runners use the same lab-local files:

- `agent_prompts/` for the operating prompts
- `orchestrator.md` for the cycle contract
- `research_brief.md` and `research_sources.md` for the preserved knowledge trail
- `state/` for the live state
- `scripts/operator_helper.py` for readiness checks, status, and next-prompt selection
- `implementation_audit.md` when the helper routes into audit mode

## Shared Operating Model

For a new lab:

1. scaffold the lab
2. run Phase 0 deep research
3. define cheap probes, audit policy, and formulation-change triggers
4. confirm readiness
5. bootstrap
6. start autonomous cycles

For an existing lab:

1. run `python scripts/operator_helper.py status`
2. run `python scripts/operator_helper.py next-prompt --runner ... --phase auto`
3. give that prompt to the agent

## Claude Code

Claude Code is the cleanest fit for long-running loops and parallel branch work.

### Phase 0

```bash
python scripts/operator_helper.py next-prompt --runner claude --phase design
```

### Normal operation

```bash
python scripts/operator_helper.py status
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

### Repeated cycles

After the lab is bootstrapped and stable, reuse the cycle prompt with `/loop`.

Cadence defaults:

- fast CPU labs: `/loop 5m` to `/loop 10m`
- medium experiments: `/loop 30m`
- long GPU runs: `/loop 1h`

## Codex

Codex works well for the same workflow, but it relies more on the helper prompts and thread continuity than on a built-in `/loop` pattern.

### Phase 0

```bash
python scripts/operator_helper.py next-prompt --runner codex --phase design
```

### Normal operation

```bash
python scripts/operator_helper.py status
python scripts/operator_helper.py next-prompt --runner codex --phase auto
```

### Repeated cycles

Reuse the same thread and keep handing Codex the next helper-generated prompt. If you want scheduled runs in Codex desktop, use an automation that reuses the same helper command and prompt path.

## Scout, Audit, And Expansion Phases

When the helper routes the lab into audit mode:

```bash
python scripts/operator_helper.py next-prompt --runner claude --phase audit
```

Or:

```bash
python scripts/operator_helper.py next-prompt --runner codex --phase audit
```

When the helper routes the lab into scout or expansion mode:

```bash
python scripts/operator_helper.py prepare-scout --all-stuck
python scripts/operator_helper.py next-prompt --runner claude --phase scout
```

Or:

```bash
python scripts/operator_helper.py prepare-scout --expansion
python scripts/operator_helper.py next-prompt --runner codex --phase expansion
```

`auto` may now resolve to `design`, `cycle`, `audit`, `scout`, `frame_break`, `expansion`, or `checkpoint` depending on the lab state.

## Dashboard

The static dashboard is always the baseline path:

```bash
python -m http.server 8787
```

The React dashboard remains optional:

```bash
cd dashboard-app
npm install
npm run dev
```
