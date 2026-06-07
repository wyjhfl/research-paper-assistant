# UI and Function Improvement Research

Version: v1.0.1 personal local use

This note records product research and a practical improvement roadmap for the
Research Paper Assistant. It intentionally contains no `.env` values, API keys,
Authorization headers, database URLs, or local machine paths.

## External product signals

The strongest patterns from comparable research assistants are:

1. **Source-grounded answers with visible citations**
   - Google NotebookLM emphasizes source-grounded chat and clear citations that
     let users inspect where an answer came from.
   - Project implication: every answer should expose source snippets, paper
     title, page, chunk id, retrieval mode, and an easy path back to the source.

2. **Question starters and guided workflows**
   - NotebookLM and similar tools guide users with suggested prompts, summaries,
     study guides, or follow-up questions instead of leaving a blank input.
   - Project implication: single-paper and cross-paper QA should include
     one-click question presets for contribution, method, evidence, limitations,
     comparison, gaps, and citation drafting.

3. **Semantic search and evidence synthesis**
   - Elicit exposes programmatic research search over a large paper corpus and
     report generation. Consensus focuses on academic search and synthesis.
   - Project implication: the next major quality gain is still real embedding
     provider support, then structured evidence tables for literature review.

4. **Interactive PDF / paper reading assistance**
   - SciSpace-style PDF copilot workflows focus on explaining paper sections and
     grounding answers in precise citations.
   - Project implication: source snippets should link back to the chunk preview,
     and the paper detail page should keep chunks easy to inspect.

5. **Structured extraction**
   - Modern research tools increasingly transform sources into tables,
     snapshots, or reusable notes.
   - Project implication: extend Idea extraction toward structured review tables:
     problem, method, dataset, metric, limitation, and future work.

## Improvements landed in this iteration

- Added single-paper QA question presets.
- Added cross-paper QA question presets.
- Added answer copy buttons for single-paper and cross-paper QA.
- Added cross-paper "select all completed" action.
- Added source jump links from answer citations to paper chunks.
- Exposed lexical and vector scores in citation metadata.
- Added an evidence quality summary for answer sources: top score, average
  score, lexical/vector maxima, and retrieval mode distribution.
- Added expandable/copyable source cards for single-paper and cross-paper QA.
- Added hash-target chunk highlighting on the paper detail page so citation
  jumps make the active chunk visible and expanded.
- Added a structured literature review matrix page for selected completed
  papers: problem, method, evidence, metric/result, limitation, future work,
  and source chunk links.
- Added follow-up question chips after successful answers.
- Changed copy behavior to copy the answer plus compact source metadata.
- Added Idea extraction controls for LLM fallback and max idea count.
- Added no-result reason and suggestions display for Idea extraction.
- Added paper library summary cards: total, completed, failed, chunk count.
- Added a paper library usage hint for the most common next actions.
- Kept paper chunks open with a bounded scroll area for faster source checking.
- Reworked paper detail rendering to avoid a local streaming skeleton stall and
  make client-side source inspection more reliable.
- Expanded frontend mojibake scan coverage to the edited components.

## Recommended next roadmap

### P1: Real embedding provider

Goal: improve strict RAG, multilingual retrieval, and semantic matching.

Validation:

- English and Chinese questions over English papers retrieve relevant chunks.
- Strict RAG answers improve beyond current local embedding baseline.
- `model_smoke_check.py` passes with both LLM and embedding providers.

### P1: Structured literature review table

Goal: convert selected papers into a review matrix:

- paper
- problem
- method
- dataset or evidence
- metric or result
- limitation
- future work
- source chunk ids

Validation:

- Generated table never includes secrets.
- Every row includes at least one source chunk id.
- UI can copy/export the table.

Status: **Landed in heuristic form.** `/papers/review` generates a review
matrix without calling the model, links each row back to source chunks, and can
copy the result as Markdown. Future improvement: optional LLM-assisted synthesis
with strict source grounding.

### P2: Follow-up questions

Goal: after an answer, suggest 3 short follow-up questions grounded in the same
sources.

Validation:

- Suggestions are short and clickable. **Landed in lightweight form.**
- Clicking a suggestion fills the question box. **Landed in lightweight form.**
- No extra model call is made unless the user submits. **Landed in lightweight form.**
- Future improvement: generate context-specific follow-ups from the returned
  source set instead of using fixed presets.

### P2: Saved notes

Goal: let users save an answer or source snippet as a local note linked to papers
and chunks.

Validation:

- Notes preserve user isolation.
- Notes do not store API keys, prompt raw text, or long hidden context.

### P2: Better source viewer

Goal: make source inspection closer to a reader workflow:

- highlight active chunk
- show source list beside answer on wide screens
- allow chunk text expansion

Validation:

- No horizontal overflow on mobile.
- Source jump links remain stable.

Status: **Landed in practical form.** Answer source cards now include an
evidence summary, expandable excerpts, copy buttons, and stable links back to
paper chunks. The paper detail page highlights and expands the active chunk
when opened with `#chunk-...`.

## Sources consulted

- Google NotebookLM Help: https://support.google.com/notebooklm/answer/16164461
- Google NotebookLM product page: https://notebooklm.google/
- Elicit API documentation: https://docs.elicit.com/
- Consensus app: https://consensus.app/
- PaperQA paper: https://arxiv.org/abs/2312.07559
