# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## IMPORTANT: Repository Context
- This COSA repo is a git subproject/submodule contained within the parent "genie-in-the-box" project
- When working within the COSA directory, only manage this repository (not the parent project)
- Do not stage, commit, or push changes to the parent repository from here

## Commands
- Run tests: `pytest tests/`
- Run single test: `pytest tests/test_file.py::test_function -v`
- Run lint: `flake8 .`
- Format code: `black .`

## Code Style
- **Imports**: Group by stdlib, third-party, local packages
- **Indentation**: 4 spaces (not tabs)
- **Naming**: snake_case for functions/methods, PascalCase for classes, UPPER_SNAKE_CASE for constants
- **Documentation**: Add docstrings to new functions and classes
- **Error handling**: Catch specific exceptions with context in messages
- **XML Formatting**: Use XML tags for structured agent responses
- **Variable Alignment**: Maintain vertical alignment of equals signs within code blocks
  ```python
  # CORRECT - keep vertical alignment
  self.debug           = debug
  self.verbose         = verbose
  self.path_prefix     = path_prefix
  self.model_name      = model_name
  ```
- **Spacing**: Use spaces inside parentheses and brackets
  ```python
  # CORRECT - with spaces inside parentheses/brackets
  if requested_length is not None and requested_length > len( placeholders ):
  for command in commands.keys():
  words = text.split()
  
  # INCORRECT - no spaces inside parentheses/brackets
  if requested_length is not None and requested_length > len(placeholders):
  for command in commands.keys():
  words = text.split()
  ```

## Key Components
- **AgentBase**: Abstract base class for all agents
- **Llm**: Handles interactions with language models (OpenAI, Groq, Google)
- **ConfigurationManager**: Manages settings with inheritance capabilities
- **RunnableCode**: Handles code generation and execution

## Debug Practices
- Most classes accept `debug` and `verbose` parameters
- Use `print_banner()` from `utils.py` for formatted messages
- Track state with constants (STATE_INITIALIZED, STATE_RUNNING, etc.)

## Recent Changes
- Refactoring to use external LLM services instead of in-memory models
- Implementing router for directing requests to appropriate LLM endpoints