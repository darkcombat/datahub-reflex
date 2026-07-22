# Publishing DataHub Reflex

The local repository is prepared with a clean `main` branch. Publishing it
requires a GitHub repository URL and the user's GitHub authentication.

## First publication

Create an empty public GitHub repository named `datahub-reflex`, then run from
the project root:

```powershell
.\scripts\publish_github.ps1 -RemoteUrl https://github.com/darkcombat/datahub-reflex.git
```

The script refuses to replace an existing remote, to publish a dirty working
tree, or to publish a branch other than `main`.

Do not create an additional README, license, or `.gitignore` on GitHub: those
files are already part of this repository.

## Verify the public repository

Use a new directory and run:

```powershell
git clone https://github.com/darkcombat/datahub-reflex.git
cd datahub-reflex
python -m pip install -e ".[dev]"
python scripts/audit_submission.py
python -m pytest -q tests/unit tests/evaluation tests/ui
python examples/evaluation/run_evaluation.py
```

For the live path, start the tested DataHub Quickstart and then seed it:

```powershell
python -m datahub docker quickstart
python scripts/seed_live_datahub.py seed
python scripts/seed_live_datahub.py verify
python -m pytest -q tests/integration/test_live_datahub.py
```

## Submission metadata

After the public clone succeeds, record both URLs in
`docs/submission_checklist.md` and use the public repository URL in the
Devpost submission. The required category is `Agents That Do Real Work`.
