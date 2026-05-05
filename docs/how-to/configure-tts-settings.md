# Configure TTS Settings

The Text-to-Speech (TTS) system supports multiple voices and languages using the [NVIDIA Magpie TTS model](https://build.nvidia.com/nvidia/magpie-tts-multilingual/modelcard). TTS services are defined in [`services.cloud.yaml`](../../services.cloud.yaml) or [`services.local.yaml`](../../services.local.yaml), and voices can be changed from the UI.

## Default Configuration

The default cloud TTS service is defined in `services.cloud.yaml`:

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

When a local Magpie TTS NIM runs on GPU 0, add or edit the entry under the active platform block in `services.local.yaml`. Use Compose network names (`tts-service:50051`); the backend rewrites them to `localhost:50151` automatically when the app is run directly on the host instead of inside a container:

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

Edit the `.env` file only if you want to override the default TTS key. Any override must match a key in the active catalog for your deployment; otherwise the first built-in TTS entry is used:

```bash
DEFAULT_TTS=magpie-tts
```

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

The text filter (`NemotronSpeechTextFilter`) strips markdown formatting, special characters, and excess whitespace before sending text to the TTS model. This prevents synthesis failures caused by unsupported characters.

Controlled via the `ENABLE_TTS_TEXT_FILTER` environment variable in `.env`:

```bash
ENABLE_TTS_TEXT_FILTER=true
```

The filter is automatically disabled when a multilingual prompt is selected, because multilingual responses are handled by a dedicated processor that extracts the spoken `Text:` block and switches TTS language and voice dynamically. For setup details, see [Enable Multilingual Voice Agent](./enable-multilingual.md).
