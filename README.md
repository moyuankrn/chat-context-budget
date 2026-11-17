# Chat Context Budget

A small Python module that bounds an outgoing chat request while leaving the saved conversation untouched. It was extracted from a private chat gateway and has no runtime dependencies.

The active user turn is kept together with its assistant tool calls and tool results. Older turns are removed as whole turns. Long tool results in the active turn are shortened with explicit markers. If the current input still cannot fit, `ContextTooLarge` is raised instead of silently truncating it.

## Install

```sh
pip install .
```

Or copy `context_budget.py` into your project.

## Use

```python
from context_budget import ContextTooLarge, pack

messages = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "An earlier question"},
    {"role": "assistant", "content": "An earlier answer"},
    {"role": "user", "content": "The current request"},
]
tools = []

try:
    outgoing = pack(messages, turn_start=3, tools=tools, budget=12000)
except ContextTooLarge:
    # Ask for a smaller current input or choose a larger request budget.
    raise

# Send outgoing to your model. Keep messages as your durable history.
```

`turn_start` is the index of the first message in the current turn, after the initial system message. The caller decides where a turn begins. `pack()` returns the original list unchanged when it already fits; when packing is needed it copies the active messages before changing them.

`budget` is a **rough UTF-8 byte-weight estimate**, not a provider token count. Calibrate it for your model and still handle provider context-limit errors. `is_context_error(exc)` recognizes common HTTP 400/413/422 context errors; `force=True` removes older turns for a retry. The caller must decide whether retrying is safe after tool actions.

### Images

If multiple images in the current turn exceed the budget, pass `preview_image(part)`. It must return a smaller `image_url` or `text` part. The newest image stays full resolution. Without that callback, packing raises `ContextTooLarge` so it cannot silently discard image pixels.

```python
outgoing = pack(
    messages, turn_start, tools, budget=22000,
    preview_image=lambda part: {
        **part,
        "image_url": {**part["image_url"], "detail": "low"},
    },
)
```

Supply a real image downsampler when your provider's `detail: low` setting does not reduce the payload enough.

## Test

```sh
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

The tests cover whole-turn removal, active tool pairs, oversized current input, image previews, non-mutation, forced packing, and context error detection.

MIT licensed. See [LICENSE](LICENSE).
