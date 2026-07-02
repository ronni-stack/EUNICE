# EUNICE — End-User Quick Start

## Starting a conversation

Send a message:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $EUNICE_API_KEY" \
  -H "X-EUNICE-Device-ID: my-phone" \
  -d '{"message":"Hello EUNICE"}'
```

## Memory commands

- **Remember a fact**: `Remember that my favorite color is blue`
- **Recall facts**: `What do you know about me?`
- **Explicit store**: `Remember that [fact]`

## Sessions

Use the `session` field to keep separate conversation threads:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $EUNICE_API_KEY" \
  -H "X-EUNICE-Device-ID: my-phone" \
  -d '{"message":"Plan the Nairobi trip","session":"trip-2026"}'
```

## Tools

EUNICE can run tools based on your permissions:

- **Notes**: `Take a note: call bank tomorrow`
- **Weather/time**: `What time is it in Berlin?`
- **Code**: `Write a Python function to parse CSV`
- **Network scan**: `Scan my network` (may require confirmation)
- **Banking**: `What is my balance?` / `Transfer $50 to savings` (high-risk, requires confirmation)

## File manager

Upload or manage files in your sandboxed workspace:

- `POST /files/write`
- `POST /files/upload`
- `GET /files?path=...`
- `DELETE /files?path=...`

## Documents / RAG

Upload PDF, TXT, or MD files for retrieval-augmented answers:

```bash
curl -X POST http://localhost:8000/documents/upload \
  -H "Authorization: Bearer $EUNICE_API_KEY" \
  -H "X-EUNICE-Device-ID: my-phone" \
  -F "file=@report.pdf"
```

Then ask questions about the document.
