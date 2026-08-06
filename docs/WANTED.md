# Wanted: what to go looking for

A brief for a human with access I do not have. Written to be acted on out of order — take
whatever is cheap for you and ignore the rest. Every item says **why I want it** and **what
counts as bringing it back**, because a link with no context costs more to process than it saves.

The corpus is at 468 mapped sources, 68 units read, 25 structural findings. Reading is the binding
constraint and always has been; adding entries to the bibliography has never once produced a
finding. So this is a list of things to *read* or *retrieve*, not things to catalogue.

---

## 1. Things I literally cannot reach

Highest value per unit of your effort, because no amount of my searching substitutes.

| What | Why it matters | What counts as bringing it back |
|---|---|---|
| `/Users/punkyrest/polymarket-mm` | The only account of how we actually make markets. Every proposal I write about the MM implementation is currently invented rather than read, and `knowledge extensions` refuses to rank it for exactly that reason. | Push to a repo I can attach, or paste the README plus the core strategy/quoting module. Even the config schema is useful — it names the parameters we think matter. |
| `/Users/punkyrest/Documents/HyperLiquidL4Collection` | The L4 collection itself. I read `ProjectDXAI/hyperliquid-ingest`, which is the capture service, not the collection. | A repo, or a description of what levels/fields are collected and at what cadence. |
| `/Users/punkyrest/DXT Reports` | Whatever conclusions have already been reached. I risk re-deriving them. | Any format. Even a table of contents tells me what not to spend reading on. |
| Sessions' acquired PDFs | A parallel session gathered ~295 PDFs; they live outside git by design, so a fresh container has none. I re-fetch from open sources each time. | Nothing needed if that's the intent — flagged so the cost is a known choice rather than a surprise. |

**One specific unknown blocks more than anything else on the list:** whether resting orders on
Hyperliquid carry a **persistent, publicly visible owner**. If they do, a large part of the L4
workstream is possible and a lot of the microstructure literature becomes checkable against ground
truth rather than inferred. If they don't, several proposals die and should be cut. This is a
documentation question, answerable in an afternoon by someone who can read the API docs or ask.

---

## 2. Hunting patterns — how to spot something worth grabbing

These are the shapes the corpus keeps arriving at from unrelated directions. If you see one in the
wild, in any field, it is worth a link even if it has nothing to do with markets. **That is the
point of the file** — the value has consistently come from a field that solved our problem without
knowing it existed.

- **Same object, two names, no shared citations.** Two literatures proving the same theorem in
  different notation. Already found: adverse selection ≡ loss-versus-rebalancing; market-maker
  subsidy ≡ learner regret; market-maker pricing ≡ natural gradient descent. The tell is a bound
  with the same *form* — a log of the number of states, a square root of time, an inverse
  temperature — appearing in a field that has never heard of ours.
- **A conditional whose trigger an adversary controls.** A rule that changes under load, under
  stress, under budget exhaustion. Whoever can move the trigger picks the rule, so the system has
  one mode, not two, and it's the worse one.
- **A corrective step that is an identity function on its common input.** A re-sort, a
  normalization, a fairness pass that only acts when its key differs — where in production the key
  is nearly always tied.
- **Each stage correct, the composition wrong.** Where unit tests on both halves pass and the
  defect needs real data's distribution to appear.
- **The penalty is set by the geometry, not the content.** A cost that depends only on how many
  parameters meet how much data, and not at all on what is being estimated.

---

## 3. Named bets on where the unexpected value is

Ranked by how strongly I'd expect a hit. Each is a claim I'm willing to be wrong about in public.

### 3.1 Epidemiology's R₀ estimation is our branching-ratio problem, already solved

**The bet.** The Hawkes branching ratio *is* R₀. `FIND-CRITICAL-SYSTEMS-LOOK-SUBCRITICAL` records
that an estimation window shorter than the process memory manufactures a downward-biased,
plausibly-trending estimate — which Hardiman, Bercot and Bouchaud presented as a finance result. I
would bet real money that this bias is named, characterized and corrected in the epidemic-estimation
literature, where the generation-interval-versus-observation-window problem has been worked over
since the 1980s and again very publicly since 2020.

**Why it matters more than it sounds.** If the correction exists, the open tension in §4 below may
be an artifact with a known fix rather than a genuine three-way inconsistency.

**Bring back:** anything on R₀ or R_t estimation bias under truncated observation windows,
renewal-equation estimators, or "real-time estimation of the reproduction number." Review articles
are ideal — I want the named bias, not a new derivation.

### 3.2 Real-time systems scheduling already models our venue's queue

**The bet.** `FIND-CATEGORICAL-PRIORITY-IS-A-DIFFERENT-QUEUE` says the Hyperliquid batch — orders
without GTC/IOC, then cancels, then GTC/IOC orders, proposer order within category — is not the
continuous-arrival queue every order-book model assumes. Fixed-priority preemptive scheduling in
real-time systems is *exactly* this structure: discrete releases, categorical priority classes,
tie-breaking within class. That field has exact schedulability tests and response-time analysis.
Microstructure does not cite it, as far as I can tell.

**Bring back:** response-time analysis for fixed-priority scheduling, especially anything on
*non-preemptive* or *batch-release* variants, and anything on priority inversion. A textbook chapter
beats a paper here.

### 3.3 Radar CFAR detection is regime detection with the threshold problem solved

**The bet.** Constant false alarm rate detection sets a detection threshold adaptively when the
noise floor is unknown and drifting — which is precisely the regime-break problem under changing
volatility, where a fixed threshold gives you a detector that fires constantly in high vol and never
in low. The radar literature has decades of specific CFAR variants (cell-averaging, ordered
statistic, adaptive) with known false-alarm behavior under clutter edges. "Clutter edge" is a
volatility regime boundary.

**Bring back:** a CFAR survey, or anything comparing CFAR variants under non-homogeneous clutter.

### 3.4 Near-critical branching in population genetics

**The bet.** Jaisson and Rosenbaum's result — nearly unstable Hawkes rescales to integrated CIR — is
a Feller diffusion limit, which is the central object of mathematical population genetics. That field
has deep results on genealogies of near-critical branching populations that have no counterpart in
the finance reading. If order flow is a near-critical branching process, its *genealogy* is the
causal ancestry of trades, and we have counterparty IDs on every fill, which almost nobody has.

**Bring back:** anything on genealogies of near-critical branching processes, the Kingman coalescent
applied to branching populations, or Feller diffusion limits stated outside a finance context.

### 3.5 Thermodynamics of computation, applied to agent memory

**The bet.** Still, Sivak, Bialek and Crutchfield give `β⟨W_diss⟩ = I_mem − I_pred`: the
thermodynamic cost of a model is exactly the memory it keeps that does not predict. For an LLM
agent with a growing memory this is a *pruning criterion with a physical derivation* rather than a
heuristic — retain by predictive information, not by recency or similarity. I have found no work
applying it to agent memory, which is either an opportunity or a sign someone tried and it doesn't
transfer.

**Bring back:** anything applying predictive information or information bottleneck to agent/LLM
memory management, retrieval, or context compression. A negative result is as useful as a positive
one, and cheaper to act on.

### 3.6 The microstructure and execution canon, which is paywalled

Sixteen of forty-three concept cards rest on anchors nobody has opened, and they are almost all the
commercial microstructure and execution books. So **the most confident part of the corpus is the
least verified part** — which is an acquisition problem, not an effort one. `make acquire` ranks the
list by what the knowledge store currently cannot support.

**Bring back:** any of them you have or can get. Bouchaud/Bonart/Donier/Gould *Trades, Quotes and
Prices* and Aït-Sahalia/Jacod *High-Frequency Econometrics* are the two that unblock the most cards.

---

## 4. The one open tension, and what would settle it

`FIND-EXPONENT-TENSION` is the only finding marked unresolved, deliberately:

- Jaisson–Rosenbaum: a heavy-tailed Hawkes kernel `x^−(1+α)` gives rough volatility with
  `H = α − 1/2`, and the limit **requires `α ∈ (1/2, 1)`** to exist at all.
- Rough volatility empirics: `H ≈ 0.1`, which implies `α ≈ 0.6`. Consistent so far.
- Hardiman/Bercot/Bouchaud, fitting a power-law Hawkes kernel to E-mini mid-price changes: decay
  exponents near `−1.15` below ~1000s and `−1.45` above, i.e. `α ≈ 0.15` and `0.45`. **Both below
  the 1/2 threshold at which the roughness regime begins.**

The three cannot all be right about the same object. Resolving this is worth more than another ten
findings, because two of the corpus's most load-bearing bets sit on top of it.

**What would settle it, in order of cost:**

1. **Someone has already noticed.** A paper reconciling measured Hawkes kernel exponents with
   rough-volatility `H`. Search terms: "Hawkes kernel exponent rough volatility consistency",
   "microstructural foundation of rough volatility". If this exists, everything below is unnecessary.
2. **Estimate `α` on our own data.** We have the trade timestamps. `EXT-FANO-EXPONENT` is the
   pre-registered version of this and is small enough to finish. Needs no new plumbing.
3. **The bias in §3.1.** If the epidemic literature's window-truncation correction applies, the
   measured `α` may be biased downward and the tension may dissolve.

---

## 5. What makes something easy for me to absorb

Not a formality — the difference between a link I can act on and one that costs a session.

- **A URL to an openly readable version beats a citation.** arXiv, an author's page, a university
  PDF. I can fetch and read those directly.
- **Name the section if you know it.** "the queueing chapter" is enough. The corpus reads at
  chapter granularity, and an un-located source becomes a `map_first` task before it becomes a read.
- **Tell me what you think is in it.** Even a wrong guess is useful — it tells me what to check, and
  a mismatch between what you expected and what's there is often the finding.
- **Don't filter for relevance to trading.** That filter has cost more than it saved. The three
  best findings this round came from consensus protocols, information geometry and random matrix
  theory, and two of them touch no trade we make.
