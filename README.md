# wyoming-voice-bridge

Speech recognition and speech synthesis for [Hermes](https://github.com/NousResearch/hermes-agent) voice mode, on a [Wyoming](https://github.com/rhasspy/wyoming) server you run. Built on the Wyoming protocol.

Hermes installs the Python package named in `plugin.yaml` when you enable the plugin. This plugin registers an STT provider and a TTS provider, both named `wyoming`, and one tool, `wyoming_voice_status`.

**日本語の説明は[下にあります](#日本語)。**

## Set the servers

The host is a hostname or an IP address, up to 253 characters. Do not write a scheme, a user, a path, or brackets. An IPv6 address is written without brackets; the plugin adds them. The port is a decimal integer from 1 to 65535, with no leading zero. A public address is accepted. The connection is cleartext TCP, with no login. The plugin contacts only the host you set. There is no paid API.

```bash
export WYOMING_STT_HOST=127.0.0.1
export WYOMING_STT_PORT=10300
export WYOMING_TTS_HOST=127.0.0.1
export WYOMING_TTS_PORT=10200
```

Optional: `WYOMING_STT_MODEL`, `WYOMING_STT_LANGUAGE`, `WYOMING_TTS_VOICE`. Empty, or the word `default`, means the server's own default and no name is sent.

Hermes passes a language on every recognition call. This plugin sends one language, skipping empty and the word `default`, in this order: the language a pre_transcription hook set; `stt.wyoming.language`; `WYOMING_STT_LANGUAGE`; `stt.language` from the raw config; `HERMES_LOCAL_STT_LANGUAGE`. If none of those apply, no language is sent. The raw `stt.language` value is used as written. This plugin does not tell a line you wrote from a line Hermes wrote. The installer or `hermes doctor` copies `cli-config.yaml.example` into config.yaml, and that copy includes `stt.language: en`. To choose another language, set `WYOMING_STT_LANGUAGE` or `stt.wyoming.language`. This plugin does not call the pre_transcription hook again. It compares the language Hermes passed with the language Hermes would resolve from its own settings with no hook. When those two differ, the passed value is the hook language and is used first, including `en`. When they are the same string, it is not treated as a hook. The `en` Hermes fills in for `stt.language` when that key is absent, and the passed language is that same `en`, is not sent. If the config cannot be read, this plugin does not use `stt.wyoming.language` or `stt.language`, and it continues with the environment variables. That read is `hermes_cli.config.read_raw_config`, which is not in Hermes's public docs.

The server must list at least one installed model or voice. If `installed` is missing or null, this plugin treats that row as installed. `installed: false` is not a recognition candidate. The status tool returns every describe row, including rows that are not installed, and the `installed` field marks each row. `ready` is true only when at least one row is installed. A name is sent only when the installed list contains that exact spelling, including case. A language is sent only when it matches a listed code. If you name a model, only that model's list counts. If you do not name a model, the language is sent only when every installed model lists it, because describe does not say which model is the server default. If only some installed models list it, no audio is sent, and the reply asks you to name a model and try again. Case does not matter for a language code, and `_` and `-` are the same character. `en` does not match `en-US`. The plugin sends the spelling from the list. When no model is named, that spelling is the first installed model's. A refusal for an unknown name or language says that nothing was sent, that names are case-sensitive, and to copy the spelling with `wyoming_voice_status`. On the Docker Whisper image below, the list contains `en`, and `en-US` is refused before any audio is sent. Asking that server directly for an unknown model still returned a transcript; this plugin reads the list first and does not send the audio.

In Hermes config, set `stt.provider` and `tts.provider` to `wyoming`. A `type: command` provider of the same name wins over this plugin. The model row Hermes shows is one static line, not a live catalog. `list_models` does not connect. Speed, a recognition hint, and any host inside the call are ignored. The host comes only from the environment variables above.

`voice.voice_chat_mode: gpt-live` does not call STT or TTS providers. Voice-only model choice (`auxiliary.voice_chat`) is part of Hermes on current main and is absent on v0.21.4. This plugin does not add it, and it does not provide streaming transcription. This is not a satellite gateway.

## The status tool

`wyoming_voice_status` takes `which`: `stt`, `tts`, or `both`. `stt` or `tts` sends one describe. `both` opens two connections, one to each server, and the approval question states that count and that no audio and no text to speak are sent. It returns every model or voice from that describe, including rows that are not installed. The `installed` field marks each row. `ready` is true only when at least one row is installed. It does not send audio or text to speak. `both` is a success only when both sides succeed. A bad `which`, or a missing host, is refused before any approval and before any connection. More than 200 languages sets `languages_truncated` and returns the first 200. More than 50 speakers sets `speakers_truncated` and returns the first 50. There is no daily cap. On the Docker Piper image below, the `tts` reply was about 24KB because every voice is listed. The measured reply was 24381 bytes and 174 voices.

If one side lists more than 500 models or voices, the list is not trusted and nothing else is sent. Exactly 500 is allowed. The count is the raw describe rows, before the installed filter.

Hermes asks you to approve each call. Prefer once. Choosing always writes one line under `command_allowlist` in `config.yaml`. The next call does not reuse that line, because the rule key is a new uuid each call. Removing this plugin does not delete the line. Delete it by editing `command_allowlist`. If the question would not fit in one piece, the tool fails and does not ask. The tool is refused, and nothing is sent, when the session is cron, yolo, approvals off, `hermes -q`, another unattended platform, or the plugin-host process. If the approval helpers cannot be read, raise, or a function was renamed, the tool is refused.

The toolset name is `wyoming_voice`. It is on for every surface, including gateways. A guest who can reach the gateway can call it and approve it. Turn that toolset off per surface with `hermes tools`. The agent can call the tool. This README does not say the gateway is closed.

## Speech

Setting the provider to `wyoming` is the opt-in. After that, Hermes calls this plugin for audio and for text to speak, with no second question. That includes cron, webhooks, yolo, approvals off, `hermes -q`, another unattended platform, and the plugin-host process. This plugin does not create a cron job. A cron job you create still sends. Each utterance describes the server before audio or text is sent. Those waits add to each other, and to the 30 second ffmpeg wait when audio is converted. Nothing is retried.

`is_available` means the `wyoming` package imports and the host and port are an address this plugin accepts. An empty value, or a value this plugin refuses, counts as not set. It does not mean the server answered.

A WAV that is already 16 kHz, 16-bit, mono, with at least one frame, is sent as it is. Anything else is converted with `ffmpeg` as an argument list, with no shell, a 30 second limit, and `-t 656` before the input. That is just past the 20 MiB PCM cap, so a long compressed file cannot fill the disk. Output over 20 MiB is still not sent. `ffmpeg` is not a sandbox. A symlink is refused and nothing is sent. A format ffmpeg cannot convert is refused and nothing is sent. A file over 25 MB (25,000,000 bytes) is not converted and is not sent. At or under that size, the 16 kHz, 16-bit, mono PCM just before sending must be at most 20 MiB. That cap applies to a WAV that is already in that form and to ffmpeg output. Over the cap, the plugin returns a reason, deletes the temporary file when it made one, and sends no audio bytes. Text of exactly 4000 characters may reach describe. Text over 4000 characters is refused before connecting, and the reply says to shorten it and try again. Empty text, or text that is only whitespace, creates no file and does not connect.

The spoken file is written only after the server finishes, via a temporary file in the same directory, then replaced into place. If the requested path does not end in `.wav`, the plugin writes a `.wav` next to it and returns that path. If that `.wav` already exists, this plugin does not write over it. When the path Hermes asked for is that existing file, Hermes's speech tool deletes it while cleaning up the failed call. A neighboring `.wav` that already exists is left in place. If the temporary file already exists, this plugin does not replace it. The parent directory must exist. The write goes through Hermes's private write guard (`agent.file_safety`). If that guard cannot be loaded, raises, was renamed, denies the path, or would ask for approval, the file is not written and no approval question is sent. Hermes voice mode and the TTS tool may keep the WAV under the profile's `cache/audio`. This plugin writes nothing under `<HERMES_HOME>/plugin-data/wyoming-voice-bridge`. A partial PCM reply is not success. If synthesis returns more than 20 MiB of PCM, the file is not written.

An empty transcript is success: the server heard silence. It does not mean the server died. Logs record the event type and the payload size in bytes. They do not record the audio, the spoken words, or the text to speak. Speaker names and chat ids are not stored.

Connect waits 5 seconds. That limit is not left on the socket after the connection opens, so a transcript that arrives after more than 5 seconds of silence is still success. Describe waits 10 seconds. Speech synthesis waits 60. Speech recognition waits 120. On a timeout, including a describe timeout, the message says the server may already be working and that it was not sent again. Check the server before you try again. A line that is not JSON is not reported as a closed connection. JSON that is not an object is refused before the wyoming library reads it, with a different sentence. Nothing from that reply is kept, and nothing is retried.

## What was tested

On this machine, against Docker:

- `rhasspy/wyoming-whisper` with `--model tiny-int8 --language en`, port 10300
- `rhasspy/wyoming-piper` with `--voice en_US-lessac-medium`, port 10200

That is the set that was tried. It is not a claim that the plugin runs only in Docker.

A 16 kHz mono WAV from macOS `say` (the words were "hello bridge") was sent to Whisper. The transcript was 15 characters. It contained "bridge" and did not contain "hello". That is tiny-int8, not a dropped connection. The same image lists `en`. Asking for `en-US` was refused before any audio was sent. Piper returned 22050 Hz, 16-bit, mono PCM for the sentence "Hello." The file was not played. An unknown model and an unknown voice were refused after describe, before audio or speech was sent. Empty text to Piper produced no audio file. One Piper voice on that image lists more than 50 speakers. `wyoming_voice_status` with `which=tts` returned 24381 bytes and 174 voices.

Unit tests ran with `wyoming` 1.5.4. With the two local Hermes checkouts present, pytest reported 83 passed. From a copy of this repository that does not contain those checkouts, pytest reported 81 passed, 2 skipped. The two skipped tests call Hermes `transcribe_audio` and read the language on the Wyoming transcribe event. The Docker calls used `wyoming` 1.10.2. `plugin.yaml` allows `wyoming>=1.5.4,<2`.

`tests/` is in the repository and is not loaded by `register()`.

Not tested:

- A microphone, a speaker, a live Hermes voice session, streaming audio, or a real `gpt-live` session.
- A real cron turn, a real call from a gateway, and synthesis in a separate plugin-host process. The plugin host was checked only as the environment variable that blocks the status tool.
- Harm from opening a port beyond your LAN. The connection is cleartext. This plugin does not stop you from opening that port.
- Home Assistant satellites, or a real Wyoming device at home.
- The catalog pull request, which is not merged.
- Sending audio over the size cap to a real Whisper server to reproduce an out-of-memory stop. The refusal was seen on a fake server.
- Playing the Piper WAV on a speaker.

## License

MIT, Copyright (c) 2026 TakeshiTGAL. `NOTICE` quotes the copyright line from the `wyoming` package: Copyright (c) 2023 Michael Hansen. That package is MIT. See [wyoming on PyPI](https://pypi.org/project/wyoming/).

## 日本語

Hermes の音声モードから、自分で動かしている Wyoming の音声認識と音声合成を使うプラグインです。Wyoming プロトコルの上に作っています。音声と本文は、設定したホストとポートへ、ログイン無しの平文 TCP で送られます。公開アドレスも指定できます。有料 API は無く、日ごとの上限もありません。

状態を聞く道具 `wyoming_voice_status` は、ゲートウェイを含むすべての面で有効です。ゲートウェイに届く人は、この道具を呼び、承認もできます。止めるには `hermes tools` でツールセット `wyoming_voice` を面ごとに切ります。この道具は、cron、yolo、承認オフ、`hermes -q`、無人の面、プラグインホストでは動きません。音声そのものは、それらの場面と webhook でも送られます。このプラグインは cron を作りません。返答の一覧には未導入の行も入り、`installed` で区別します。`both` は接続が2本で、承認の文がその本数と、音声も読み上げも送らないことを言います。承認は once を選んでください。always は `config.yaml` の `command_allowlist` に1行残し、プラグインを消しても消えません。消すにはその行を編集します。

言語は、空と `default` という語を飛ばして、次の順で1つだけ送ります。順は、事前フックが置いた language、`stt.wyoming.language`、`WYOMING_STT_LANGUAGE`、生の config の `stt.language`、`HERMES_LOCAL_STT_LANGUAGE` です。どれも無ければ language は付けません。生の `stt.language` は、書いてある値をそのまま使います。誰が書いたかは見分けません。インストーラーや `hermes doctor` が `cli-config.yaml.example` を写すと、config.yaml に `stt.language: en` が入ることがあります。別の言語にするなら `WYOMING_STT_LANGUAGE` か `stt.wyoming.language` を置きます。このプラグインは pre_transcription フックを呼び直しません。Hermes が渡した language と、フック無しのときに Hermes 自身の設定から解決する値を比べ、違えばその渡した値をフックの language として先に使います。`en` でも同じです。同じ文字列のときはフックとは見なしません。キーが無く、渡した値もその解決値と同じときに本体が埋める `en` は送りません。設定が読めないときは、節も `stt.language` も使わず、環境変数へ進みます。生の config は、文書に無い `hermes_cli.config.read_raw_config` で読みます。言語は、サーバーの導入済み一覧にある符号と一致するときだけ送ります。大文字小文字は無視し、`_` と `-` は同じです。`en` は `en-US` にはなりません。モデル名が無いときは、導入済みのすべてのモデルがその符号を持つときだけ送り、綴りは先頭のモデルのものです。一部だけが持つときは、モデル名を指定してやり直す、と返し、音声は送りません。モデル名と声の名前は、大文字小文字を含めて完全一致です。拒否文は、何も送っていないことと、`wyoming_voice_status` で綴りを写すことを言います。

入力が 25 MB（25,000,000 バイト）を超える音声は、変換も送信もしません。それ以下でも、送る直前の PCM（16 kHz、16 bit、モノラル）が 20 MiB を超えたら送りません。既にその形式の WAV も、ffmpeg の出力も同じ上限です。超えたら理由を返し、作った一時ファイルを消し、サーバーへ音声を1バイトも送りません。ffmpeg は引数の配列で、シェルは使わず、30秒で止め、入力の前に `-t 656` を付けます。一時の PCM は 20 MiB の次の秒で止まります。20 MiB を超えた出力は送りません。ffmpeg は砂場ではありません。読み上げは 4000 字ちょうどまでで、4001 字は接続の前に拒否し、短くしてやり直す、と返します。空白だけの本文はファイルを作らず、接続もしません。片側のモデルまたは声が 500 件を超えたら、続きは送りません。合成で受け取った PCM が 20 MiB を超えたら、ファイルは書きません。

音声ファイルは Hermes が頼んだ場所に書き、音声モードはそれをプロファイルの `cache/audio` に残すことがあります。同じ `.wav` が既にあるときは、このプラグインは上書きしません。Hermes が頼んだパスがそのファイルであるときは、失敗した呼び出しの後始末で Hermes の読み上げ道具がそのファイルを消します。隣に既にある `.wav` はそのまま残します。一時ファイルが既にあるときは、このプラグインは置き換えません。`plugin-data` には何も書きません。状態の返答は未導入の行も含むため、Docker の Piper では 24381 バイト、174 声でした。JSON でない行は、接続が切れたとは別の文です。dict でない JSON は、ライブラリに渡す前に、また別の文で返します。ログに出すのはイベントの種別とバイト数だけで、音声も話した語も読み上げる文も出しません。

これは衛星ゲートウェイではありません。`gpt-live` はこのプラグインを使いません。`auxiliary.voice_chat` は現行 main の Hermes 本体にあり、このプラグインは足しません。v0.21.4 にはその設定がありません。ストリーミングの文字起こしはありません。同名の `type: command` 提供者がこのプラグインより先です。

試したのは Docker の `rhasspy/wyoming-whisper`（`--model tiny-int8 --language en`）と `rhasspy/wyoming-piper`（`--voice en_US-lessac-medium`）だけです。Docker でしか動かない、という意味ではありません。macOS の `say` が作った「hello bridge」の文字起こしは 15 文字で、bridge を含み hello を含みませんでした。Piper の「Hello.」は 22050 Hz、16 bit、モノラルでした。単体テストは wyoming 1.5.4 で、Hermes の checkout が2つあるときは 83 passed、checkout が無いコピーでは 81 passed, 2 skipped でした。Docker のクライアントは wyoming 1.10.2 でした。

確かめていないもの: マイク、スピーカー、Hermes のライブの音声セッション、ストリーミング、`gpt-live` の実セッション。cron の実ターン、ゲートウェイからの実際の呼び出し、プラグインホストの別プロセスでの合成。プラグインホストは、環境変数で状態の道具が拒否されることまでです。LAN の外へポートを開けたときの被害。平文であることは上に書きました。開けないことまでは強制しません。Home Assistant の衛星や、家にある実機の Wyoming。カタログの未マージの pull request。上限を超える音声を本物の Whisper へ送ってメモリ不足を再現すること。拒否は偽のサーバーで見ました。Piper の WAV をスピーカーで再生すること。
