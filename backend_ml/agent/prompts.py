"""Builds the extraction system prompt by reusing services/extractor loaders."""

from services.extractor import _load_prompt_file, get_current_date_context


def build_extraction_system_prompt() -> str:
    """Same composition the live extractor uses: dated system prompt + examples."""
    template = _load_prompt_file("extraction_system.md")
    examples = _load_prompt_file("extraction_examples.md")
    current_date, day_of_week = get_current_date_context()
    prompt = template.format(current_date=current_date, day_of_week=day_of_week)
    return prompt + "\n\n---\n\n" + examples
