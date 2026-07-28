// load_kg_v6.cypher
// Loads the TRACE-CTI KG v6.0 snapshot (01_kg_snapshot_v6/) into a vanilla
// Neo4j 5 instance. No APOC required. Copy the CSV files into the Neo4j
// import/ directory preserving the kg_csv/, ontology/, gold/ subfolders,
// then run this script followed by constraints_v6.cypher (already applied
// here up-front) and audit_queries_q1_q7.cypher.
//
// Source of truth for the schema: 05_scripts/build_kg.py (docstring) and the
// CSV headers themselves. Counts after load must match Table 5 of the paper:
//   ExtractionSetup 6, ImportBatch 6, GraphVersion 6, LLMRun 72,
//   Report 65, Sentence 5303, Prediction 82260, GraphAssertion 27420,
//   ConsensusAssertion 5410, RetrievedContext 89706, gold doc-tuples 663
//   (824 gold instances at KG level collapse to 663 distinct doc-level tuples),
//   AttackTechnique 1250, ATTACK_RELATIONSHIP 21324, MalontClass 75.

// ---------- constraints ----------
CREATE CONSTRAINT setup_id IF NOT EXISTS FOR (n:ExtractionSetup) REQUIRE n.extraction_setup_id IS UNIQUE;
CREATE CONSTRAINT batch_id IF NOT EXISTS FOR (n:ImportBatch) REQUIRE n.import_batch_id IS UNIQUE;
CREATE CONSTRAINT version_id IF NOT EXISTS FOR (n:GraphVersion) REQUIRE n.graph_version_id IS UNIQUE;
CREATE CONSTRAINT run_id IF NOT EXISTS FOR (n:LLMRun) REQUIRE n.llm_run_id IS UNIQUE;
CREATE CONSTRAINT report_id IF NOT EXISTS FOR (n:Report) REQUIRE n.rid IS UNIQUE;
CREATE CONSTRAINT sentence_id IF NOT EXISTS FOR (n:Sentence) REQUIRE n.sentence_id IS UNIQUE;
CREATE CONSTRAINT attack_id IF NOT EXISTS FOR (n:AttackTechnique) REQUIRE n.attack_id IS UNIQUE;
CREATE CONSTRAINT prediction_id IF NOT EXISTS FOR (n:Prediction) REQUIRE n.prediction_id IS UNIQUE;
CREATE CONSTRAINT assertion_id IF NOT EXISTS FOR (n:GraphAssertion) REQUIRE n.graph_assertion_id IS UNIQUE;
CREATE CONSTRAINT consensus_id IF NOT EXISTS FOR (n:ConsensusAssertion) REQUIRE n.consensus_assertion_id IS UNIQUE;
CREATE CONSTRAINT context_id IF NOT EXISTS FOR (n:RetrievedContext) REQUIRE n.retrieved_context_id IS UNIQUE;
CREATE CONSTRAINT malont_id IF NOT EXISTS FOR (n:MalontClass) REQUIRE n.malont_iri IS UNIQUE;

// ---------- governance spine ----------
LOAD CSV WITH HEADERS FROM 'file:///kg_csv/nodes_extraction_setup.csv' AS row
MERGE (s:ExtractionSetup {extraction_setup_id: row.extraction_setup_id})
SET s.retriever = row.retriever, s.generator = row.generator,
    s.sampler = row.sampler, s.seed_range = row.seed_range,
    s.import_batch_id = row.import_batch_id,
    s.first_seen_version = row.first_seen_version;

LOAD CSV WITH HEADERS FROM 'file:///kg_csv/nodes_import_batch.csv' AS row
MERGE (b:ImportBatch {import_batch_id: row.import_batch_id})
SET b.extraction_setup_id = row.extraction_setup_id,
    b.first_seen_version = row.first_seen_version;

LOAD CSV WITH HEADERS FROM 'file:///kg_csv/nodes_graph_version.csv' AS row
MERGE (v:GraphVersion {graph_version_id: row.graph_version_id})
SET v.included_setups = row.included_setups,
    v.included_import_batches = row.included_import_batches;

LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_version_includes.csv' AS row
MATCH (v:GraphVersion {graph_version_id: row.graph_version_id})
MATCH (b:ImportBatch {import_batch_id: row.import_batch_id})
MERGE (v)-[:INCLUDES]->(b);

// ---------- corpus ----------
// Report identity is (dataset, report_id): report_id alone (e.g. "bosch_0")
// is only unique within a dataset, so nodes carry rid = dataset + '::' + report_id.
LOAD CSV WITH HEADERS FROM 'file:///kg_csv/nodes_report.csv' AS row
MERGE (r:Report {rid: row.dataset + '::' + row.report_id})
SET r.dataset = row.dataset, r.report_id = row.report_id,
    r.first_seen_version = row.first_seen_version;

LOAD CSV WITH HEADERS FROM 'file:///kg_csv/nodes_sentence.csv' AS row
MERGE (s:Sentence {sentence_id: row.sentence_id})
SET s.dataset = row.dataset, s.doc_id = row.doc_id,
    s.sent_idx = toInteger(row.sent_idx), s.text = row.sentence,
    s.first_seen_version = row.first_seen_version
WITH s, row
MATCH (r:Report {rid: row.dataset + '::' + row.doc_id})
MERGE (r)-[:CONTAINS_SENTENCE]->(s);

// ---------- ATT&CK + MALOnt grounding ----------
LOAD CSV WITH HEADERS FROM 'file:///ontology/attack_tactics.csv' AS row
MERGE (t:AttackTactic {tactic_id: row.tactic_id})
SET t.name = row.name, t.tactic_short = row.tactic_short;

LOAD CSV WITH HEADERS FROM 'file:///ontology/attack_techniques.csv' AS row
MERGE (t:AttackTechnique {attack_id: row.attack_id})
SET t.name = row.name, t.is_subtechnique = row.is_subtechnique,
    t.platforms = row.platforms;

LOAD CSV WITH HEADERS FROM 'file:///ontology/attack_relationships.csv' AS row
MATCH (a:AttackTechnique {attack_id: row.source_attack_id})
MATCH (b:AttackTechnique {attack_id: row.target_attack_id})
MERGE (a)-[rel:ATTACK_RELATIONSHIP]->(b)
SET rel.rel_type = row.relationship_type;

LOAD CSV WITH HEADERS FROM 'file:///ontology/malont_classes.csv' AS row
MERGE (m:MalontClass {malont_iri: row.malont_iri})
SET m.label = row.label, m.kind = row.kind;

LOAD CSV WITH HEADERS FROM 'file:///ontology/malont_relations.csv' AS row
MATCH (a:MalontClass {malont_iri: row.source_iri})
MATCH (b:MalontClass {malont_iri: row.target_iri})
MERGE (a)-[rel:MALONT_RELATION]->(b)
SET rel.rel_type = row.relationship_type;

// Observed-technique nodes referenced by predictions/assertions (203 ids incl. gold-only):
LOAD CSV WITH HEADERS FROM 'file:///kg_csv/nodes_attack_id.csv' AS row
MERGE (t:AttackTechnique {attack_id: row.attack_id})
SET t.in_gold = row.in_gold, t.first_seen_version = row.first_seen_version;

// ---------- extraction substrate ----------
LOAD CSV WITH HEADERS FROM 'file:///kg_csv/nodes_llm_run.csv' AS row
MERGE (l:LLMRun {llm_run_id: row.llm_run_id})
SET l.extraction_setup_id = row.extraction_setup_id, l.dataset = row.dataset,
    l.method = row.method, l.seed = toInteger(row.seed),
    l.original_seed = row.original_seed, l.source_file = row.source_file,
    l.import_batch_id = row.import_batch_id,
    l.first_seen_version = row.first_seen_version
WITH l, row
MATCH (s:ExtractionSetup {extraction_setup_id: row.extraction_setup_id})
MERGE (l)-[:RUN_OF]->(s);

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/nodes_prediction.csv' AS row
CALL {
  WITH row
  MERGE (p:Prediction {prediction_id: row.prediction_id})
  SET p.llm_run_id = row.llm_run_id, p.extraction_setup_id = row.extraction_setup_id,
      p.dataset = row.dataset, p.method = row.method, p.seed = toInteger(row.seed),
      p.sentence_id = row.sentence_id, p.attack_id = row.attack_id,
      p.first_seen_version = row.first_seen_version
} IN TRANSACTIONS OF 10000 ROWS;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_predicted_by.csv' AS row
CALL {
  WITH row
  MATCH (p:Prediction {prediction_id: row.prediction_id})
  MATCH (l:LLMRun {llm_run_id: row.llm_run_id})
  MERGE (l)-[:PRODUCED {first_seen_version: row.first_seen_version}]->(p)
} IN TRANSACTIONS OF 10000 ROWS;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_evidenced_by.csv' AS row
CALL {
  WITH row
  MATCH (p:Prediction {prediction_id: row.prediction_id})
  MATCH (s:Sentence {sentence_id: row.sentence_id})
  MERGE (p)-[:EVIDENCED_BY {first_seen_version: row.first_seen_version}]->(s)
} IN TRANSACTIONS OF 10000 ROWS;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_about.csv' AS row
CALL {
  WITH row
  MATCH (p:Prediction {prediction_id: row.prediction_id})
  MATCH (t:AttackTechnique {attack_id: row.attack_id})
  MERGE (p)-[:ASSERTS {first_seen_version: row.first_seen_version}]->(t)
} IN TRANSACTIONS OF 10000 ROWS;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/nodes_retrieved_context.csv' AS row
CALL {
  WITH row
  MERGE (c:RetrievedContext {retrieved_context_id: row.retrieved_context_id})
  SET c.retriever_key = row.retriever_key, c.dataset = row.dataset,
      c.method = row.method, c.sentence_id = row.sentence_id,
      c.rank = toInteger(row.rank), c.attack_id = row.attack_id,
      c.name = row.name, c.score = toFloat(row.score),
      c.first_seen_version = row.first_seen_version
} IN TRANSACTIONS OF 10000 ROWS;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_retrieved_for_sent.csv' AS row
CALL {
  WITH row
  MATCH (c:RetrievedContext {retrieved_context_id: row.retrieved_context_id})
  MATCH (s:Sentence {sentence_id: row.sentence_id})
  MERGE (c)-[:RETRIEVED_FOR {first_seen_version: row.first_seen_version}]->(s)
} IN TRANSACTIONS OF 10000 ROWS;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_retrieved_about.csv' AS row
CALL {
  WITH row
  MATCH (c:RetrievedContext {retrieved_context_id: row.retrieved_context_id})
  MATCH (t:AttackTechnique {attack_id: row.attack_id})
  MERGE (c)-[:CONSIDERED {first_seen_version: row.first_seen_version}]->(t)
} IN TRANSACTIONS OF 10000 ROWS;

// ---------- assertion & trust layer ----------
:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/nodes_graph_assertion.csv' AS row
CALL {
  WITH row
  MERGE (a:GraphAssertion {graph_assertion_id: row.graph_assertion_id})
  SET a.setup_id = row.setup_id, a.dataset = row.dataset, a.method = row.method,
      a.sentence_id = row.sentence_id, a.doc_id = row.doc_id,
      a.sent_idx = toInteger(row.sent_idx), a.attack_id = row.attack_id,
      a.support_seeds = row.support_seeds,
      a.first_seen_version = row.first_seen_version,
      a.scope_v1 = row.scope_v1, a.scope_v2 = row.scope_v2,
      a.scope_v3 = row.scope_v3, a.scope_v4 = row.scope_v4,
      a.scope_v5 = row.scope_v5, a.scope_v6 = row.scope_v6,
      a.trust_scope = row.trust_scope
} IN TRANSACTIONS OF 10000 ROWS;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_assertion_evidence.csv' AS row
CALL {
  WITH row
  MATCH (a:GraphAssertion {graph_assertion_id: row.graph_assertion_id})
  MATCH (s:Sentence {sentence_id: row.sentence_id})
  MERGE (a)-[:HAS_EVIDENCE {first_seen_version: row.first_seen_version}]->(s)
} IN TRANSACTIONS OF 10000 ROWS;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_assertion_about.csv' AS row
CALL {
  WITH row
  MATCH (a:GraphAssertion {graph_assertion_id: row.graph_assertion_id})
  MATCH (t:AttackTechnique {attack_id: row.attack_id})
  MERGE (a)-[:ASSERTS_TECHNIQUE {first_seen_version: row.first_seen_version}]->(t)
} IN TRANSACTIONS OF 10000 ROWS;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_assertion_setup.csv' AS row
CALL {
  WITH row
  MATCH (a:GraphAssertion {graph_assertion_id: row.graph_assertion_id})
  MATCH (s:ExtractionSetup {extraction_setup_id: row.extraction_setup_id})
  MERGE (a)-[:ASSERTED_BY {first_seen_version: row.first_seen_version}]->(s)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///kg_csv/nodes_consensus_assertion.csv' AS row
MERGE (c:ConsensusAssertion {consensus_assertion_id: row.consensus_assertion_id})
SET c.dataset = row.dataset, c.method = row.method,
    c.sentence_id = row.sentence_id, c.doc_id = row.doc_id,
    c.attack_id = row.attack_id,
    c.n_supporters_latest = toInteger(row.n_supporters_latest),
    c.supporters_latest = row.supporters_latest,
    c.scope = row.scope, c.gold_backed = row.gold_backed,
    c.first_seen_version = row.first_seen_version;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_supports.csv' AS row
CALL {
  WITH row
  MATCH (c:ConsensusAssertion {consensus_assertion_id: row.consensus_assertion_id})
  MATCH (a:GraphAssertion {graph_assertion_id: row.graph_assertion_id})
  MERGE (c)-[:SUPPORTS {supporting_setup_id: row.supporting_setup_id,
                        first_seen_version: row.first_seen_version}]->(a)
} IN TRANSACTIONS OF 10000 ROWS;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_agrees_with.csv' AS row
CALL {
  WITH row
  MATCH (a:GraphAssertion {graph_assertion_id: row.graph_assertion_id_a})
  MATCH (b:GraphAssertion {graph_assertion_id: row.graph_assertion_id_b})
  MERGE (a)-[:AGREES_WITH {setup_a: row.setup_a, setup_b: row.setup_b,
                           first_seen_version: row.first_seen_version}]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

:auto LOAD CSV WITH HEADERS FROM 'file:///kg_csv/edges_disagrees_with.csv' AS row
CALL {
  WITH row
  MATCH (s:Sentence {sentence_id: row.sentence_id})
  MERGE (d:Disagreement {sentence_id: row.sentence_id, dataset: row.dataset,
                         method: row.method, setup_a: row.setup_a, setup_b: row.setup_b})
  SET d.n_a_only = toInteger(row.n_a_only), d.n_b_only = toInteger(row.n_b_only),
      d.n_intersection = toInteger(row.n_intersection),
      d.first_seen_version = row.first_seen_version
  MERGE (d)-[:DISAGREES_ON]->(s)
} IN TRANSACTIONS OF 10000 ROWS;

// ---------- gold (doc-level analyst labels) ----------
// report_id format: "rpt::<dataset>::<doc_id>" (see gold_assertions.csv).
LOAD CSV WITH HEADERS FROM 'file:///gold/gold_assertions.csv' AS row
MERGE (g:GoldInstance {gold_id: row.assertion_id})
SET g.report_id = row.report_id,
    g.dataset = split(row.report_id, '::')[1],
    g.doc_id = split(row.report_id, '::')[2],
    g.attack_id = row.attack_id,
    g.validation_basis = row.validation_basis
WITH g, row
MATCH (t:AttackTechnique {attack_id: row.attack_id})
MERGE (g)-[:LABELS_TECHNIQUE]->(t)
WITH g
MATCH (r:Report {rid: g.dataset + '::' + g.doc_id})
MERGE (r)-[:HAS_GOLD_LABEL]->(g);
