# Configure Prompts

You can customize your voice agent's personality, behavior, and response format using system prompts. Built-in prompts are defined in example-local `prompts.yaml` files and can be switched or added at runtime via the UI.

## Switching Prompts via the UI

The client UI includes a prompt selector dropdown. Select any prompt to switch during a session. The change takes effect on the next conversation turn.

## Adding Custom Prompts via the UI

You can add custom prompts directly from the UI's **Prompts** tab without editing any files or restarting the server. Custom prompts added in the UI are stored in the browser's localStorage, so they persist for that browser/profile and origin only.

## Available Prompt Presets

Prompt presets are defined per example. The generic cascaded example currently provides the presets below.

### Flowershop Assistant (default)

**Characteristics:**
- Persona: Flora from GreenForce Garden
- Handles order management, consultations, delivery coordination
- Concise responses (1-2 sentences, max 200 characters)

### Generic Assistant

Tool calling is enabled automatically for this preset; the other built-in prompts run without function calls.

### Multilingual Voice Assistant

Uses structured `Language: Text: MetaData:` output format for automatic language detection and multilingual responses.

## Changing the Default Prompt

Mark the desired entry with `default: true` in the active example's `prompts.yaml`. If no entry is marked, the first entry is used.

```yaml
my_prompt:
  default: true
  description: "Your prompt description"
  content: |
    ...
```

## Adding Built-In Prompts via `prompts.yaml`

To make a prompt available as a built-in option for all users of an example, add an entry to that example's `prompts.yaml`, such as [`src/cascaded/generic/prompts.yaml`](../../src/cascaded/generic/prompts.yaml) or [`src/speech_to_speech/generic/prompts.yaml`](../../src/speech_to_speech/generic/prompts.yaml). The client loads built-in prompts for the active example; refresh open browser tabs after editing YAML.

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
