---
description: Server-Sent Events for real-time updates
icon: waves-sine
---

# SSE Events

The dashboard receives real-time updates via Server-Sent Events (SSE).

## Connect

```javascript
const evtSrc = new EventSource('/api/events');

evtSrc.addEventListener('hive-update', (event) => {
  const data = JSON.parse(event.data);
  console.log('Hive updated:', data);
});
```

## Events

### `hive-update`

Fired when data changes. The event data contains:

```json
{
  "hive": "transformers",
  "action": "ingest",
  "concepts": 3
}
```

Possible actions: `ingest`, `arxiv-import`, `rollback`, `embed`.

## Dashboard behavior

When the dashboard receives a `hive-update` event, it:

1. Re-fetches the meta-graph
2. Re-fetches the hive list
3. If a hive is currently selected, re-fetches its graph data

This ensures the UI is always in sync with the server state.
