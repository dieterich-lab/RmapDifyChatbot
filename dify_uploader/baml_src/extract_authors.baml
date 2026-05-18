function ExtractAuthorsFromHeader(header_text: string) -> AuthorExtractionResult {
  client OllamaQwen32
  prompt #"
    You extract author names from scientific paper header text.

    Task:
    - Return ONLY human author names.
    - Keep original spelling when possible.
    - Remove affiliations, institutes, universities, hospitals, addresses, section labels,
      copyright text, dates, editorial notes, and publication metadata.
    - Remove duplicates while preserving order.
    - If unsure, return only clearly identifiable person names.

    Input header text:
    {{header_text}}

    {{ ctx.output_format(prefix="Use the following OUTPUT FORMAT:") }}
  "#
}

function ExtractTitleFromHeader(header_text: string) -> TitleExtractionResult {
  client OllamaQwen32
  prompt #"
    You extract the scientific paper title from header text.

    Task:
    - Return exactly one title string.
    - Return only the paper title.
    - Remove author names, affiliations, journal header/footer, copyright/license text,
      DOI lines, section labels (e.g. ABSTRACT, INTRODUCTION), and page metadata.
    - Preserve original title wording and punctuation where possible.

    Input header text:
    {{header_text}}

    {{ ctx.output_format(prefix="Use the following OUTPUT FORMAT:") }}
  "#
}
