# Configure Prompts

You can customize your voice agent's personality, behavior, and response format using system prompts. Prompts are defined in [`prompt.yaml`](../../prompt.yaml) and can be switched or added at runtime via the UI.

## Switching Prompts via the UI

The client UI includes a prompt selector dropdown. Select any prompt to switch during a session. The change takes effect on the next conversation turn.

## Adding Custom Prompts via the UI

You can add custom prompts directly from the UI's **Prompts** tab without editing any files or restarting the server. Custom prompts added in the UI are stored in the browser's localStorage, so they persist for that browser/profile and origin only.

## Available Prompt Presets

The following presets are available in [`prompt.yaml`](../../prompt.yaml):

### Flowershop Assistant (default)

```bash
# In .env
PROMPT_SELECTOR=flowershop
```

**Characteristics:**
- Persona: Flora from GreenForce Garden
- Handles order management, consultations, delivery coordination
- Concise responses (1-2 sentences, max 200 characters)

### Generic Assistant

```bash
# In .env
PROMPT_SELECTOR=generic_assistant
```

Tool calling is enabled automatically for this preset; the other built-in prompts run without function calls.

### Multilingual Voice Assistant

```bash
# In .env
PROMPT_SELECTOR=multilingual_voice_assistant
```

Uses structured `Language: Text: MetaData:` output format for automatic language detection and multilingual responses.

## Changing the Default Prompt

Edit the `.env` file to set the default prompt key (must match a key in `prompt.yaml`):

```bash
PROMPT_SELECTOR=flowershop
```

## Adding Prompts via `prompt.yaml`

To make a prompt available as a built-in option for all users, add an entry to [`prompt.yaml`](../../prompt.yaml). This requires a server restart for the new entry to appear in the UI.

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
