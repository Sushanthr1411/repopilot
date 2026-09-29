from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/repopilot"

    # Embedding provider — "sentence_transformers" (default) or "openai"
    # Use "openai" in environments where PyTorch DLLs are unavailable (e.g. Windows App Control).
    # When "openai", set embedding_model to a valid OpenAI embedding model name
    # (e.g. "text-embedding-3-small") and ensure OPENAI_API_KEY is set.
    # IMPORTANT: do not mix providers in the same ChromaDB collection — vector
    # dimensions differ (sentence_transformers: 384, openai: 1536).
    embedding_provider: str = "sentence_transformers"

    # Embedding model name/path — interpreted by the selected embedding_provider
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ChromaDB persistence directory (relative to the process working directory)
    chroma_persist_directory: str = "./data/chroma"

    # ChromaDB collection name for code chunks
    chroma_collection_name: str = "repopilot_code"

    # Maximum lines per chunk before the secondary line-aware splitter kicks in
    chunk_max_lines: int = 80

    # Overlap lines when splitting oversized chunks
    chunk_overlap_lines: int = 5

    # --- Agent tool limits ---
    # Maximum search results returned by search_code (hard cap, prevents context floods)
    tool_search_max_results: int = 20
    # Maximum lines returned by read_file per call
    tool_file_max_lines: int = 200
    # Maximum graph nodes returned by dependency/caller tools
    tool_graph_max_results: int = 50

    # --- LLM / Agent configuration ---
    # LiteLLM model string, e.g. "anthropic/claude-sonnet-4-5" or "openai/gpt-4o"
    llm_model: str = "anthropic/claude-haiku-4-5-20251001"
    # Maximum tokens in the LLM completion response
    llm_max_tokens: int = 4096
    # Sampling temperature (0.0 = deterministic, 1.0 = creative)
    llm_temperature: float = 0.0
    # Maximum tool-call rounds before the agent stops and returns its best answer
    agent_max_iterations: int = 10
    # Maximum total tool calls across all iterations in one agent run
    agent_max_tool_calls: int = 30

    # --- API / Security ---
    # CORS origins allowed to call the API (never use ["*"] in production)
    cors_allow_origins: list[str] = ["http://localhost:3000"]
    # Security boundary for repository local paths.
    # When non-empty, every repository local_path must reside under this directory.
    # Empty string = any valid absolute path is accepted (development mode only).
    allowed_repo_root: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
