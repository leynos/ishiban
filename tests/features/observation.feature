Feature: Honest observer reconciliation
  Scenario: A metadata refresh cannot erase proven completion
    Given a fresh observation journal
    When a persisted completion is followed by a metadata-only restart
    Then the completion is retained as evidence from the earlier generation
