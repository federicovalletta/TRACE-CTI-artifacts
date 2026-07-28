// audit_queries_q1_q7.cypher
// The seven SOC audit queries of the paper (Table "Baseline A", Q1-Q7),
// against the TRACE-CTI KG v6.0 snapshot loaded via load_kg_v6.cypher.
// Each query is closed-form: it reads the graph alone, no model re-run needed.
//
// Schema notes (v6 snapshot, see 01_kg_snapshot_v6/kg_csv headers):
//   - GraphAssertion.trust_scope in {'gold_backed','strong_consensus',
//     'consensus_validated','prediction_only'} (strongest applicable scope).
//   - GraphAssertion.scope_v1..scope_v6 give the scope AT each graph version:
//     the version axis is materialised, so time travel is a property read.
//   - ExtractionSetup carries explicit retriever / generator columns.
//   - The retrieval facet lives on RetrievedContext -[:CONSIDERED]-> AttackTechnique.
//
// Parameters (Neo4j Browser):
//   :param assertion_id => '...';        // any GraphAssertion graph_assertion_id
//   :param setup_id     => 'e5_mistral'; // any of the six ExtractionSetups
//   :param version_a    => 'scope_v1';
//   :param version_b    => 'scope_v3';

// ---------------------------------------------------------------------------
// Q1. Which verbatim span supports this ATT&CK claim?
MATCH (a:GraphAssertion {graph_assertion_id: $assertion_id})
MATCH (a)-[:HAS_EVIDENCE]->(s:Sentence)
OPTIONAL MATCH (r:Report)-[:CONTAINS_SENTENCE]->(s)
RETURN a.attack_id AS claimed_technique,
       s.text      AS verbatim_evidence,
       r.rid       AS source_report,
       s.sent_idx  AS sentence_index;

// ---------------------------------------------------------------------------
// Q2. Which model, prompt, seed, retriever produced it?
// The assertion collapses sigma=0 seeds; the per-seed runs are its predictions.
MATCH (a:GraphAssertion {graph_assertion_id: $assertion_id})
MATCH (a)-[:ASSERTED_BY]->(setup:ExtractionSetup)
OPTIONAL MATCH (p:Prediction {sentence_id: a.sentence_id, attack_id: a.attack_id,
                              extraction_setup_id: setup.extraction_setup_id})
OPTIONAL MATCH (run:LLMRun)-[:PRODUCED]->(p)
RETURN a.attack_id              AS technique,
       setup.generator          AS generator,
       setup.retriever          AS retriever,
       setup.sampler            AS sampler,
       a.method                 AS method,
       collect(DISTINCT run.seed)      AS seeds,
       collect(DISTINCT run.llm_run_id) AS llm_runs;

// ---------------------------------------------------------------------------
// Q3. Is this claim gold-backed, corroborated, unanimous, or prediction-only?
// trust_scope is materialised; witness support is re-derivable from SUPPORTS.
MATCH (a:GraphAssertion {graph_assertion_id: $assertion_id})
OPTIONAL MATCH (c:ConsensusAssertion)-[:SUPPORTS]->(a)
RETURN a.attack_id   AS technique,
       a.trust_scope AS trust_scope,          // gold_backed | strong_consensus | consensus_validated | prediction_only
       c.n_supporters_latest AS witness_support,
       c.supporters_latest   AS supporting_setups;

// ---------------------------------------------------------------------------
// Q4. What does the graph look like under v1.0 vs v3.0 (version delta)?
// Version views are materialised per assertion (scope_v1..scope_v6):
// an assertion exists in view vN iff its scope_vN is non-empty.
MATCH (a:GraphAssertion)
WITH a,
     CASE $version_a WHEN 'scope_v1' THEN a.scope_v1 WHEN 'scope_v2' THEN a.scope_v2
                     WHEN 'scope_v3' THEN a.scope_v3 WHEN 'scope_v4' THEN a.scope_v4
                     WHEN 'scope_v5' THEN a.scope_v5 ELSE a.scope_v6 END AS sA,
     CASE $version_b WHEN 'scope_v1' THEN a.scope_v1 WHEN 'scope_v2' THEN a.scope_v2
                     WHEN 'scope_v3' THEN a.scope_v3 WHEN 'scope_v4' THEN a.scope_v4
                     WHEN 'scope_v5' THEN a.scope_v5 ELSE a.scope_v6 END AS sB
RETURN
  count(CASE WHEN sA IS NOT NULL AND sA <> '' THEN 1 END) AS assertions_in_view_a,
  count(CASE WHEN sB IS NOT NULL AND sB <> '' THEN 1 END) AS assertions_in_view_b,
  count(CASE WHEN (sA IS NULL OR sA = '') AND sB IS NOT NULL AND sB <> '' THEN 1 END) AS added_between_views,
  count(CASE WHEN sA IS NOT NULL AND sA <> '' AND sA <> sB THEN 1 END) AS scope_changed;

// ---------------------------------------------------------------------------
// Q5. Which claims would disappear if I revoked an ExtractionSetup?
// Dry-run, non-destructive: assertions of the revoked setup whose target
// (sentence, technique) has no surviving witness from another setup.
MATCH (a:GraphAssertion)-[:ASSERTED_BY]->(:ExtractionSetup {extraction_setup_id: $setup_id})
OPTIONAL MATCH (other:GraphAssertion)-[:ASSERTED_BY]->(os:ExtractionSetup)
  WHERE other.sentence_id = a.sentence_id
    AND other.attack_id   = a.attack_id
    AND other.method      = a.method
    AND os.extraction_setup_id <> $setup_id
WITH a, count(other) AS surviving_witnesses
WHERE surviving_witnesses = 0
RETURN a.attack_id   AS technique,
       a.doc_id      AS report,
       a.sentence_id AS sentence,
       a.trust_scope AS current_scope,
       'sole witness: target leaves every corroborated view' AS impact
ORDER BY technique
LIMIT 100;

// ---------------------------------------------------------------------------
// Q6. Which technique disagreements separate retriever effect from generator effect?
// Disagreement nodes record, per sentence, the symmetric difference between
// two setups' verdicts; the setup pair tells which axis moved.
MATCH (d:Disagreement)
MATCH (sa:ExtractionSetup {extraction_setup_id: d.setup_a})
MATCH (sb:ExtractionSetup {extraction_setup_id: d.setup_b})
WITH d, sa, sb,
     CASE
       WHEN sa.generator = sb.generator AND sa.retriever <> sb.retriever THEN 'retriever effect'
       WHEN sa.generator <> sb.generator AND sa.retriever = sb.retriever THEN 'generator effect'
       ELSE 'both axes'
     END AS attributed_axis
RETURN attributed_axis,
       count(d)                            AS disagreeing_sentence_pairs,
       sum(d.n_a_only + d.n_b_only)        AS total_one_sided_labels,
       avg(1.0 * (d.n_a_only + d.n_b_only) /
           (d.n_a_only + d.n_b_only + d.n_intersection)) AS mean_jaccard_distance
ORDER BY disagreeing_sentence_pairs DESC;

// ---------------------------------------------------------------------------
// Q7. Which untrusted claims are candidates for analyst review?
// Prediction-only targets ranked by how close they are to corroboration:
// highest witness support first, then broadest technique impact.
MATCH (a:GraphAssertion {trust_scope: 'prediction_only'})
OPTIONAL MATCH (other:GraphAssertion)
  WHERE other.sentence_id = a.sentence_id
    AND other.attack_id   = a.attack_id
    AND other.method      = a.method
    AND other.graph_assertion_id <> a.graph_assertion_id
WITH a, count(DISTINCT other.setup_id) + 1 AS support
RETURN a.attack_id          AS technique,
       a.doc_id             AS report,
       a.sentence_id        AS sentence,
       support              AS witness_support,
       a.first_seen_version AS since_version
ORDER BY support DESC, technique
LIMIT 100;
