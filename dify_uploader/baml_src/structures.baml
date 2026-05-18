class AuthorExtractionResult {
  authors string[] @description("Cleaned person names only. No institutions, affiliations, editorial text, or section labels.")
}

class TitleExtractionResult {
  title string @description("Cleaned paper title only. No author list, affiliations, journal metadata, copyright, or section labels.")
}
