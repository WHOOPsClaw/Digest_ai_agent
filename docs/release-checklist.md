# Release Checklist

Before releasing v0.X.0:

- [ ] All tests pass: `pytest`
- [ ] Lint clean: `ruff check`
- [ ] Docs updated (README, CHANGELOG)
- [ ] Version bumped in pyproject.toml + __init__.py
- [ ] Test Docker build: `docker build -t newsbrief:test .`
- [ ] Test setup wizard end-to-end manually
- [ ] Create GitHub Release (draft)
- [ ] Push tag: `git push origin v0.X.0`
- [ ] Verify CI passes on release
- [ ] Verify Docker image pushed to GHCR
- [ ] Verify PyPI package published
- [ ] Announcement:
  - [ ] GitHub Discussions
  - [ ] Twitter/Mastodon
  - [ ] HackerNews (Show HN)
  - [ ] Reddit r/selfhosted
  - [ ] ProductHunt
