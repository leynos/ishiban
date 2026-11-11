Feature: Published Ishiban commands
  Scenario: The documented collector and server use one isolated workspace
    Given the published collector and server examples
    When I run their Cyclopts commands with read-only Lody fixtures
    Then the collector identity reaches a loopback-only server
