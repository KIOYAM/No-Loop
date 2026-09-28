# Public Source Links

## Repositories
- JobSync: https://github.com/Gsync/jobsync
- JobMatch AI: https://github.com/SamlyticsDS/jobmatch-ai
- Aipply: https://github.com/attdobi/aipply
- AutoApply: https://github.com/AbhishekMandapmalvi/AutoApply
- JobMatch AI Extension: https://github.com/wadekarg/JobMatchAI
- Job Scraper: https://github.com/ScottCoffin/Job_Scraper
- AI Job Application Bot: https://github.com/Vigneshyadala/ai-job-application-bot
- job-apply-bot: https://github.com/dsharm9148/job-apply-bot

## Local inspection
Clone an allowed repository:
    git clone <REPOSITORY_URL>

Then:
    cd <REPOSITORY>
    git log --oneline -20
    git branch -a
    git remote -v

Inspect top-level files:
    git ls-files | head -200

Find architecture/config:
    find . -maxdepth 3 -type f | sort

Windows PowerShell alternative:
    Get-ChildItem -Recurse -File | Select-Object -First 200 FullName

Check license:
    Get-Content LICENSE -ErrorAction SilentlyContinue

Search for relevant implementation:
    git grep -n -i "playwright|selenium|resume|cover letter|job match|greenhouse|lever|workday|ashby|ollama"

Python projects:
    python -m venv .venv
    # activate the venv
    pip install -r requirements.txt

Node projects:
    npm install

Do NOT execute unknown install scripts blindly. Read package manifests and README first.

## Evidence capture
For every reference, record:
- repository URL
- commit/tag inspected
- license
- feature
- relevant files
- relevant classes/functions
- architectural lesson
- whether No-loop can reuse code under the license
- whether only the idea should be reimplemented
