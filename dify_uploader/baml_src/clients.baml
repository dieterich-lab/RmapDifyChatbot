client<llm> OllamaQwen32 {
  provider "openai-generic"
  options {
    base_url env.BAML_OLLAMA_BASE_URL
    model env.BAML_OLLAMA_MODEL
    temperature 0.0
    max_tokens 2048
    timeout_ms 30000
  }
}
