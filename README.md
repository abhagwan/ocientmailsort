# Mailsort
## Updated 
Mailsort - Rule Causation Explorer (XAI)
[Project Overview]
[Why]
 Explainable AI (Rule Causation Explorer)
Current State: The Web UI shows what happened. Enhancement: Add a "Why did this happen?" view. For a specific move, show the evidence: "This was moved to Shopping because it matched the sender_domain rule for amazon.com, which has a 98% success rate over the last 50 emails."
[Enhancement 1]
Subject Regex Rules Skip the Confidence Threshold — actual bug
File: src/mailsort/classifier/rules.py:62-69

Every other rule type checks rule["confidence"] >= threshold before returning — but the subject_regex loop doesn't. A low-confidence regex rule will fire unconditionally. Fix is one if statement:


for rule in self._find_rules_by_type("subject_regex"):
    try:
        if re.search(rule["condition_value"], features.subject):
            if rule["confidence"] < threshold:   # ← add this check
                continue
            ...


All 209 tests pass (208 original + 1 new).

Summary of what was done:

Bug fixed in C:\AvinashProject\mailsort\src\mailsort\classifier\rules.py: subject_regex rules now correctly check the confidence threshold before matching, consistent with all other rule types.
New test added in tests/test_rules.py: test_subject_regex_below_threshold_returns_none — this would have caught the bug originally.




[Enhancement 2]
This enhancement adds the Rule Causation Explorer to Mailsort, providing transparency to the "deterministic-first" classification pipeline. It transforms the system from a "black box" into an explainable assistant by surfacing the specific evidence and historical reliability behind every automated email move.
Self-hosted email classification service for Fastmail. Periodically scans read, unflagged inbox messages and moves them to the appropriate subfolder using deterministic rules and an LLM classifier.
Why: Explainable AI (XAI)
The "Why did this happen?" view was chosen to reinforce Mailsort’s core philosophy of user-controlled automation:
Trust: Replaces opaque automation with data-backed logic (e.g., "Matched sender_domain for amazon.com").
Performance Tracking: Displays real-time success rates (e.g., "98% success over 50 emails") based on your actual manual corrections.
Actionable Debugging: Quickly identifies which rules are underperforming or require "Confidence Decay" adjustments.
Setup & Implementation
Environment: Requires Python 3.12.
Database: Utilizes existing SQLite audit_log and rules tables.
Run Application: python -m mailsort.main
[Testing & Quality Assurance]
Following Mailsort’s disciplined methodology (Phase Cards & Dry-Run Safety), this feature was validated using a "Closed Loop" strategy:
1. How I Thought About Testing
Testing focuses on the relationship between automated moves and manual corrections. If a user moves an email back, the "Explainable" logic must immediately reflect a drop in that rule's success rate.
2. Validation Layers
Unit (tests/test_rules.py): Validates the SQL CTE logic that calculates success rates by joining automated entries with manual overrides.
Web (tests/test_web_rules.py): Ensures the controller correctly handles different classification sources (Rule Engine, LLM, or Thread Context) and returns the proper template context.
Integration (tests/test_integration.py): Verifies the full feedback loop—simulating an automated move, followed by a manual correction, and confirming the "Why?" view updates the statistical evidence.
3. Run Tests
pytest tests/test_rules.py tests/test_web_rules.py tests/test_integration.py


-[Core Logic: Reliability Calculation]
The system identifies "Success Rate" by looking at the last 50 emails processed by a specific rule and subtracting instances where a manual classification exists for the same message_id. This ensures the explanation is always grounded in recent user behavior.

## Documentation

- [Product Requirements](docs/prd.md) — goals, scope, user stories
- [Architecture](docs/architecture.md) — component diagram, bootstrap & per-run sequences
- **Design docs** — detailed subsystem design:
  - [JMAP Integration](docs/design/jmap-integration.md)
  - [Classification Pipeline](docs/design/classification.md)
  - [Learning & Auto-Rules](docs/design/learning.md)
  - [Audit Log](docs/design/audit.md)
  - [Data Models](docs/design/data-models.md)
  - [Web UI](docs/design/web-ui.md)
- [Configuration Reference](docs/configuration.md)
- [Operations & Deployment](docs/operations.md)
- **Planning** — [phases](docs/planning/phases.md), [open questions](docs/planning/open-questions.md), [system test plan](docs/planning/system-test-plan.md)
- **Dev** — [changelog](docs/dev/changelog.md), [design ideas](docs/dev/design-ideas.md), [scratch notes](docs/dev/scratch.md)

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Validate config and Fastmail connectivity
mailsort check-config

# Bootstrap: scan existing folders to seed rules
mailsort bootstrap

# Single classification pass (useful for testing)
mailsort run

# Dry run: classify but don't move
mailsort dry-run

# Start the scheduler (runs every N minutes)
mailsort start
```

## Docker

```bash
cp .env.example .env  # add your API tokens
docker compose up -d
```

## Configuration

Edit `config.yaml`. API tokens are set via environment variables:

- `FASTMAIL_API_TOKEN` — Fastmail API token
- `ANTHROPIC_API_KEY` — Anthropic API key (for LLM classification)

## Development

```bash
pip install -e ".[dev]"
pytest
```
