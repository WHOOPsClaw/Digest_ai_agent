#!/bin/bash
# One-liner install: curl -sSL https://raw.githubusercontent.com/newsbrief/newsbrief/main/scripts/install.sh | bash

set -e

echo "Installing newsbrief..."

# Check requirements
command -v docker >/dev/null 2>&1 || { echo "Docker required. https://docs.docker.com/get-docker/"; exit 1; }

# Clone
INSTALL_DIR="${NEWSBRIEF_DIR:-$HOME/newsbrief}"
if [ -d "$INSTALL_DIR" ]; then
  echo "Directory exists: $INSTALL_DIR"
  cd "$INSTALL_DIR" && git pull
else
  git clone https://github.com/newsbrief/newsbrief "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

echo "Installed to $INSTALL_DIR"
echo ""
echo "Next steps:"
echo "  cd $INSTALL_DIR"
echo "  docker compose run --rm newsbrief setup"
echo "  docker compose up -d"
