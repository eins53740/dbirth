---
title: Jira Task Generation – CSV Ready, Test-First
labels: [codex, jira, tasks, testing]
model: codex-1
---

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

✅ **In short:** Codex must generate detailed, Jira-ready tasks per epic, starting with tests, written in Markdown and convertible into CSV. Tasks should be understandable for both junior and senior engineers, and linked to project documentation.