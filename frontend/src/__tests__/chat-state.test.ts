// The chat widget shows errors inline, but an error must never be sent back
// to the LLM as part of `history` — the model would read "The assistant is
// temporarily unavailable" as something it said, and repeat or reason from it.
//
//   node --import ./src/__tests__/resolve-ts.mjs src/__tests__/chat-state.test.ts
import assert from 'node:assert/strict';
import {
  initialChatState, withUserTurn, withReply, withError, requestBody,
  errorMessageFrom, FALLBACK_ERROR, type ChatState,
} from '../lib/chat-state';

const DETAIL = 'The assistant is temporarily unavailable, please try again.';
const err503 = { response: { status: 503, data: { detail: DETAIL } } };

let failures = 0;
function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`ok   ${name}`);
  } catch (e) {
    failures++;
    console.error(`FAIL ${name}\n     ${(e as Error).message}`);
  }
}

// One failed exchange, the way useChat drives it.
function failedSend(state: ChatState, message: string, error: unknown): ChatState {
  return withError(withUserTurn(state, message), errorMessageFrom(error));
}

test('error reply is not in the history sent with the next message', () => {
  const s = failedSend(initialChatState, 'what is urgent?', err503);
  const body = requestBody(s, 'try again');

  assert.deepEqual(body.history, []);
  assert.ok(!JSON.stringify(body).includes(DETAIL), 'error text leaked into request');
});

test('error after a successful exchange leaves the server history intact', () => {
  const serverHistory = [
    { role: 'user', content: 'hi' },
    { role: 'assistant', content: 'Hello.' },
  ];
  let s = withReply(withUserTurn(initialChatState, 'hi'), 'Hello.', serverHistory);
  s = failedSend(s, 'what is urgent?', err503);

  const body = requestBody(s, 'try again');
  assert.deepEqual(body.history, serverHistory);
  assert.ok(!JSON.stringify(body).includes(DETAIL), 'error text leaked into request');
});

test('repeated errors never accumulate in history', () => {
  let s = initialChatState;
  for (let i = 0; i < 3; i++) s = failedSend(s, `attempt ${i}`, err503);
  assert.deepEqual(requestBody(s, 'again').history, []);
});

test('error is shown inline and the user message is kept', () => {
  const s = failedSend(initialChatState, 'what is urgent?', err503);
  assert.deepEqual(s.turns, [
    { role: 'user', content: 'what is urgent?' },
    { role: 'assistant', content: DETAIL, error: true },
  ]);
});

test('server detail is shown when present', () => {
  const forbidden = { response: { data: { detail: "The assistant isn't available for your role." } } };
  assert.equal(errorMessageFrom(forbidden), "The assistant isn't available for your role.");
});

test('network failure with no response falls back to the standard message', () => {
  assert.equal(errorMessageFrom(new Error('Network Error')), FALLBACK_ERROR);
  assert.equal(errorMessageFrom(undefined), FALLBACK_ERROR);
});

test('non-string detail (e.g. a 422 validation list) falls back', () => {
  assert.equal(errorMessageFrom({ response: { data: { detail: [{ msg: 'x' }] } } }), FALLBACK_ERROR);
});

if (failures) {
  console.error(`\n${failures} failed`);
  process.exit(1);
}
console.log('\nall passed');
