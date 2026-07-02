"""repo-oracle entry point: python -m repo_oracle"""

import sys
from repo_oracle.cli import app

if __name__ == "__main__":
    app(sys.argv[1:] if len(sys.argv) > 1 else None)
