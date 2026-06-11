"""Module entry point so `python -m agent.refresh` works.

This module delegates entirely to agent.cli.main(), keeping all real logic in
cli.py where it can be imported and inspected without triggering execution.
"""

from agent.cli import main

if __name__ == "__main__":
    main()
