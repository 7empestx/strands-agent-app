# Clippy Automatic Suggestions Feature Plan

## Overview

Add proactive suggestions to Clippy based on patterns detected across logs, deployments, incidents, and historical data.

## Use Cases

### 1. Error Pattern Detection
- "I've seen 5 similar 504 errors this week on cast-core - the common factor is high memory usage before each incident"
- "This error pattern matches what happened on Oct 7th - we fixed it by increasing Lambda timeout"

### 2. Deployment Correlation
- "Build failures on mrrobot-auth-rest increased 40% since PR #445 was merged"
- "The last 3 failed deploys all touched the authentication module"

### 3. Incident Prevention
- "CloudFront 4xx errors are trending up (currently 2.5%, was 0.5% yesterday) - similar to the docs.mrrobotpay.com outage from last week"
- "ECS memory utilization is at 85% - approaching the threshold that caused OOM issues last month"

### 4. Best Practice Recommendations
- "This PR modifies database migrations but has no rollback plan - consider adding one"
- "The service doesn't have CloudWatch alarms configured for error rate"

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Suggestions Engine                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │ Data         │   │ Pattern      │   │ Suggestion           │ │
│  │ Collectors   │──▶│ Analyzer     │──▶│ Generator            │ │
│  └──────────────┘   └──────────────┘   └──────────────────────┘ │
│        │                   │                     │               │
│        ▼                   ▼                     ▼               │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │ • Coralogix  │   │ • Error      │   │ • Priority Score     │ │
│  │ • CloudWatch │   │   Clustering │   │ • Context Enrichment │ │
│  │ • Bitbucket  │   │ • Time       │   │ • Action Items       │ │
│  │ • PagerDuty  │   │   Correlation│   │ • Historical Link    │ │
│  │ • Jira       │   │ • Anomaly    │   │                      │ │
│  │ • KB Search  │   │   Detection  │   │                      │ │
│  └──────────────┘   └──────────────┘   └──────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Delivery        │
                    │  • Slack DM      │
                    │  • Channel Post  │
                    │  • Dashboard     │
                    │  • Tool Response │
                    └──────────────────┘
```

## Implementation Phases

### Phase 1: Data Aggregation (Foundation)
- Create `src/lib/suggestions/data_collector.py`
- Aggregate data from all sources into a unified format
- Store recent patterns in memory (or DynamoDB for persistence)

```python
@dataclass
class DataPoint:
    source: str  # coralogix, cloudwatch, bitbucket, etc.
    timestamp: datetime
    service: str
    event_type: str  # error, deploy, incident, pr_merged
    severity: str
    message: str
    metadata: dict
```

### Phase 2: Pattern Detection
- Create `src/lib/suggestions/pattern_analyzer.py`
- Implement pattern detection algorithms:
  - **Error clustering**: Group similar errors by message/stack trace
  - **Time correlation**: Link events that happen close together
  - **Trend detection**: Identify increasing/decreasing patterns
  - **Anomaly detection**: Flag unusual activity

```python
class PatternAnalyzer:
    def find_error_clusters(self, errors: list, threshold=0.8) -> list[ErrorCluster]
    def correlate_with_deploys(self, errors: list, deploys: list) -> list[Correlation]
    def detect_trends(self, metrics: list, window_hours=24) -> list[Trend]
    def find_similar_historical_events(self, event: DataPoint) -> list[HistoricalMatch]
```

### Phase 3: Suggestion Generation
- Create `src/lib/suggestions/generator.py`
- Use Claude to generate human-readable suggestions
- Include actionable recommendations

```python
class SuggestionGenerator:
    def generate_suggestion(self, pattern: Pattern, context: dict) -> Suggestion:
        """Use Claude to turn a detected pattern into an actionable suggestion."""

    def prioritize(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        """Rank suggestions by urgency and impact."""
```

### Phase 4: Clippy Integration
- Add `get_suggestions` tool to Clippy
- Proactively offer suggestions when relevant
- Store feedback for improvement

```python
# New tool in clippy_tools.py
_tool(
    name="get_suggestions",
    description="Get proactive suggestions based on recent patterns. Use when user asks 'any suggestions?', 'what should I look at?', or after investigating an issue.",
    properties={
        "service": _param("Service to get suggestions for (optional)"),
        "category": _param("Filter by category: errors, deploys, security, performance"),
    },
)
```

## GPU Acceleration Considerations

### What Could Benefit from GPU
1. **Local Embedding Generation** - If we move from Bedrock KB to local embeddings
2. **Pattern Matching** - Vector similarity search for finding similar historical events
3. **Anomaly Detection** - ML models for detecting unusual patterns

### Current Reality
- **Claude/Bedrock**: AWS managed, already on optimized hardware
- **Coralogix**: External service, no GPU needed
- **Vector Search**: Bedrock KB uses OpenSearch Serverless (managed)

### If We Wanted GPU
- Could use **SageMaker** for custom ML models
- Could run **local LLM** (Llama, Mistral) on GPU instance for embeddings
- **Not recommended** unless we have specific latency/cost requirements

## New Tool Definition

```python
# Add to INVESTIGATION_TOOLS in clippy_tools.py
_tool(
    name="get_suggestions",
    description="""Get proactive suggestions based on patterns in logs, deploys, and incidents.
Use when:
- User asks "anything I should know?" or "any suggestions?"
- After investigating an issue (offer related suggestions)
- User asks about service health broadly
Returns prioritized suggestions with context and recommended actions.""",
    properties={
        "service": _param("Service name (optional - omit for all services)"),
        "hours_back": _param("Hours of data to analyze", "integer", default=24),
        "category": _param("Filter: 'errors', 'deploys', 'security', 'performance', or 'all'", default="all"),
    },
)
```

## Example Suggestion Output

```json
{
  "suggestions": [
    {
      "priority": "high",
      "category": "errors",
      "title": "Recurring 504 errors on cast-core",
      "summary": "5 instances of 504 timeout on syncAll endpoint in the last 24 hours",
      "pattern": "All occurred during peak hours (2-4 PM EST) with memory > 80%",
      "historical_match": "Similar to incident on Oct 7th (DEVOPS-234)",
      "recommended_actions": [
        "Check Lambda memory configuration",
        "Review syncAll query performance",
        "Consider adding circuit breaker"
      ],
      "related_links": [
        "https://bitbucket.org/mrrobot-labs/cast-core-service/...",
        "https://mrrobot.atlassian.net/browse/DEVOPS-234"
      ]
    }
  ],
  "summary": "Found 3 suggestions: 1 high priority, 2 medium"
}
```

## Files to Create

1. `src/lib/suggestions/__init__.py`
2. `src/lib/suggestions/data_collector.py` - Aggregate data from sources
3. `src/lib/suggestions/pattern_analyzer.py` - Detect patterns
4. `src/lib/suggestions/generator.py` - Generate suggestions with Claude
5. `src/lib/suggestions/models.py` - Data classes
6. Update `src/mcp_server/clippy_tools.py` - Add tool definition
7. Update `src/mcp_server/slack_bot/tool_executor.py` - Wire up execution

## Timeline Estimate

- Phase 1 (Data Aggregation): Foundation work
- Phase 2 (Pattern Detection): Core logic
- Phase 3 (Suggestion Generation): Claude integration
- Phase 4 (Clippy Integration): Tool wiring

## Success Metrics

- Suggestions that lead to proactive fixes (before incidents)
- User engagement (do people act on suggestions?)
- False positive rate (suggestions that aren't useful)
- Time saved vs. manual investigation
