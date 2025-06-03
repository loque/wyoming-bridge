---
applyTo: "**"
---

# 📖 WyomingBridge Glossary

---

### **Source**

The upstream Wyoming component connected to the bridge.

- Usually **Home Assistant Assist**.
- Initiates events such as `audio-start`, `audio-chunk`, `detect`, etc.
- The bridge forwards enriched events back to the Source after processing.

### **Upstream** _(synonym of Source in bridge docs)_

Refers generally to the direction _toward_ Assist.

### **Target**

The primary Wyoming service that the bridge wraps.

- Receives events originating from the Source (after optional preprocessing by processors).
- Emits core output events expected by Assist (e.g. `detection` for wake-word phase).
- Examples: `openWakeWord`, `faster-whisper`, `Piper`, etc.

### **Downstream**

All services connected **behind** the bridge — includes both the Target and Processors.

### **Processor**

Any additional Wyoming service connected to the bridge that can:

- Observe events (`observer` role)
- Enrich events (`enricher` role)
- Participate in the orchestration of voice processing.

### **Observer (Processor Role)**

- Receives copies of events for observation or logging.
- Does not block or influence the event flow.
- Can subscribe to events originating from the Source or Target.
- Fire-and-forget delivery.

### **Enricher (Processor Role)**

- Participates in enrichment of an event.
- The bridge waits for all enrichers to return enrichment data before forwarding the event upstream.
- Enrichers may depend on other enrichers via `depends_on`.

### **Subscription**

The declaration inside processor configuration describing:

- Which event type the processor listens to (`event`).
- Origin of the event (`source` or `target`).
- In what role (`observer` or `enricher`).
- Optional dependencies (`depends_on`) for enrichers.

Each subscription defines **when** and **how** a processor participates in processing.
