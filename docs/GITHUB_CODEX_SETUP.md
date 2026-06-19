# GitHub and Codex Setup

## 1. Install Git

Git is required before this project can be committed or pushed.

Recommended Windows install options:

```powershell
winget install --id Git.Git -e --source winget
```

Or download Git for Windows from:

```text
https://git-scm.com/download/win
```

After installing Git, close and reopen PowerShell.

## 2. Initialize the Repository

Run these commands from the project folder:

```powershell
cd "C:\Users\Phani Santosh\Documents\ai-coding-agent"
git init
git status
git add .
git commit -m "Initial AI coding agent setup"
```

## 3. Create a GitHub Repository

Create a new empty repository on GitHub, then connect it:

```powershell
git branch -M main
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

If you prefer GitHub CLI:

```powershell
gh repo create <your-repo> --private --source . --remote origin --push
```

## 4. Connect GitHub to Codex

Use GitHub as the source of truth for the project, then open the same repository folder in Codex. Codex will read repo files, including `AGENTS.md`, and use them as project-specific guidance.

For Codex code review in GitHub:

1. Set up Codex cloud for the GitHub repository.
2. Open Codex settings for code review.
3. Enable code review for the repository.
4. On a GitHub pull request, comment:

   ```text
   @codex review
   ```

Codex can also use repository guidance from `AGENTS.md` during reviews.

## 5. What To Commit

Commit:

- `agent.py`
- `tools.py`
- `app.py`
- `requirements.txt`
- `.gitignore`
- `README.md`
- `AGENTS.md`
- useful generated app source under `workspace/`

Do not commit:

- `venv/`
- `node_modules/`
- `*.db`
- `workspace/_snapshots/`
- build outputs such as `dist/`, `bin/`, and `obj/`

