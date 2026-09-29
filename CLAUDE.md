# RepoPilot AI — Claude Code Instructions

## Project Overview

RepoPilot AI is an agentic codebase intelligence platform for analyzing and understanding complex Python codebases.

The product should allow a user to provide a Python repository and then:

* Explore the repository structure
* Understand files, modules, classes, functions, and symbols
* Understand imports and relationships between code elements
* Search the codebase using natural language
* Ask questions about how parts of the codebase work
* Trace dependencies, callers, and callees
* Receive AI-generated explanations grounded in the actual repository
* See the source files and line ranges used to support an explanation

The core value of RepoPilot is not simply "chat with code".

The system must combine:

1. Static code understanding
2. Repository structure
3. Code relationships / graph information
4. Semantic code search
5. Agentic tool use
6. Grounded AI explanations

---

## Current Development Strategy

Build the product incrementally.

### Phase 1 — Backend

Build and validate the complete code-intelligence backend before building the frontend.

Backend responsibilities include:

* Repository ingestion
* Python source parsing
* Symbol extraction
* Relationship extraction
* Code graph construction
* Code chunking
* Semantic indexing
* Repository search
* Agent tools
* Agent reasoning
* REST API

### Phase 2 — Frontend

After the backend APIs are stable, build a React frontend that consumes those APIs.

The frontend should not contain core code-intelligence logic.

---

## Technology Direction

Preferred backend technologies:

* Python
* FastAPI
* PostgreSQL
* SQLAlchemy
* Pydantic
* Alembic
* Python `ast`
* NetworkX
* ChromaDB
* sentence-transformers
* Anthropic Claude API
* pytest

Use `uv` for Python dependency and environment management.

Do not introduce additional infrastructure unless there is a clear reason.

Avoid premature adoption of:

* Kubernetes
* Kafka
* Celery
* Redis
* Neo4j
* Microservices
* Complex event-driven architecture

A simple modular monolith is preferred for the initial product.


### AI / LLM Routing

Use LiteLLM as the LLM abstraction and routing layer.

The application should not directly depend on provider-specific SDKs for normal agent inference.

Preferred architecture:

RepoPilot Agent
    ↓
LiteLLM
    ↓
Configured LLM provider/model

LiteLLM should make it possible to switch models/providers through configuration without changing the core agent logic.

Provider-specific integrations should be isolated behind LiteLLM where possible.
---

## Architecture Principles

Keep the backend modular.

Separate:

* API layer
* Schemas
* Database layer
* Business/services layer
* Code intelligence layer
* Graph layer
* Search/indexing layer
* Agent layer
* Agent tools

Avoid putting business logic directly inside FastAPI route handlers.

Prefer reusable services with clear interfaces.

Keep external dependencies behind abstractions when practical, especially:

* LLM providers
* Embedding providers
* Vector databases

The first implementation should be simple, but the architecture should not make future replacement unnecessarily difficult.

---

## Repository Intelligence Model

RepoPilot should treat a repository as structured data.

The system should eventually understand entities such as:

### Repository

A repository being analyzed.

### File

A source file belonging to a repository.

### Symbol

Examples:

* module
* class
* function
* async function
* method

Every symbol should retain source-location information.

### Relationship

Examples:

* IMPORTS
* DEFINES
* CALLS
* INHERITS
* USES

### Code Chunk

A searchable piece of source code with metadata such as:

* repository
* file
* symbol
* start line
* end line
* source content

---

## Python Parsing

Use Python's built-in `ast` module as the initial parser.

Do not assume static analysis can perfectly resolve all Python behavior.

Python is dynamic, so unresolved or ambiguous references must be represented honestly rather than guessed.

The parser should prioritize:

* correctness
* source locations
* deterministic behavior
* graceful handling of syntax errors
* clear data structures

Do not pretend that an inferred relationship is certain when it is not.

---

## Agentic Architecture

The AI agent must not receive the entire repository by default.

The intended pattern is:

User question
→ agent decides what information is needed
→ agent calls RepoPilot tools
→ tools retrieve repository information
→ agent reasons over retrieved information
→ grounded answer with source references

The agent should have access to narrowly scoped tools such as:

* search_code
* inspect_symbol
* read_file
* get_dependencies
* get_dependents
* get_callers
* get_callees
* get_file_dependencies

Tool outputs must contain enough metadata for the agent to cite source locations.

The agent should communicate with LLMs through LiteLLM.

Do not couple the core agent implementation directly to the Anthropic SDK.

---

## Grounding Rules

RepoPilot must prioritize factual grounding over confident answers.

When answering questions about a repository:

* Inspect relevant repository data before making claims.
* Do not invent files, functions, classes, or relationships.
* Do not assume behavior from a name alone.
* Use actual source code and graph/search results.
* Clearly distinguish confirmed information from inference.
* When evidence is insufficient, say so.
* Include relevant file paths and line ranges whenever possible.

The agent should never claim to have inspected code that it did not retrieve.

---

## Source References

Repository explanations should eventually support references in this form:

`path/to/file.py:20-42`

Where possible, also include the relevant symbol name.

Example:

`services/auth.py:15-38 — authenticate()`

Source references are a core product feature and should be preserved throughout the backend architecture.

---

## API Design

The backend should expose a clean REST API for the future React client.

Keep API contracts:

* predictable
* versionable
* typed
* JSON-based
* independent of internal implementation details

Do not make frontend-specific assumptions inside backend services.

---

## Coding Standards

Write clean, readable Python.

Prefer:

* type hints
* Pydantic models
* small focused functions
* clear names
* explicit interfaces
* dependency injection
* structured error handling
* useful logging
* unit tests for important logic

Avoid:

* giant functions
* deeply coupled modules
* duplicated business logic
* unnecessary abstractions
* magic constants
* hard-coded repository-specific behavior

Use abstractions only where they provide real value.

Do not build abstractions solely for hypothetical future requirements.

---

## Error Handling

Validate external inputs at system boundaries.

Handle failures gracefully for:

* invalid repository sources
* missing files
* malformed Python files
* unsupported constructs
* database errors
* embedding failures
* vector-store failures
* LLM/API failures

Errors should provide useful diagnostic information without exposing secrets.

---

## Security

Treat analyzed repositories as untrusted input.

Never execute arbitrary repository code as part of normal repository analysis.

Do not allow the AI agent to:

* execute arbitrary Python from the analyzed repository
* execute arbitrary shell commands against the host
* modify the analyzed repository unless a future feature explicitly introduces a secure sandbox

Never commit:

* API keys
* passwords
* tokens
* `.env` files containing secrets
* private credentials

Use `.env.example` for required configuration.

---

## Testing

Tests should verify behavior, not merely increase coverage numbers.

Important areas include:

* Python parsing
* symbol extraction
* relationship extraction
* graph traversal
* code chunking
* semantic search
* API behavior
* agent tool behavior

Use realistic small fixture repositories for code-intelligence tests.

Tests should not be written in a way that forces the implementation to hard-code expected outputs.

---

## Development Workflow

Before modifying an unfamiliar part of the codebase:

1. Inspect the relevant files.
2. Understand the existing architecture.
3. Identify the smallest appropriate change.
4. Implement the change.
5. Run relevant tests.
6. Fix regressions.
7. Review the final diff.

Do not rewrite unrelated code unnecessarily.

Do not create new architectural layers unless they solve an actual current requirement.

---

## Claude Code Behavior

When working on this project:

* Investigate the existing code before answering questions about it.
* Prefer modifying the existing architecture over creating parallel implementations.
* Keep changes incremental.
* Preserve working functionality.
* Run tests after meaningful changes.
* Tell the developer when an assumption is being made.
* Ask for clarification only when the ambiguity materially affects the implementation; otherwise make the safest reasonable assumption and document it.
* Do not claim a feature works without actually verifying it.
* Do not hide failing tests or errors.

For larger tasks, first inspect the repository and explain the intended change briefly before implementing it.

---

## Documentation

Keep important architectural decisions documented.

The README should eventually contain:

* project purpose
* architecture overview
* setup instructions
* environment variables
* development commands
* API overview
* example usage

Do not create excessive documentation files for trivial implementation details.

---

## Git

Use Git as the project's source of truth.

Prefer small, meaningful commits.

Before significant changes, inspect:

* `git status`
* relevant existing diffs
* recent commits when historical context is useful

Never force-push or destroy existing work without explicit instruction.

---

## Product Direction

The core user experience should eventually feel like:

"Give RepoPilot a Python repository and ask it to explain the codebase."

Examples:

* "How does authentication work?"
* "What happens when a user creates an account?"
* "Which modules depend on the database layer?"
* "Who calls this function?"
* "Where is payment processing implemented?"
* "Explain the architecture of this repository."
* "What would break if I changed this class?"

The answer should be based on actual repository evidence rather than generic AI knowledge.

---

## Definition of Done

A feature is not considered complete merely because the code was written.

A feature should be considered complete only after:

* implementation is finished
* relevant tests pass
* integration behavior is verified where applicable
* errors are handled appropriately
* API contracts are correct
* no obvious unrelated regressions were introduced

When verification is not possible, explicitly state what remains unverified.
