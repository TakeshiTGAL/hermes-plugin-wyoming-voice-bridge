# Changelog

## 0.1.6

In the `wyoming-speech` skill, the line for listing speech voices («声の一覧») now calls `wyoming_voice_status` with `{"which": "tts"}` and searches for "Wyoming speech synthesis". It used to point at speech recognition, which lists models, not voices.

## 0.1.5

`wyoming_voice_status` returns block on cron, `hermes -q`, webhook, msgraph_webhook, and api_server, even after always. The hook does this before Hermes reads the allowlist, and the handler does not open a describe. yolo and approvals off still skip the prompt. Hermes 0.21.4 does not list the `wyoming-speech` skill. The v0.21.5 canary's prompt builder adds plugin skills to the index, and Hermes 0.22.2 lists the line. The 0.1.1 note that 0.21.5 does not list the skill was wrong for that canary. With the v0.22.2 checkout on `HERMES_SRC` and `HERMES_AGENT_SRC`, that interpreter, and wyoming 1.5.4, pytest reported 122 passed and 0 skipped.

## 0.1.4

The wyoming file-tree table lists the official 1.5.4 wheel. A matching install is imported, `wyoming_voice_status` returns one approve line, and speech is sent to the servers you set. A missing package or a different tree is not imported, and the reply names the install step. ffmpeg is still not started, because this build lists no ffmpeg digest. Speech files are refused at the home credential directories and the profile token directories without importing Hermes's write-guard module. `requires_hermes` is `>=0.21.4`, which already accepts the public approve line. With the v0.22.2 checkout on `HERMES_SRC` and `HERMES_AGENT_SRC`, that interpreter, and wyoming 1.5.4, pytest reported 114 passed and 0 skipped.

## 0.1.3

The manifest lists the pre_tool_call hook that wyoming_voice_status already registers. Hermes shows that one approve line. Speech providers do not use the hook. Session and always cover only the same which and the same host:port list. `python_dependencies` pins `wyoming==1.5.4`. The installed package is imported only when its tree sha256 is in this build's table. This build's table is empty, so the package is not imported and nothing is sent. ffmpeg runs only when its sha256 is in the table for this operating system and CPU. This build's ffmpeg table is empty, so an unlisted binary is not started. A symlink at the ffmpeg path is refused before it is resolved. Recognition language is only the plugin setting `stt_language`, read with `ctx.get_config`. Speech file writes still use the write guard.

## 0.1.2

The README opens with the five steps of the first request: install, `WYOMING_STT_HOST`, `WYOMING_STT_PORT`, the server already running, and `wyoming_voice_status` with which stt. That call asks once and sends no audio. Switching `stt.provider` is a later step. The skill turns a Japanese request into an English tool_search query. A missing recognition host names `WYOMING_STT_HOST`, `WYOMING_STT_PORT`, and which stt. The describe approval is unchanged.

The first call uses which stt and asks once. 日本語: 最初は which stt。承認は1回。ホストが無い返事は、設定名と which stt を英語の後に日本語で書く。

## 0.1.1

`WYOMING_STT_HOST`, `WYOMING_STT_PORT`, `WYOMING_TTS_HOST`, `WYOMING_TTS_PORT`, `WYOMING_STT_MODEL`, `WYOMING_STT_LANGUAGE`, and `WYOMING_TTS_VOICE` were read from `os.environ`. One Hermes process can serve more than one profile, so that read could send one profile's audio to another profile's server. Each call now reads them with `agent.secret_scope.get_secret`. With a single profile the environment is used as before. Under multiplexing with no profile scope the read is refused and nothing is sent; `is_available` then reports not configured instead of raising.

Adds the `wyoming-speech` skill. It tells the model to find `wyoming_voice_status` with tool_search before web_search. Hermes 0.21.4 does not list it. The v0.21.5 canary's prompt builder adds plugin skills to the index, and Hermes 0.22.2 lists the line while the plugin is enabled, including a surface where the toolset was turned off with hermes tools. It does not set requires_toolsets, so it stays listed when Tool Search is left at its default, which hides this plugin's tools. The earlier wording that 0.21.5 does not list the skill does not match that canary. On Hermes 0.21.4 it loads only by its full name.

which written in fullwidth letters is accepted; any letter case was already accepted. Extra arguments, which used to be ignored, are refused. A missing which and a value such as 10.0 are refused as before. Each refusal gives a fix and an example, does not copy the caller's value, and adds `ok: false` and `error_type`.

The tool description now opens with Wyoming speech server and what the call does. Under Tool Search's default, the first sentence is the part of the description the model sees before it searches. It also says that the status tool does not transcribe or speak; the stt and tts providers do.

Tests that speak the Wyoming protocol skip when the declared `wyoming` library is not installed.

The README describes the per-profile reading of the `WYOMING_*` settings, the skill, where it is listed, and how to remove it.
