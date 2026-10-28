# wyoming-voice-bridge

Speech recognition and speech synthesis for [Hermes](https://github.com/NousResearch/hermes-agent) voice mode, on a [Wyoming](https://github.com/rhasspy/wyoming) server you run. Built on the Wyoming protocol. The installed package is imported only when its file tree is the listed wyoming 1.5.4 wheel. A different tree is not imported and nothing is sent.

Hermes installs the Python package named in `plugin.yaml` when you enable the plugin. This plugin registers an STT provider and a TTS provider, both named `wyoming`, and one tool, `wyoming_voice_status`.

**The Japanese notes are below. 日本語の説明は[下にあります](#日本語)。**

## First request

You can list models before you switch the voice provider. Speech itself is a later step. Install the catalog name so Hermes uses the pinned commit. The owner/repo form skips that pin.

1. `hermes plugins install wyoming-voice-bridge --enable`
2. Set `WYOMING_STT_HOST` to the hostname, such as `127.0.0.1`. Do not write a scheme.
3. Set `WYOMING_STT_PORT`, such as `10300`.
4. The Wyoming server is already running.
5. Ask "which speech models are installed". The model calls `wyoming_voice_status` with which stt. When the installed tree is the listed 1.5.4 wheel, Hermes asks once, and no audio is sent. If the package is missing or the tree does not match, the reply names the install step and opens no connection. Hermes may also say the STT plugin is not available and mention credentials or dependencies. That sentence is not an API key. Install the declared wyoming 1.5.4 with the Python that runs Hermes, then set the host. Set `stt.provider` and `tts.provider` to `wyoming` only when you want voice mode.

The first call is wyoming_voice_status with which set to stt. 日本語: 最初は which を stt にした wyoming_voice_status。承認は1回。音声にする provider の切り替えは後でよい。

## Set the servers

The host is a hostname or an IP address, up to 253 characters. Do not write a scheme, a user, a path, or brackets. An IPv6 address is written without brackets. The plugin adds them. The port is a decimal integer from 1 to 65535, with no leading zero. A public address is accepted. The connection is cleartext TCP, with no login. The plugin contacts only the host you set. There is no paid API.

```bash
export WYOMING_STT_HOST=127.0.0.1
export WYOMING_STT_PORT=10300
export WYOMING_TTS_HOST=127.0.0.1
export WYOMING_TTS_PORT=10200
```

Optional: `WYOMING_STT_MODEL` and `WYOMING_TTS_VOICE`. Empty, or the word `default`, means the server's own default and no name is sent. Recognition language is the plugin setting `stt_language` (`plugins.entries.wyoming-voice-bridge.settings`). Empty, or the word `default`, sends no language.

These six settings are read on each call for the active Hermes profile, through the Hermes secret scope. On a gateway that serves several profiles from one process, each profile's audio and text go only to the servers set for that profile, and a call that has no profile scope there connects nowhere. With a single profile, the values in the environment are used as before. This plugin does not read the process environment for a recognition language.

Hermes passes a language on every recognition call. This plugin does not send that value. It sends only `stt_language` from its own plugin setting, skipping empty and the word `default`. A pre_transcription hook, `stt.language`, `stt.wyoming.language`, and the process environment are not read. If the setting is missing or the read fails, no language is sent.

The server must list at least one installed model or voice. If `installed` is missing or null, this plugin treats that row as installed. `installed: false` is not a recognition candidate. The status tool returns every describe row, including rows that are not installed, and the `installed` field marks each row. `ready` is true only when at least one row is installed. A name is sent only when the installed list contains that exact spelling, including case. A language is sent only when it matches a listed code. If you name a model, only that model's list counts. If you do not name a model, the language is sent only when every installed model lists it, because describe does not say which model is the server default. If only some installed models list it, no audio is sent, and the reply asks you to name a model and try again. Case does not matter for a language code, and `_` and `-` are the same character. `en` does not match `en-US`. The plugin sends the spelling from the list. When no model is named, that spelling is the first installed model's. A refusal for an unknown name or language says that nothing was sent, that names are case-sensitive, and to copy the spelling with `wyoming_voice_status`. On the Docker Whisper image below, the list contains `en`, and `en-US` is refused before any audio is sent. Asking that server directly for an unknown model still returned a transcript. This plugin reads the list first and does not send the audio.

In Hermes config, set `stt.provider` and `tts.provider` to `wyoming`. A `type: command` provider of the same name wins over this plugin. The model row Hermes shows is one static line, not a live catalog. `list_models` does not connect. Speed, a recognition hint, and any host inside the call are ignored. The host comes only from the settings above.

`voice.voice_chat_mode: gpt-live` does not call STT or TTS providers. Voice-only model choice (`auxiliary.voice_chat`) is part of Hermes on current main and is absent on v0.21.4. This plugin does not add it, and it does not provide streaming transcription. This is not a satellite gateway.

## The status tool

`wyoming_voice_status` takes `which`: `stt`, `tts`, or `both`. `stt` or `tts` sends one describe. `both` opens two connections, one to each server, and the approval question states that count and that no audio and no text to speak are sent. It returns every model or voice from that describe, including rows that are not installed. The `installed` field marks each row. `ready` is true only when at least one row is installed. It does not send audio or text to speak. `both` is a success only when both sides succeed. A bad `which`, or a missing host, is refused before any approval and before any connection. More than 200 languages sets `languages_truncated` and returns the first 200. More than 50 speakers sets `speakers_truncated` and returns the first 50. There is no daily cap. On the Docker Piper image below, the `tts` reply was about 24KB because every voice is listed. The measured reply was 24381 bytes and 174 voices.

If one side lists more than 500 models or voices, the list is not trusted and nothing else is sent. Exactly 500 is allowed. The count is the raw describe rows, before the installed filter.

Hermes asks you to approve each new plan. The `pre_tool_call` hook returns `{"action": "approve", "message": <one line>}` naming how many describes and which `host:port` values, and that no audio and no text to speak are sent. Hermes then runs the same human gate as a dangerous shell command (`hermes_cli/plugins.py` `_resolve_block_from_details`, line 2069 in v0.22.2, calls `tools/approval.py` `request_tool_approval`). Prefer once. Choosing always writes one `plugin_rule:wyoming_voice_status:` line under `command_allowlist` in `config.yaml`. When a person is present, later calls with that same `which` and the same host:port list skip the question. A different `which` or a different server asks again. cron, `hermes -q`, webhook, msgraph_webhook, and api_server do not send a describe, even after that line is stored. The hook returns block on those turns, before Hermes reads the allowlist (`hermes_cli/plugins.py` `_resolve_block_from_details` returns the block message at line 2057 in v0.22.2, and `request_tool_approval` is the next step). When the pre_tool_call dispatcher returns BLOCKED, Hermes does not call the handler (`model_tools.py` `handle_function_call` returns at line 944 in v0.22.2 and line 926 on origin-main, before `_execute_tool`, and `agent/tool_executor.py` `_dispatch_authorized_once` returns at line 741 in v0.22.2 and on origin-main, before `execute`). Removing this plugin does not delete the line. Delete it by editing `command_allowlist`. If the question would not fit in one piece, the hook blocks and nothing is sent. A bad `which`, a missing host, or a missing `wyoming` library returns nothing from the hook, and the handler opens no connection. After a yes, the handler sends the describe only when that same call, session, and task still name the same servers. If the target changed, nothing is sent.

Hermes decides the modes. This plugin does not read them:

- yolo (`--yolo` / `/yolo`) and `approvals.mode: off` skip the prompt and treat the call as approved (`tools/approval.py` `_run_approval_gate`, the check at line 967 in v0.22.2). This plugin does not add a second refusal for those modes. A person does not have to be present for that skip.
- cron, `hermes -q`, webhook, msgraph_webhook, and api_server are blocked by this plugin even after always. Hermes's own defaults for `approvals.cron_mode`, `single_query_mode`, and `unattended_mode` are deny (`hermes_cli/config_defaults.py` lines 1681-1683 in v0.22.2). Those defaults do not stop a stored always line. The hook's block does. Any other non-interactive context with nobody to answer fails closed (`request_tool_approval` passes `fail_closed_when_no_human=True`, line 1120 in v0.22.2).

`HERMES_PLUGIN_HOST_PROCESS=1` still refuses the status tool, because that process is not the parent's approval check. Speech providers do not use this gate. They still send audio and text after the provider is selected, including on cron and webhooks. Requires Hermes `>=0.21.4`. That release already accepts `{"action": "approve"}` and `rule_key` from `pre_tool_call`. This plugin does not call the cron identity API that arrived in 0.21.6. It reads `HERMES_CRON_SESSION`, `HERMES_SINGLE_QUERY_SESSION`, and `HERMES_SESSION_PLATFORM`, taking a ContextVar when that var holds a string, and the process environment otherwise.

An empty `HERMES_HOME` scan with Hermes v0.22.2 and with origin-main is `Verdict: SAFE`, 28 findings, `Decision: ALLOWED — Allowed (community source, safe verdict)`. The findings are the ffmpeg `subprocess` call, the host names in the changelog, and addresses and subprocesses in the tests. They stay, because the converter and the tests need them.

The toolset name is `wyoming_voice`. It is on for every surface, including gateways. A guest who can reach the gateway can call it and approve it. Turn that toolset off per surface with `hermes tools`. The agent can call the tool. This README does not say the gateway is closed.

## Speech

Setting the provider to `wyoming` is the opt-in. This build imports the installed `wyoming` package only when the sha256 of its file tree is the one value listed in this repository. That value is the tree of the official `wyoming-1.5.4-py3-none-any.whl`. The PyPI JSON file sha256 of that wheel is `cb044b8d9e0f625907efb1bde32cc38eaef67fdd495075f6127d98d3b12c0683`. The tree sha256, skipping `__pycache__` and `.pyc`, is `d3fd5dcc24ad89a5145de41dbd1e7ac2b6597d67cc610fd19c32368d1132e8c6`. The extracted wheel, pip 21.2.4, and uv on Python 3.12.14 all produced that tree value. A symlink in that tree is not hashed and is not imported. A missing package or a different tree is not imported, `is_available` is false, and no audio or text is sent. The reply then says to install wyoming 1.5.4 and call `wyoming_voice_status` again. `python_dependencies` is the version line `wyoming==1.5.4`. A hash inside that line is not a valid requirement, so the pin is the table, checked before import, including a package that is already installed. When the installed tree matches, Hermes calls this plugin for audio and for text to speak, with no second question. That includes cron, webhooks, yolo, approvals off, `hermes -q`, another unattended platform, and the plugin-host process. This plugin does not create a cron job. Each utterance describes the server before audio or text is sent. Those waits add to each other, and to the 30 second ffmpeg wait when audio is converted. Nothing is retried.

`is_available` means the installed `wyoming` tree's sha256 is in this build's table and the host and port are an address this plugin accepts. An empty value, or a value this plugin refuses, counts as not set. A package that merely imports is not enough. It does not mean the server answered.

After the wyoming table lists the installed tree, a WAV that is already 16 kHz, 16-bit, mono, with at least one frame, is sent as it is. This build lists that tree, so a matching install sends the file. Anything else is converted only when the sha256 of the ffmpeg on PATH is listed for this operating system and CPU. This build's ffmpeg table is empty, so that binary is not started and the audio is not sent. When a digest is listed, conversion is an argument list, with no shell, a 30 second limit, and `-t 656` before the input. That is just past the 20 MiB PCM cap, so a long compressed file cannot fill the disk. Output over 20 MiB is still not sent. `ffmpeg` is not a sandbox. A symlink at the path `shutil.which` returns is refused before that path is resolved, and nothing is sent. A format ffmpeg cannot convert is refused and nothing is sent. A file over 25 MB (25,000,000 bytes) is not converted and is not sent. At or under that size, the 16 kHz, 16-bit, mono PCM just before sending must be at most 20 MiB. That cap applies to a WAV that is already in that form and to ffmpeg output. Over the cap, the plugin returns a reason, deletes the temporary file when it made one, and sends no audio bytes. Text of exactly 4000 characters may reach describe. Text over 4000 characters is refused before connecting, and the reply says to shorten it and try again. Empty text, or text that is only whitespace, creates no file and does not connect.

The spoken file is written only after the server finishes, via a temporary file in the same directory, then replaced into place. If the requested path does not end in `.wav`, the plugin writes a `.wav` next to it and returns that path. If that `.wav` already exists, this plugin does not write over it. When the path Hermes asked for is that existing file, Hermes's speech tool deletes it while cleaning up the failed call. A neighboring `.wav` that already exists is left in place. If the temporary file already exists, this plugin does not replace it. The parent directory must exist. The write does not import Hermes's write-guard module. It refuses a symlink, an existing file, a path under the home credential directories this plugin names (`.ssh`, `.aws`, `.gnupg`, `.kube`, and `.netrc`), a path under the profile's `sessions`, `mcp-tokens`, `pairing`, `vault`, or `browser-profile`, and a path outside `HERMES_WRITE_SAFE_ROOT` when that variable is set. If the check fails, the file is not written and no approval question is sent. A Hermes update of its own write guard does not extend this list. Hermes voice mode and the TTS tool may keep the WAV under the profile's `cache/audio`. This plugin writes nothing under `<HERMES_HOME>/plugin-data/wyoming-voice-bridge`. A partial PCM reply is not success. If synthesis returns more than 20 MiB of PCM, the file is not written.

An empty transcript is success: the server heard silence. It does not mean the server died. Logs record the event type and the payload size in bytes. They do not record the audio, the spoken words, or the text to speak. Speaker names and chat ids are not stored.

Connect waits 5 seconds. That limit is not left on the socket after the connection opens, so a transcript that arrives after more than 5 seconds of silence is still success. Describe waits 10 seconds. Speech synthesis waits 60. Speech recognition waits 120. On a timeout, including a describe timeout, the message says the server may already be working and that it was not sent again. Check the server before you try again. A line that is not JSON is not reported as a closed connection. JSON that is not an object is refused before the wyoming library reads it, with a different sentence. Nothing from that reply is kept, and nothing is retried.

## What was tested

On this machine, against Docker:

- `rhasspy/wyoming-whisper` with `--model tiny-int8 --language en`, port 10300
- `rhasspy/wyoming-piper` with `--voice en_US-lessac-medium`, port 10200

That is the set that was tried. It is not a claim that the plugin runs only in Docker.

A 16 kHz mono WAV from macOS `say` (the words were "hello bridge") was sent to Whisper. The transcript was 15 characters. It contained "bridge" and did not contain "hello". That is tiny-int8, not a dropped connection. The same image lists `en`. Asking for `en-US` was refused before any audio was sent. Piper returned 22050 Hz, 16-bit, mono PCM for the sentence "Hello." The file was not played. An unknown model and an unknown voice were refused after describe, before audio or speech was sent. Empty text to Piper produced no audio file. One Piper voice on that image lists more than 50 speakers. `wyoming_voice_status` with `which=tts` returned 24381 bytes and 174 voices.

On this machine, pytest used the Hermes v0.22.2 checkout as `HERMES_SRC` and `HERMES_AGENT_SRC`, that checkout's interpreter as `HERMES_AGENT_PYTHON`, and wyoming 1.5.4. It reported 122 passed and 0 skipped. The Docker calls below used wyoming 1.10.2, which this build does not import. `plugin.yaml` lists `wyoming==1.5.4`. Protocol tests run when that tree is the one this build lists.

`tests/` is in the repository and is not loaded by `register()`.

Not tested:

- A microphone, a speaker, a live Hermes voice session, streaming audio, or a real `gpt-live` session.
- A real cron turn, a real call from a gateway, and synthesis in a separate plugin-host process. The plugin host was checked only as the environment variable that blocks the status tool.
- Harm from opening a port beyond your LAN. The connection is cleartext. This plugin does not stop you from opening that port.
- Home Assistant satellites, or a real Wyoming device at home.
- The catalog pull request, which is not merged.
- Sending audio over the size cap to a real Whisper server to reproduce an out-of-memory stop. The refusal was seen on a fake server.
- Playing the Piper WAV on a speaker.

## Skill

The plugin registers one skill, `wyoming-speech`. It tells the model to look up `wyoming_voice_status` with tool_search, in English, before it tries web_search. The skill runs nothing, sends nothing, and approves nothing by itself. The status tool asks on a new plan. The same plan skips the question only when a person is present and always was already chosen. Unattended turns do not send a describe. It does not change which provider Hermes uses for speech.

This plugin requires Hermes `>=0.21.4`. Hermes 0.21.4 does not add this skill to the skills index. The v0.21.5 canary's prompt builder does, and Hermes 0.22.2 lists one line in every session that loads the plugin. That includes a surface where the toolset was turned off with `hermes tools`. The line stays there, and the call is simply unavailable. There is no separate user list for the skill. Every session that loads the plugin on a Hermes version that shows plugin skills can read it. `hermes plugins disable wyoming-voice-bridge` removes the skill, the status tool, and the speech providers together.

## License

MIT, Copyright (c) 2026 TakeshiTGAL. `NOTICE` quotes the copyright line from the `wyoming` package: Copyright (c) 2023 Michael Hansen. That package is MIT. See [wyoming on PyPI](https://pypi.org/project/wyoming/).

## 日本語

Hermes の音声モードから、自分で動かしている Wyoming の音声認識と音声合成を使うプラグインです。Wyoming プロトコルの上に作っています。音声と本文は、設定したホストとポートへ、ログイン無しの平文 TCP で送られます。公開アドレスも指定できます。有料 API は無く、日ごとの上限もありません。

The six `WYOMING_*` settings are two hosts, two ports, the model, and the voice. Language is not one of them. 日本語: `WYOMING_*` の6つの設定は、呼び出しのたびに Hermes のシークレットスコープから、今のプロファイルの値を読みます。1つのゲートウェイが複数のプロファイルを持つとき、音声と読み上げる文は、そのプロファイルに設定したサーバーへだけ行きます。プロファイルが1つなら、これまでどおり環境変数の値を使います。

This plugin requires Hermes 0.21.4 or newer. 日本語: Hermes 0.21.4 では skill `wyoming-speech` は skill 一覧に出ません。v0.21.5 の canary の prompt builder はプラグインの skill を一覧に足します。Hermes 0.22.2 では、プラグインが有効なあいだ全セッションの一覧に1行出ます。`hermes tools` で道具を切った面でも残ります。skill は何も送らず、何も承認しません。`hermes plugins disable wyoming-voice-bridge` で、skill・道具・音声の提供者がまとめて外れます。公式の wyoming 1.5.4 の木だけを import します。違う木は送らず、入れ直しの一文を返します。

状態を聞く道具 `wyoming_voice_status` は、ゲートウェイを含むすべての面で有効です。ゲートウェイに届く人は、この道具を呼び、承認もできます。止めるには `hermes tools` でツールセット `wyoming_voice` を面ごとに切ります。承認は `pre_tool_call` が返す1行で、Hermes が人に尋ねます。yolo と承認オフは、人がいなくても尋ねずに通します（`tools/approval.py` 967行、v0.22.2）。cron、`hermes -q`、webhook、msgraph_webhook、api_server は、always の行が残っていても describe を送りません。Hermes の既定 deny（`hermes_cli/config_defaults.py` 1681-1683行）は、保存された always より後なので、そこでは止まりません。`HERMES_PLUGIN_HOST_PROCESS=1` のときは、この道具だけ動きません。音声そのものは、それらの場面と webhook でも送られます。このプラグインは cron を作りません。返答の一覧には未導入の行も入り、`installed` で区別します。`both` は接続が2本で、承認の文がその本数と、音声も読み上げも送らないことを言います。承認は once を選んでください。人がいるとき、always は同じ which と同じ host:port の一覧だけを次から省きます。違う計画は再び聞きます。`config.yaml` の `command_allowlist` に1行残り、プラグインを消しても消えません。消すにはその行を編集します。

The only recognition language is the plugin setting `stt_language`. Empty, or the word `default`, sends no language. The language Hermes passes, `stt.language`, and the process environment are not read. 日本語: 認識の言語はプラグイン設定 `stt_language` だけです。空と `default` という語は送りません。Hermes が渡した language、`stt.language`、プロセスの環境変数は読みません。言語は、サーバーの導入済み一覧にある符号と一致するときだけ送ります。大文字小文字は無視し、`_` と `-` は同じです。`en` は `en-US` にはなりません。モデル名が無いときは、導入済みのすべてのモデルがその符号を持つときだけ送り、綴りは先頭のモデルのものです。一部だけが持つときは、モデル名を指定してやり直す、と返し、音声は送りません。モデル名と声の名前は、大文字小文字を含めて完全一致です。拒否文は、何も送っていないことと、`wyoming_voice_status` で綴りを写すことを言います。

ffmpeg runs only when its sha256 is listed for this operating system and CPU. This build lists none, so audio that is not already 16 kHz, 16-bit, mono WAV is not converted and is not sent. 日本語: 入力が 25 MB（25,000,000 バイト）を超える音声は、変換も送信もしません。それ以下でも、送る直前の PCM（16 kHz、16 bit、モノラル）が 20 MiB を超えたら送りません。既にその形式の WAV も、ffmpeg の出力も同じ上限です。超えたら理由を返し、作った一時ファイルを消し、サーバーへ音声を1バイトも送りません。ffmpeg は引数の配列で、シェルは使わず、30秒で止め、入力の前に `-t 656` を付けます。一時の PCM は 20 MiB の次の秒で止まります。20 MiB を超えた出力は送りません。ffmpeg は砂場ではありません。読み上げは 4000 字ちょうどまでで、4001 字は接続の前に拒否し、短くしてやり直す、と返します。空白だけの本文はファイルを作らず、接続もしません。片側のモデルまたは声が 500 件を超えたら、続きは送りません。合成で受け取った PCM が 20 MiB を超えたら、ファイルは書きません。

音声ファイルは Hermes が頼んだ場所に書き、音声モードはそれをプロファイルの `cache/audio` に残すことがあります。同じ `.wav` が既にあるときは、このプラグインは上書きしません。Hermes が頼んだパスがそのファイルであるときは、失敗した呼び出しの後始末で Hermes の読み上げ道具がそのファイルを消します。隣に既にある `.wav` はそのまま残します。一時ファイルが既にあるときは、このプラグインは置き換えません。`plugin-data` には何も書きません。状態の返答は未導入の行も含むため、Docker の Piper では 24381 バイト、174 声でした。JSON でない行は、接続が切れたとは別の文です。dict でない JSON は、ライブラリに渡す前に、また別の文で返します。ログに出すのはイベントの種別とバイト数だけで、音声も話した語も読み上げる文も出しません。

これは衛星ゲートウェイではありません。`gpt-live` はこのプラグインを使いません。`auxiliary.voice_chat` は現行 main の Hermes 本体にあり、このプラグインは足しません。v0.21.4 にはその設定がありません。ストリーミングの文字起こしはありません。同名の `type: command` 提供者がこのプラグインより先です。

試したのは Docker の `rhasspy/wyoming-whisper`（`--model tiny-int8 --language en`）と `rhasspy/wyoming-piper`（`--voice en_US-lessac-medium`）だけです。Docker でしか動かない、という意味ではありません。macOS の `say` が作った「hello bridge」の文字起こしは 15 文字で、bridge を含み hello を含みませんでした。Piper の「Hello.」は 22050 Hz、16 bit、モノラルでした。その時のクライアントは wyoming 1.10.2 で、このビルドは import しません。このコミットの pytest の件数は英語の What was tested に1つだけ書いてあります。

確かめていないもの: マイク、スピーカー、Hermes のライブの音声セッション、ストリーミング、`gpt-live` の実セッション。cron の実ターン、ゲートウェイからの実際の呼び出し、プラグインホストの別プロセスでの合成。プラグインホストは、環境変数で状態の道具が拒否されることまでです。LAN の外へポートを開けたときの被害。平文であることは上に書きました。開けないことまでは強制しません。Home Assistant の衛星や、家にある実機の Wyoming。カタログの未マージの pull request。上限を超える音声を本物の Whisper へ送ってメモリ不足を再現すること。拒否は偽のサーバーで見ました。Piper の WAV をスピーカーで再生すること。
