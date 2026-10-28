---
name: wyoming-speech
description: "Wyoming speech server models and voices. Before web_search, use tool_search to find wyoming_voice_status and tool_call to run it."
---

For this kind of request, use tool_search to find this plugin's tools before web_search, then call them with tool_call. Write tool_search queries in English (for example: "Wyoming speech").

First call: `wyoming_voice_status` with which stt. Hermes asks once. The call sends no audio and no text to speak. Do not pass a model name on that first call. If the reply is not ok, do what the error says once. Answer in the language the user used.

which is stt, tts, or both. Listing models does not require stt.provider or tts.provider to be wyoming. Set those providers only when the user wants voice mode.

Japanese requests use the same tool. Search in English, then answer in Japanese:

- List the speech voices. 「声の一覧」 → tool_search "Wyoming speech synthesis" → `wyoming_voice_status` {"which": "tts"} <!-- ja-alias -->
- List the speech models. 「モデルの一覧」 → tool_search "Wyoming speech" → `wyoming_voice_status` {"which": "stt"} <!-- ja-alias -->
- Can it transcribe speech. 「文字起こしできる」 → tool_search "Wyoming speech recognition" → `wyoming_voice_status` {"which": "stt"} <!-- ja-alias -->
- Voices for reading aloud. 「読み上げの声」 → tool_search "Wyoming speech synthesis" → `wyoming_voice_status` {"which": "tts"} <!-- ja-alias -->
- Is the server up. 「サーバは生きてる」 → tool_search "Wyoming speech" → `wyoming_voice_status` {"which": "stt"} <!-- ja-alias -->
