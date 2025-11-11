---
epic_id: EP-09
epic_title: Test Infrastructure & Quality Gates
status: draft
last_updated: 2025-09-23
sources:
  - docs/epics/EP-09 - Test Infrastructure & Quality Gates.md
  - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md
  - docs/Metadata Sync Microservice Solution Design - Release 1.0.md
jira_defaults:
  parent_id: EP-09
  issue_type: Task
  priority: High
  labels:
    - uns-meta
    - ep09
---

## Unit Tests

#### [TBD-EP-09-UT-01] Fixture loader unit tests
- **Summary**: Fixture loader unit tests
- **Issue Type**: Task
- **Parent ID**: EP-09
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep09, unit-test
- **Description**:
  - **Background**: Central fixture loader must support Sparkplug payloads, UNS paths, and database snapshots.
  - **In Scope**:
    - Implement tests verifying fixture discovery, schema validation, and caching.
    - Ensure loader handles versioned fixtures with semantic version enforcement.
    - Provide fail-fast errors when fixture missing.
  - **Out of Scope**:
    - Fixture content authoring (handled in other epics).
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (Testing infrastructure)
- **Acceptance Criteria**:
  - [ ] Unit tests confirm loader returns typed fixture objects.
  - [ ] Missing fixture surfaces descriptive error.
  - [ ] Version mismatches cause test failure with remediation hint.

#### [TBD-EP-09-UT-02] Test harness utilities coverage
- **Summary**: Test harness utilities coverage
- **Issue Type**: Task
- **Parent ID**: EP-09
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep09, unit-test
- **Description**:
  - **Background**: Shared test utilities (e.g., correlation id generator, clock mocks) require coverage to ensure stability.
  - **In Scope**:
    - Add tests for deterministic ID generation, time travel controls, and logging assertions.
    - Ensure utilities thread-safe and documented.
    - Validate utilities support parallel test execution.
  - **Out of Scope**:
    - Production runtime utilities.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Testing approach)
- **Acceptance Criteria**:
  - [ ] Utilities operate correctly under concurrency tests.
  - [ ] Logging assertions capture structured entries.
  - [ ] Clock mocks support time jumps without flakiness.

#### [TBD-EP-09-UT-03] Coverage threshold guard tests
- **Summary**: Coverage threshold guard tests
- **Issue Type**: Task
- **Parent ID**: EP-09
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep09, unit-test
- **Description**:
  - **Background**: Need automated guards to ensure minimum coverage levels.
  - **In Scope**:
    - Add unit tests verifying coverage report parser rejects builds below threshold.
    - Ensure parser handles multiple language reports (Go, Python, SQL tests) if present.
    - Provide human-friendly failure messaging.
  - **Out of Scope**:
    - Actual coverage improvements (handled per epic).
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (Quality gates)
- **Acceptance Criteria**:
  - [ ] Guard fails pipeline when coverage < target.
  - [ ] Reports aggregated and published in artifacts.
  - [ ] Failure message links to remediation doc.

## Integration Tests

#### [TBD-EP-09-IT-01] Full pipeline smoke test harness
- **Summary**: Full pipeline smoke test harness
- **Issue Type**: Task
- **Parent ID**: EP-09
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep09, integration-test
- **Description**:
  - **Background**: Provide automated smoke test orchestrating MQTT -> decode -> Postgres -> CDC -> Canary mock.
  - **In Scope**:
    - Compose existing harnesses into single workflow.
    - Validate key metrics, logs, and data persistence at each stage.
    - Run in CI nightly with artifact capture.
  - **Out of Scope**:
    - Performance benchmarking.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (End-to-end testing)
- **Acceptance Criteria**:
  - [ ] Smoke test passes in CI and fails fast on regression.
  - [ ] Artifacts include logs, metrics, DB snapshots for debugging.
  - [ ] Execution time under 20 minutes.

#### [TBD-EP-09-IT-02] CI environment provisioning test
- **Summary**: CI environment provisioning test
- **Issue Type**: Task
- **Parent ID**: EP-09
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep09, integration-test
- **Description**:
  - **Background**: Ensure infrastructure setup scripts (containers, secrets) function reliably in CI.
  - **In Scope**:
    - Add integration test verifying container orchestration and secret injection.
    - Capture timing metrics for setup phases.
    - Provide failure diagnostics when provisioning fails.
  - **Out of Scope**:
    - Production provisioning.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (DevOps)
- **Acceptance Criteria**:
  - [ ] CI job provisions services without manual steps.
  - [ ] Failures emit actionable logs and hints.
  - [ ] Setup duration tracked for optimization.

## Contract Tests

#### [TBD-EP-09-CT-01] CI quality gate contract
- **Summary**: CI quality gate contract
- **Issue Type**: Task
- **Parent ID**: EP-09
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep09, contract-test
- **Description**:
  - **Background**: Document and enforce list of required checks before merge.
  - **In Scope**:
    - Define YAML manifest enumerating required jobs, coverage thresholds, linting.
    - Add contract test verifying manifest vs actual pipeline.
    - Publish manifest for team visibility.
  - **Out of Scope**:
    - Tool-specific configuration (handled in downstream repos).
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (Quality gates)
- **Acceptance Criteria**:
  - [ ] Contract test fails when pipeline deviates from manifest.
  - [ ] Manifest stored at `docs/contracts/ci_quality_gates.yaml`.
  - [ ] Reviews required for manifest changes.

## Implementation

#### [TBD-EP-09-IMP-01] Build unified test harness CLI
- **Summary**: Build unified test harness CLI
- **Issue Type**: Task
- **Parent ID**: EP-09
- **Priority**: High
- **Story Points**: 4
- **Labels**: uns-meta, ep09, implementation
- **Description**:
  - **Background**: Simplify running unit/integration/contract tests locally.
  - **In Scope**:
    - Create CLI that orchestrates test suites, environment setup, and reporting.
    - Provide options for selective test categories.
    - Emit summary JSON consumed by CI.
  - **Out of Scope**:
    - GUI for test execution.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Developer workflow)
- **Acceptance Criteria**:
  - [ ] CLI runs on Windows/Linux/macOS.
  - [ ] Produces exit codes aligning with CI requirements.
  - [ ] Documentation updated.

#### [TBD-EP-09-IMP-02] Set up CI pipeline with parallel stages
- **Summary**: Set up CI pipeline with parallel stages
- **Issue Type**: Task
- **Parent ID**: EP-09
- **Priority**: Medium
- **Story Points**: 5
- **Labels**: uns-meta, ep09, implementation
- **Description**:
  - **Background**: Optimize CI throughput by running unit, integration, contract tests in parallel.
  - **In Scope**:
    - Configure workflow (GitHub Actions/Azure DevOps) with caching and parallelization.
    - Integrate quality gates manifest.
    - Publish artifacts for logs, coverage, contracts.
  - **Out of Scope**:
    - CD deployment.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (CI requirements)
- **Acceptance Criteria**:
  - [ ] Pipeline executes in under 30 minutes on baseline hardware.
  - [ ] Failures surface clear context and links to artifacts.
  - [ ] Gates enforced before merge allowed.

#### [TBD-EP-09-IMP-03] Testing documentation and onboarding
- **Summary**: Testing documentation and onboarding
- **Issue Type**: Task
- **Parent ID**: EP-09
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep09, documentation
- **Description**:
  - **Background**: Provide onboarding guide for developers to run tests locally and interpret CI results.
  - **In Scope**:
    - Document prerequisites, commands, troubleshooting.
    - Explain quality gates and waiver process.
    - Link to harness CLI and fixtures.
  - **Out of Scope**:
    - Corporate onboarding.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (Onboarding)
- **Acceptance Criteria**:
  - [ ] Guide stored at `docs/runbooks/testing-onboarding.md`.
  - [ ] Includes flowchart for selecting test suites.
  - [ ] Reviewed by new hire buddy program.
