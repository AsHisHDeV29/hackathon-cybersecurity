# NETRA — Message Intelligence

A local OSINT prototype that screens submitted messages for potential illegal-trade signals and routes flagged or unclear results to a password-protected authority review portal.

**Llama 3.2 3B** runs locally through Ollama to assess English, Hindi, and Hinglish. Other local languages can go directly to human review. Assessments are investigative leads; they do not establish wrongdoing.

## Features

- Submit text with optional source context and a language hint.
- Screen suspected drug or weapons trade, bank-account/card/SIM sale or rental, and forged-document offers.
- View explanations, exact evidence snippets, and extracted phone numbers, handles, UPI IDs, and links.
- Automatically queue potential flags, ambiguous messages, unsupported languages, and model failures.
- Search and filter the authority portal, including a dedicated **Language review** view.
- Save officer notes, translations or interpretations, and review decisions.
- Keep original messages and review decisions in SQLite across restarts.
- Try synthetic samples for routine conversation, potential trade, ambiguity, Hinglish, and a regional language.

## Requirements

- **Python 3.10+**. The application uses the standard library; no pip packages are required.
- **Ollama** and the `llama3.2:3b` model for AI screening.
- Internet access for initial downloads. The model download is approximately **2 GB**.
- Sufficient memory for local inference; a supported GPU can accelerate it.
- Node.js is optional, used only for the JavaScript syntax check.

## Quick start

Clone your repository and enter its directory, replacing the placeholders:

```sh
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

### 1. Install Ollama

Install Ollama from its [official download page](https://ollama.com/download). The launcher supports an existing installation on your `PATH`.

Alternatively, on **x86-64 Linux**, install it inside the project. This requires curl, tar, and Zstandard support:

```sh
mkdir -p .runtime/ollama
curl -fL https://ollama.com/download/ollama-linux-amd64.tar.zst -o .runtime/ollama-linux-amd64.tar.zst
tar --zstd -xf .runtime/ollama-linux-amd64.tar.zst -C .runtime/ollama
```

Runtime files and model weights are excluded from Git. Anyone cloning this project must install them separately.

### 2. Start the application and model

```sh
python3 run.py
```

The launcher reuses a running local Ollama service or starts one, downloads the model if missing, and starts NETRA at **http://127.0.0.1:8000**.

Open **Authority portal** and use the password printed in your current terminal session. A new password is generated on each start unless you provide one (POSIX shell example):

```sh
AUTHORITY_PASSWORD='replace-with-your-own-password' python3 run.py
```

Press **Ctrl+C** in that terminal to stop the app and the Ollama service it started. An Ollama service that was already running independently is left running. Saved messages and downloaded models remain on disk.

### If you manage Ollama separately

With the Ollama service already running:

```sh
ollama pull llama3.2:3b
python3 -m backend.server
```

This starts only the application. If the configured model is unavailable, submitted messages enter manual review.

### Without a model

For an explicit rule-only demonstration:

```sh
NETRA_ENGINE=rules python3 -m backend.server
```

This uses a small rule-based screener, not Llama or model-based Hinglish understanding.

## Language routing

English, Hindi, and Hinglish use a structured Llama prompt that distinguishes ordinary conversation, suspected trade, ambiguous slang, and news. This is prompt-based screening, not a fine-tuned or accuracy-certified classifier.

- Select **Other local language — manual review** to bypass AI, including for Romanized regional-language text.
- Non-Latin/non-Devanagari alphabetic scripts automatically enter manual language review, even if English was selected.
- The model is instructed to identify other languages, including Romanized regional languages. The server forces those assessments to `unclear` regardless of the model verdict.
- Unknown languages and uncertain understanding also trigger review. Officers can save their own interpretation or translation in the notes.

Romanized-language detection is imperfect; use the explicit manual-review option when known. Devanagari is shared by multiple languages, so script alone cannot distinguish Hindi from every other language.

## Configuration

Set these as environment variables before starting. The application does **not** automatically load `.env` files.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_MODEL` | `llama3.2:3b` | Screening model; the prompt is designed for Llama. |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama API endpoint. |
| `OLLAMA_MODELS` | `.runtime/models` through the launcher | Storage for a runtime started by the launcher; an existing service uses its own configuration. |
| `AUTHORITY_PASSWORD` | Random on each start | Shared local authority password. |
| `HOST` | `127.0.0.1` | Application bind address. |
| `PORT` | `8000` | Application port. |
| `NETRA_DB` | `data/netra.sqlite3` | Local message and review database. |
| `NETRA_ENGINE` | Llama mode | Set to `rules` for the rule-only demo. |

For a different application port:

```sh
PORT=8001 python3 run.py
```

Messages are sent to the configured Ollama endpoint. With the default local endpoint, screening stays on your machine; changing the endpoint changes where message text is sent.

Model responses include language, understanding, verdict, categories, explanation, and evidence. Evidence snippets are checked against the original message. Connection errors, a 120-second timeout, and invalid responses trigger manual review. The readiness indicator checks service reachability and model installation, not guaranteed inference success.

## Tests

Run the automated suite:

```sh
python3 -m unittest discover -s tests -v
```

The suite uses temporary databases and mocked model responses to check screening, language routing, authentication, persistence, invalid input, and failures. Live model tests are skipped by default.

Optional JavaScript syntax check:

```sh
node --check frontend/app.js
```

With Ollama running and the model installed, run the live smoke evaluation:

```sh
NETRA_LIVE_TESTS=1 python3 -m unittest discover -s tests -p test_llama_live.py -v
```

This checks six Hinglish and Romanized Tamil examples. It is a small smoke evaluation, not a measure of general language accuracy.

## Project structure

```text
backend/
  detection.py          Llama adapter, language routing, rule-only demo
  server.py             HTTP server, API, authentication, SQLite storage
frontend/
  index.html            Submission screen and authority portal
  styles.css            Responsive interface styles
  app.js                Submission, queue, and review interactions
tests/
  test_flow.py          Automated screening and API tests
  test_llama_live.py    Opt-in local-model smoke evaluation
run.py                  Local runtime and application launcher
data/                   Generated database; ignored by Git
.runtime/               Downloaded runtime and models; ignored by Git
```

## Sharing on GitHub

Commit the source, tests, README, and `.gitignore`. Ignore rules exclude downloaded runtimes/models, message databases, environment files, private-key files, Python caches, logs, and local tool state.

Inspect staged changes before publishing:

```sh
git status --short
git diff --cached --stat
git diff --cached
```

Do not commit real submitted messages, review notes, passwords, or credentials. Ignore rules do not remove previously tracked files. If a private file was already committed, remove it from Git's index before publishing; exposed credentials also need rotation.

## Prototype scope

NETRA screens manually submitted text. It does not collect Telegram posts, perform OCR, automatically translate unsupported languages, or notify a real government agency. **Authority portal** is the local reviewer workspace; **escalated** is a saved case status.

There is one shared authority password and in-memory sessions that expire after eight hours or on restart. The queue displays up to the latest 1,000 submissions and refreshes every 15 seconds. Review edits overwrite the current note/status; there is no immutable reviewer audit history.

Before internet deployment, add production identity, HTTPS, rate limiting, an audit trail, and retention controls. Screening can make mistakes, so human verification remains necessary.
