import copy
import io
import json
import unittest
import urllib.error

import context_budget as budget


class ContextBudgetTests(unittest.TestCase):
    def test_removes_old_turns_and_preserves_active_tool_pair(self):
        old = [
            {'role': 'user', 'content': 'old request ' * 1000},
            {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'old'}]},
            {'role': 'tool', 'tool_call_id': 'old', 'content': 'old result ' * 1000},
        ]
        active = [
            {'role': 'user', 'content': 'current task'},
            {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'new'}]},
            {'role': 'tool', 'tool_call_id': 'new', 'content': 'current result ' * 1000},
        ]
        messages = [{'role': 'system', 'content': 'rules'}] + old + active
        original = copy.deepcopy(messages)
        packed = budget.pack(messages, 4, [], 12000)
        self.assertLessEqual(budget.estimate(packed) + budget.estimate([]), 12000)
        self.assertEqual([m.get('tool_call_id') for m in packed if m['role'] == 'tool'], ['new'])
        self.assertTrue(any(m.get('content') == 'current task' for m in packed))
        self.assertEqual(messages, original)

    def test_oversized_current_user_message_is_rejected(self):
        messages = [{'role': 'system', 'content': 'rules'}, {'role': 'user', 'content': '中' * 5000}]
        with self.assertRaises(budget.ContextTooLarge):
            budget.pack(messages, 1, [], 4096)

    def test_multiple_images_need_an_explicit_preview_callback(self):
        image = lambda name: {'type': 'image_url', 'image_url': {'url': name}}
        messages = [
            {'role': 'system', 'content': 'rules'},
            {'role': 'user', 'content': [{'type': 'text', 'text': 'first'}, image('original')]},
            {'role': 'user', 'content': [{'type': 'text', 'text': 'second'}, image('crop')]},
        ]
        original = json.dumps(messages)
        with self.assertRaises(budget.ContextTooLarge):
            budget.pack(messages, 1, [], 20000)
        packed = budget.pack(messages, 1, [], 20000,
                             preview_image=lambda part: {**part, 'image_url': {**part['image_url'], 'detail': 'low'}})
        urls = [p['image_url']['url'] for m in packed if isinstance(m['content'], list)
                for p in m['content'] if p.get('type') == 'image_url']
        self.assertEqual(urls, ['original', 'crop'])
        self.assertEqual(packed[1]['content'][1]['image_url']['detail'], 'low')
        self.assertNotIn('detail', packed[2]['content'][1]['image_url'])
        self.assertEqual(json.dumps(messages), original)

    def test_force_removes_prior_turns_even_when_they_fit(self):
        messages = [
            {'role': 'system', 'content': 'rules'},
            {'role': 'user', 'content': 'old'},
            {'role': 'assistant', 'content': 'answer'},
            {'role': 'user', 'content': 'current'},
        ]
        packed = budget.pack(messages, 3, [], 10000, force=True)
        self.assertEqual([m['content'] for m in packed], ['rules', 'current'])

    def test_context_error_detection(self):
        error = urllib.error.HTTPError('https://example.invalid', 400, 'Bad Request', {},
                                       io.BytesIO(b'{"error":"maximum context length exceeded"}'))
        self.assertTrue(budget.is_context_error(error))
        other = urllib.error.HTTPError('https://example.invalid', 400, 'Bad Request', {},
                                       io.BytesIO(b'{"error":"invalid tool schema"}'))
        self.assertFalse(budget.is_context_error(other))


if __name__ == '__main__':
    unittest.main()
