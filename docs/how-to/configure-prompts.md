# Configure Prompts

You can customize your voice agent's personality, behavior, and response format using system prompts. Built-in prompts are defined in example-local `prompts.yaml` files and can be switched or added at runtime via the UI.

## Switching Prompts via the UI

The client UI includes a prompt selector dropdown. Select any prompt to switch during a session. The change takes effect on the next conversation turn.

## Adding Custom Prompts via the UI

You can add custom prompts directly from the UI's **Prompts** tab without editing any files or restarting the server. Custom prompts added in the UI are stored in the browser's localStorage, so they persist for that browser/profile and origin only.

## Available Prompt Presets

Prompt presets are defined per example. The Generic Cascaded example currently provides the presets below (the active default is set by `defaults.prompt` in `examples_registry.yaml`).

### Generic Assistant (default)

**Characteristics:**
- General-purpose Nemotron voice assistant
- Tool calling is enabled automatically for this preset (Flowershop runs without function calls)
- Single-sentence responses (≤ 75 characters; tool results passed through verbatim)

### Flowershop Assistant

**Characteristics:**
- Persona: Flora from GreenForce Garden
- Handles order management, consultations, delivery coordination
- Concise responses (1-2 sentences, max 200 characters)

> The **Multilingual Voice Assistant** preset (structured `Language: / Text: / MetaData:` output) ships with the separate Multilingual example — see [Enable Multilingual Voice Agent](./enable-multilingual.md).

## Changing the Default Prompt

Set the per-example default with `defaults.prompt` in `examples_registry.yaml`. As a fallback (when that key isn't one of the active example's prompt keys in `prompts.yaml`), the entry marked `default: true` is used, otherwise the first entry.

```yaml
my_prompt:
  default: true
  description: "Your prompt description"
  content: |
    ...
```

## Adding Built-In Prompts via `prompts.yaml`

To make a prompt available as a built-in option for all users of an example, add an entry to that example's `prompts.yaml`, such as [`src/examples/generic/prompts.yaml`](../../src/examples/generic/prompts.yaml). The client loads built-in prompts for the active example. Refresh open browser tabs after editing YAML.

```yaml
my_custom_prompt:
  description: "Your prompt description"
  content: |
    Your system prompt here...
    Define personality, rules, and response format.
```

## Best Practices for Voice Prompts

- Keep responses concise (1-2 sentences, less than 200 characters).
- Avoid special characters like `*`, `-`, `/` in output.
- Avoid bullet points or numbered lists (breaks voice flow).
- Define clear output format for structured data.
- Use plain text only.
