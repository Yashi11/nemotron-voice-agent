# Configure TTS Settings

The Text-to-Speech (TTS) system supports multiple voices and languages using the [NVIDIA Magpie TTS model](https://build.nvidia.com/nvidia/magpie-tts-multilingual/modelcard). TTS services are defined in the selected example's `services.cloud.yaml` or `services.local.yaml`, and voices can be changed from the UI.

## Default Configuration

The default cloud TTS service is defined in the selected example's `services.cloud.yaml`:

```yaml
tts:
  magpie-tts:
    name: "Magpie TTS Multilingual"
    server: "grpc.nvcf.nvidia.com:443"
    voice_id: "Magpie-Multilingual.EN-US.Aria"
    function_id: ""
```

The voice ID format of the Magpie Multilingual TTS model is `Model.Language.VoiceName`.

**Note:** The available voices depend on your Magpie TTS model version. Refer to the [NVIDIA Magpie TTS documentation](https://docs.nvidia.com/nim/riva/tts/latest/support-matrix.html#available-voices) for the complete voice list.

## Changing TTS Voice from the UI

The client UI includes a voice selector. Available voices and languages are automatically discovered from the connected TTS service. Select a voice from the dropdown to switch during a session.

## Using Local TTS NIM

When a local Magpie TTS NIM runs on GPU 0, add or edit the entry under the active platform block in `services.local.yaml`. Use Compose network names (`tts-service:50051`). The backend rewrites them to `localhost:50151` automatically when the app is run directly on the host instead of inside a container:

```yaml
workstation:
  tts:
    magpie-tts:
      name: "Magpie TTS (local)"
      server: "tts-service:50051"
      voice_id: "Magpie-Multilingual.EN-US.Aria"
      function_id: ""
```

## Changing the Default TTS Service

The first entry in the `tts:` block of the active catalog is the runtime default. Reorder entries in the example's `services.cloud.yaml` / `services.local.yaml` to change which TTS is selected on startup.

## Pronunciation Correction (IPA)

Override Magpie's default pronunciation for specific words using an International Phonetic Alphabet (IPA) dictionary. Set `TTS_IPA_FILE_PATH` in `.env` to a JSON or YAML file (relative paths resolve from the repo root):

```bash
TTS_IPA_FILE_PATH=config/ipa.json
```

Example dictionary:

```json
{
  "NVIDIA": "ˈɛnˌvɪdiə",
  "GreenForce": "ɡriːn fɔrs",
  "API": "eɪ piː aɪ"
}
```

The dictionary is loaded at session start and applied to every TTS request. Restart the server (or re-apply the active Compose profile) after changing the file path.

## TTS Text Filter

LLM output frequently contains special characters, Markdown formatting, or characters reserved by the Magpie TTS preprocessor for its own internal markup. When these characters reach the TTS inference engine unfiltered, synthesis fails or produces unexpected audio. A text filter sits between the LLM and the TTS service and removes these characters before synthesis.

The Magpie preprocessor reserves two character sequences:

- **`{` and `}`** — delimit ARPAbet phoneme tokens such as `{@AW1}` and `{@N}`.
- **`<tag>`** — SSML tags parsed by the TTS inference.

Both reserved sequences appear naturally in LLM output, particularly when the model responds with code examples, JSON, Markdown, or HTML snippets.

All filter classes live in `src/examples/shared/nemotron_speech_text_filter.py`.

### `NemotronSpeechTextFilter` *(default)*

Applies a single regex pass that strips `{`, `}`, and tag-opening `<` from the input text. All other characters — including comparison operators (`5 < 7`), currency signs, emoji, and non-Latin scripts (Arabic, Chinese, Devanagari, Korean, etc.) — are passed through unchanged.

Use this filter when the LLM produces plain prose or lightly formatted text with no Markdown.

```python
# src/examples/generic/pipeline.py
from examples.shared.nemotron_speech_text_filter import NemotronSpeechTextFilter

tts = NvidiaTTSService(
    ...
    text_filters=[NemotronSpeechTextFilter()],  # default
)
```

### `NemotronSpeechMarkdownTextFilter`

Extends Pipecat's `MarkdownTextFilter` with a second pass that applies the same reserved-character strip from `NemotronSpeechTextFilter`. Use this filter when the LLM streams Markdown-formatted responses.

```python
# src/examples/generic/pipeline.py
from examples.shared.nemotron_speech_text_filter import NemotronSpeechMarkdownTextFilter

tts = NvidiaTTSService(
    ...
    text_filters=[NemotronSpeechMarkdownTextFilter()],
)
```

All `MarkdownTextFilter` settings (`filter_code`, `filter_tables`) are inherited and work unchanged.
