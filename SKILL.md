---
name: chat-context-budget
description: Repair OpenAI-style chat requests that exceed a context budget while preserving the active user turn and its tool-call/result chain. Use when a long chat or tool output triggers a context-limit error.
---

# Chat context budget

Use the bundled `context_budget.py` to bound an outgoing OpenAI-style message list without deleting saved history. It has no third-party dependencies. The user or application must provide a safe point to pack the request before sending it.

## Work on the user's request

1. Inspect a redacted outgoing request and identify the first message of the active user turn. Set `turn_start` to that index; do not infer it from the last `user` role when tool results or multi-message turns are possible. Include the tool schemas in the budget calculation.
2. Record the pre-pack `estimate(messages) + estimate(tools)` and the target budget. Explain that `estimate()` is a UTF-8 byte-weight heuristic, not a provider token count. Calibrate against actual provider usage or errors before choosing a production threshold.
3. Call `pack(messages, turn_start, tools, budget)`. Integrate the returned list only into the outgoing provider request; preserve durable chat history. The helper removes older turns as units, may include an explicitly labelled extractive historical digest, and shortens long active tool results. It keeps the current user message, system message, tool calls, and matching tool-result messages.
4. If `ContextTooLarge` is raised, show which indivisible part still exceeds the estimate and offer a smaller current input, staged file reading, or a higher provider limit. For multiple active images, supply a real `preview_image` callback only when the user/application allows reduced image detail. Never imply that setting `detail: low` reduces wire bytes for every provider.
5. Verify the packed request is within the chosen estimate, that current instructions and tool-call IDs survive, and that the original messages are unchanged. Test a provider context-limit response separately; `is_context_error` only recognizes common HTTP 400/413/422 error bodies. Retry only when the application can establish that repeating any prior tool actions is safe.

## Boundaries

- The helper expects OpenAI-style messages and a caller-supplied `turn_start`; it is not a universal token counter or automatic summarizer.
- Active tool-result text may be excerpted. If the full result is required for correctness, keep it out of this packing path or split the task into smaller calls.
- Do not promise a particular token or dollar saving without provider measurements and a quality check on the user's workload.

The reference implementation is MIT licensed: https://github.com/moyuankrn/chat-context-budget .
