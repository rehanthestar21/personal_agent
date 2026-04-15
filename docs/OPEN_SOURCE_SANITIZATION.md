# If this repository was ever public with secrets in git history

This project is configured so **credentials and personal data files are not tracked**. Your local copies stay on disk; they are listed in the root `.gitignore`.

If you **ever pushed** API keys, `.env`, OAuth tokens, Firebase JSON, or `personal_context.md` to a remote:

1. **Treat those credentials as compromised** and rotate them in each provider’s console (OpenAI, Google Cloud, Firebase, Spotify, etc.).
2. **Remove sensitive blobs from git history** on a private clone before making the repo public again, e.g. with [git-filter-repo](https://github.com/newren/git-filter-repo) or BFG Repo-Cleaner, then force-push with coordination if others have clones.
3. Alternatively, create a **new repository** with a single clean commit containing only the sanitized tree (no history).

For day-to-day development, copying `backend/data/*.example` and `backend/mcp_servers/*.example.json` to the real filenames (see README) is enough.
