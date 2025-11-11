# Notes

uv venv --python 3.13
./.venv/Scripts/Activate.ps1

uv pip install paho-mqtt python-dotenv protobuf pytest pytest-cov pytest-xdist ruff black mypy jsonschema fastapi uvicorn psycopg[binary]

uv run pip install --upgrade pip    |  python -m pip install --upgrade pip
uv sync --locked --all-extras --dev

which python   |   pip -V

#uv run pytest -m unit --cov=. --cov-report=term-missing --cov-fail-under=70 -q
#uv run pytest -m integration --cov=. --cov-report=term-missing --cov-fail-under=30 -q
#uv run pytest -v --cov=. --cov-report=term-missing --cov-fail-under=70 tests/unit
uv run pytest -v 

------------Mirror CI locally before pushing:-------
uv run ruff check . --fix
uv run black --check .
uv run pytest -v --cov=. --cov-report=term-missing --cov-fail-under=70 tests/unit
pre-commit run --all-files #Commit the auto-fixes later:

pwsh -NoLogo -NoProfile -Command "Set-Location 'd:\GitHub\uns-metadata-sync-svc'; & .\.venv\Scripts\python.exe -m uns_metadata_sync"
 & D:/GitHub/uns-metadata-sync-svc/.venv/Scripts/python.exe d:/GitHub/uns-metadata-sync-svc/my_private/bd_tests.py


# Prompts, New Task Implementation [e.g.: EP04-01]

```Epic 04 – Implementation 01
Reference: [TBD-EP-04-IMP-01]

Task: Implement Feature 01 in EP-04: "Author database migrations for release 1.0"
Check task at: "EP-04 - PostgreSQL Persistence & Constraints.md"

Steps:
Explain what you are going to do to achieve this feature.
Analyse if we are ready to proceed. Do we have all the software required?
Create unit tests
Write unittests for the new feature.
Ensure tests run successfully.
Develop the feature
Implement the required functionality.
Continuously run tests until all pass.
Code validation & quality checks
Run pytest with coverage: uv run pytest -m unit --cov=. --cov-report=term-missing --cov-fail-under=70 -q
Run black (formatting check): uv run black --check .
Run ruff (linting and fixes): uv run ruff check . --fix

Adjustments:
Refactor code until all unit tests pass.
Ensure style, lint, and formatting checks are clean.

Notes:
Ask for clarification if any requirement is missing.
Confirm readiness before starting the implementation.
```


# Codex-1 Instructions — Jira Tasks Generation
```
## 1. Context
We are building a microservice that:
- Listens to **MQTT spB DBIRTH messages**   
- Performs **ETL transformations**
- Stores data in **PostgreSQL**
- Writes later to the **Canary Labs API**

All tasks must align with the project’s **epics**. Documentation for solution design, PostgreSQL schema, and test specifications is available in:

`\uns-metadata-sync-svc\docs`

Tasks must be saved under:

`\uns-metadata-sync-svc\docs\tasks`

---

## 2. Epic-Based Task Creation

For each epic:

- Start with **tests first** (test-driven approach).
    
- Organize tasks by test type:
    
    1. **Unit Tests**
        
        - Parsing & normalization of UNS paths
            
        - Property typing and validation
            
        - Idempotent upsert logic
            
        - Diff computation (before/after state)
            
        - Retry & backoff utilities
            
    2. **Integration Tests**
        
        - MQTT ingest → DB writes
            
        - DB writes → CDC consumer
            
        - CDC consumer → Canary client
            
    3. **Contract Tests**
        
        - Sparkplug payload decode (binary + JSON fixtures)
            
        - Canary client request/response shape
            

For each area, create tasks in **JIRA-friendly format**, with:

- Task ID placeholder
    
- Summary
    
- Description
    
- Acceptance criteria
    
- Clear language for both junior and senior engineers
    

---

## 3. Task Documentation Rules

Every task must include:

- **Epic Number**: Prefix or reference (e.g., _EP-03_).
    
- **Summary**: Short, action-oriented title (max 1–2 lines).
    
    - Example: _“Implement UNS path normalization parser”_
        
- **Description**: Detailed explanation with:
    
    - Background context
        
    - In-scope vs. out-of-scope
        
    - Links to docs (`\uns-metadata-sync-svc\docs`)
        
    - Use Markdown / Atlassian wiki syntax (checklists, tables, code blocks)
        
- **Acceptance Criteria**: Clear, testable conditions.
    
- **Acronyms**:
    
    - _IT_ = Integration Tests
        
    - _IMP_ = Implementation  
        (avoid “TI” for both)
        

---

## 4. Jira Import Requirements

Tasks must be Markdown **and** convertible to CSV, ready for Jira import.  
Minimum required Jira fields:

- **Summary**
    
- **Issue Type** (Task, Sub-task)
    
- **Parent ID** (Epic or Story link)
    
- **Description**
    
- **Priority**
    
- **Acceptance Criteria**
    
- **Labels**
    
- **Story Points**
    

Follow Atlassian’s CSV import guide:  
[https://support.atlassian.com/jira-cloud-administration/docs/import-data-from-a-csv-file/](https://support.atlassian.com/jira-cloud-administration/docs/import-data-from-a-csv-file/)

---

## 5. Deliverables
For each epic:
1. Several **Markdown documents** containing all tasks for each individual epic,  stored in `\uns-metadata-sync-svc\docs\tasks. 
2. One **CSV file** generated from the Markdown files, ready to import into Jira.
---
```