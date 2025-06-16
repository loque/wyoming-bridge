---
applyTo: "**"
---

# WyomingBridge Glossary

### **Server**

The Wyoming component connected to the bridge that initiates event flows.

- Typically **Home Assistant**'s voice pipeline coordinator or a **Wyoming Satellite**.
- Initiates events such as `audio-start`, `audio-chunk`, `detect`, etc.
- The bridge forwards original events back to the Server after processing by the Target and any relevant Processors.

### **Upstream**

Refers to the direction _toward_ the Server.

### **Target**

The primary Wyoming service that the bridge wraps.

- Receives events originating from the Server (after optional preprocessing by processors).
- Emits core output events expected by Assist (e.g. `detection` for wake-word phase).
- Examples: `openWakeWord`, `faster-whisper`, `Piper`, etc.

### **Downstream**

All services connected **behind** the bridge — includes both the Target and Processors.

### **Processor**

Any additional Wyoming service connected to the bridge that participates in the orchestration of voice processing.
Processors are configured with one or more Subscriptions that define how they interact with specific events in the
bridge's pipeline.

### **Subscription**

The declaration inside a Processor's configuration that describes how it interacts with specific events. Each
subscription defines:

- Which event type the Processor listens to (`event`).
- At what processing stage the subscription is active (`stage`: `pre_target` or `post_target`).
  - `pre_target`: Before the event is sent to the Target service.
  - `post_target`: After the event is received from the Target service.
- How the bridge interacts with the Processor for this specific event (`mode`: `blocking` or `non_blocking`).
  - `blocking`: The bridge sends the event and waits for the Processor to finish. The Processor may return an `ext`
    field in its response (see **ext (Extensions)**).
  - `non_blocking`: The bridge sends the event to the Processor and continues processing without waiting for a response.

### **Observer Pattern**

A conceptual role for a Processor whose Subscriptions are primarily configured to observe or log events.

- Implements fire-and-forget delivery using `non_blocking` Subscription modes.
- Receives copies of events for observation or logging.
- Does not block or influence the main event flow.
- Can have Subscriptions for events at different stages (`pre_target` or `post_target`).

### **Enricher Pattern**

A conceptual role for a Processor whose Subscriptions are configured to participate in modifying or adding data to an
event.

- Implements `blocking` Subscription modes for specific events.
- When a `blocking` Subscription is triggered, the bridge waits for the Processor to complete.
- The Processor, for that `blocking` Subscription, can return an `ext` field in its response. This field is a dictionary
  of key/value pairs (see **ext (Extensions)**).
- The bridge collects all `ext` data from Processors responding to `blocking` Subscriptions for a given event and sends
  it as updates to Home Assistant via the `input_text` integration.

### **ext (Extensions)**

A dictionary of arbitrary key/string value pairs that a processor can include in its response event when its `blocking`
subscription is triggered. The bridge collects these extensions from all responding `blocking` subscriptions for a given
event and sends them as updates to Home Assistant using the `input_text` integration. This allows processors to
communicate or store state/metadata related to the event processing for later use.
