# Wyoming Bridge

**Wyoming Bridge** is a proof-of-concept project designed to enhance the flexibility of Home Assistant's voice control pipeline. It acts as a proxy between existing services, enabling external services to subscribe to and enrich pipeline events, fostering user experimentation without altering the core system.

> ⚠️🚧 **EXPERIMENTAL & WORK IN PROGRESS** 🚧⚠️
>
> Wyoming Bridge is still in early development. Things may change, and some features ~~might~~ will be missing, incomplete or unstable—so please use it with care and expect a few rough edges as it evolves.
>
> 📚 Documentation and usage examples are planned and will be added as the project develops.

## Home Assistant Voice Control and Wyoming Protocol

Home Assistant's voice control pipeline processes voice commands through four key phases:

1. **Wake Word Detection**: Listens for a trigger phrase to activate the system.
2. **Speech-to-Text (STT/ASR)**: Converts spoken words into text.
3. **Intent Handling**: Interprets the text, executes actions, and generates a response.
4. **Text-to-Speech (TTS)**: Converts the response back into speech.

Services handling these phases are organized into domains, and they communicate via events defined by the [Wyoming protocol](https://github.com/rhasspy/rhasspy3/blob/master/docs/wyoming.md).


## Current Limitations

The current voice pipeline is designed for reliability and clarity, but its structured approach can make it challenging to quickly experiment with new features. Adding functionality—such as speaker identification, language detection, or emotion detection—typically requires defining new phases or domains, which is a careful and deliberate process. There have been many community requests for features like speaker identification, language identification, emotion detection and other enhancements, but these often require changes to the core system, making rapid experimentation difficult.


## Goal of Wyoming Bridge

**Wyoming Bridge** is designed to unlock new possibilities for the Home Assistant voice pipeline. By acting as a proxy between pipeline services, it allows external or experimental services to:

- Subscribe to events
- Enrich events with additional data (such as speaker identity, language information, or emotion)
- Return enhanced events to the pipeline coordinator

This approach enables users to test and develop new features—like speaker identification or emotion detection—without needing to modify the core pipeline. Wyoming Bridge aims to complement the thoughtful design of Home Assistant and the Wyoming protocol by providing a flexible space for experimentation and innovation.

## What Wyoming Bridge is *not*

While Wyoming Bridge encourages experimentation, it is important to clarify its boundaries:

- It is **not** intended to become part of the official Wyoming protocol or replace any core components. Its purpose is to provide a space for rapid prototyping and exploration, not to define new standards.
- It is **not** designed for use in stable, long-term, or production deployments. The bridge is experimental by nature and may change or break as new ideas are tested.

## Installation and Usage

*(TBD as the project develops.)*

## Contributing

*(TBD as the project develops.)*

