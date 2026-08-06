export type Rights = {
  status: string;
  confidence: string;
  use_class: string;
  evidence: string | null;
};

export type Unit = {
  unit_id: string;
  topic: string | null;
  locator: string | null;
  pages: number | null;
  read_status: string;
  notes: string | null;
};

export type Entry = {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  bucket: string;
  form: string;
  venue: string | null;
  pages: number | null;
  priority: number | null;
  tags: string[];
  notes: string | null;
  workstream?: string | null;
  doi: string | null;
  url: string | null;
  rights: Rights;
  held: boolean;
  units: Unit[];
  refs: { target: string; relation: string; note: string | null }[];
};

export type Anchor = {
  key: string;
  source_id: string;
  anchor: string | null;
  read: boolean;
};

export type Concept = {
  id: string;
  name: string;
  plain: string;
  mechanism: string;
  equations: string | null;
  assumptions: string[];
  failure_modes: string[];
  alternatives: string[];
  signature: string | null;
  markets: string[];
  horizons: string[];
  observables: string[];
  problems: string[];
  contradicts: string[];
  supports: string[];
  status: string;
  confidence: number | null;
  workstream: string;
  tags: string[];
  anchors: Anchor[];
  grounded: boolean;
  methods: string[];
};

export type Problem = {
  problem_id: string;
  vertical?: string;
  workstream?: string;
  statement: string;
  observed_signature?: string;
  weight?: number;
  buckets?: string[];
  tags?: string[];
};

export type Chain = {
  problem_id: string;
  workstream: string | null;
  weight: number | null;
  concepts: number;
  with_method: number;
  with_hypothesis: number;
  with_decision_card: number;
  complete_chains: string[];
};

export type Assessment = {
  counts: Record<string, number>;
  contradiction: {
    pairs: [string, string][];
    clusters: string[][];
    concepts_in_a_contradiction: number;
    uncountered_concepts: string[];
  };
  chains: Chain[];
  complete_chain_problems: string[];
  problems_without_concept: string[];
  load_bearing_sources: { anchor: string; source_id: string; cards: string[]; read: boolean }[];
  unread_single_points: { anchor: string; cards: string[] }[];
  high_confidence_on_unread: { concept_id: string; confidence: number; name: string }[];
  orphan_methods: string[];
  concepts_without_problem: string[];
  by_workstream: Record<string, number>;
  by_implementation_status: Record<string, number>;
  grounded_share: number;
};

export type GraphNode = {
  id: string;
  bucket: string;
  priority: number | null;
  title: string;
  held: boolean;
  degree: number;
  bridges: string[];
};

export type Bundle = {
  counts: Record<string, number>;
  entries: Entry[];
  concepts: Concept[];
  problems: Problem[];
  methods: { method_id: string; concept_ids: string[]; status: string; notes?: string }[];
  hypotheses: { hypothesis_id: string; concept_id: string; ex_ante_prediction: string }[];
  decisions: { decision_relevance_id: string; concept_id: string; decision_type: string }[];
  bets: Record<string, unknown>[];
  extensions: Record<string, unknown>[];
  assessment: Assessment;
  buckets: Record<string, { target_pages: number; pages_mapped: number; entries: number; label: string | null }>;
  graph: {
    nodes: GraphNode[];
    edges: { source: string; target: string; relation: string }[];
    components: number;
    isolated: string[];
    unresolved: number;
  };
};
