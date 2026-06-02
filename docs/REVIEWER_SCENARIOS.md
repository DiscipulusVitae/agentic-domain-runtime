# Reviewer Scenarios Draft

This document outlines reviewer scenarios designed for technical reviewers to verify the capabilities of `agentic-domain-runtime` using purely synthetic fixtures and local configuration.

---

## 1. Butler-First Routing Scenario

### Objective
Verify that the `core.butler` router can parse free-form, unstructured user inputs and dynamically delegate them to the correct domain assembly without pre-defined command trees or static menu states.

### Execution Path
1. The reviewer submits a free-text message simulating a user interaction.
2. The Butler Core processes the intent and returns a routing decision.

### Scenario Example
- **Input text**: `"I just read page 45 of Chronicles of the Green Archive and really liked the chapter."`
- **Expected routing outcome**: 
  - Target Domain: `Books Domain Assembly`
  - Action/Intent: `reading_progress_update`
  - Parameters: `{ "title": "Chronicles of the Green Archive", "page": 45 }`
- **Alternative Input text**: `"Here is the list for my Martian Tomato Salad: 3 tomatoes, 1 onion, olive oil."`
- **Expected routing outcome**:
  - Target Domain: `Kitchen Domain Assembly`
  - Action/Intent: `recipe_capture`
  - Parameters: `{ "recipe_name": "Martian Tomato Salad" }`

---

## 2. Kitchen Capture & Editing Scenario

### Objective
Verify extraction of structured recipes from unstructured text or batch image uploads, and show how reviewers can modify the parsed draft before committing it.

### Execution Path
1. The reviewer inputs a raw recipe text.
2. The Kitchen Domain Assembly runs the extraction logic, producing a schema-validated JSON draft.
3. The reviewer simulates a correction to the draft and commits it to the database namespace.

### Scenario Example
- **Step 1: Input text**:
  ```text
  Synth-Waffles
  Mix 2 cups of synthetic flour and 1 cup of almond milk.
  Bake in a preheated waffle iron for 8 minutes.
  ```
- **Step 2: Extracted Draft Schema**:
  ```json
  {
    "title": "Synth-Waffles",
    "ingredients": [
      { "name": "synthetic flour", "amount": "2 cups" },
      { "name": "almond milk", "amount": "1 cup" }
    ],
    "steps": [
      "Mix synthetic flour and almond milk.",
      "Bake in a preheated waffle iron for 8 minutes."
    ]
  }
  ```
- **Step 3: Verification**: The reviewer updates the ingredient to "oat milk" and verifies that the deterministic validator accepts the change and persists the row in the `kitchen` database namespace.

---

## 3. Books Catalog & Progress Scenario

### Objective
Validate reading log updates, shelf categorization, and progress tracking functionality using public domain literary works.

### Execution Path
1. Seed the database with a fictional library catalog.
2. Simulate progress updates from a reviewer.
3. Verify calculations for completion percentages.

### Scenario Example
- **Initial Catalog State**:
  - Book: `"Fictional Journey"` by Arthur Dystopian (Total Pages: 120)
  - Book: `"Chronicles of the Green Archive"` by Victor Classic (Total Pages: 150)
- **Reviewer Action**: Updates progress: `"Finished page 30 of Fictional Journey."`
- **Expected Database State**: 
  - Current page: `30`
  - Completion: `25%`
  - Reading sessions log: `[ { "timestamp": "2026-05-28T12:00:00Z", "pages_read": 30 } ]`

---

## 4. Health-Log Capture: Capture, Extraction, Validation, and Persistence

### Objective
Verify the end-to-end flow of structured capture/extraction of daily health parameters, executing deterministic validation and database persistence while strictly adhering to safety boundaries.

### Safety Note
This scenario is limited exclusively to event capture and logging. The system performs no clinical assessment, healthcare guidance, therapy recommendations, computer-aided clinical analysis, or urgent care sorting.

### Execution Path
1. The reviewer submits a text representation of physical log events.
2. The LLM extraction component parses the data into structured metrics.
3. The deterministic validation module checks the ranges.
4. The verified metrics are persisted.

### Scenario Example
- **Step 1: Raw Input**: `"Today physical logs: walk 10000 steps, weight 75kg, sleep 8 hours."`
- **Step 2: LLM Extraction Output**:
  ```json
  {
    "steps": 10000,
    "weight_kg": 75.0,
    "sleep_hours": 8.0
  }
  ```
- **Step 3: Deterministic Validation**:
  - Check: `steps >= 0` (Passed)
  - Check: `weight_kg > 0` (Passed)
  - Check: `sleep_hours >= 0 and sleep_hours <= 24` (Passed)
- **Step 4: Persistence**: The values are stored securely inside the isolated `health` storage namespace.

---

## 5. Observability and Trace Verification Scenario

### Objective
Enable reviewers to inspect execution traces and performance logs to understand the path of a request without exposing operational host configurations or private developer history.

### Execution Path
1. Run a test transaction using a synthetic persona.
2. Retrieve the transaction trace from the observability dashboard or test logs.

### Scenario Example
- **Trace Output Log**:
  ```text
  [2026-05-28T12:00:00.001Z] INFO  core.bootstrap: Starting transaction for user_id: 123456789
  [2026-05-28T12:00:00.050Z] DEBUG core.butler: Unstructured payload received. Routing to Books Domain.
  [2026-05-28T12:00:00.200Z] DEBUG books.extraction: LLM extraction started.
  [2026-05-28T12:00:00.850Z] INFO  books.validation: Extraction payload validated successfully.
  [2026-05-28T12:00:00.900Z] INFO  books.storage: Record persisted. Rows affected: 1. Transaction committed.
  ```
- All log details are fully standardized, containing no real network routing addresses, external endpoint credentials, or platform provider identifiers.
