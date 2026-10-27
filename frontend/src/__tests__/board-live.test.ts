// The board's ping handling: coalescing, and holding pings while the user is
// mid-drag or mid-mutation. Timers are a manual fake, so nothing waits.
//
//   node --import ./src/__tests__/resolve-ts.mjs src/__tests__/board-live.test.ts
import assert from 'node:assert/strict';
import { createPingScheduler } from '../lib/board-live';

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

// Minimal manual clock: setTimeout queues, tick(ms) advances and runs what is due.
function fakeTimers() {
  let now = 0;
  let nextId = 1;
  const queue = new Map<number, { at: number; fn: () => void }>();
  return {
    timers: {
      setTimeout: ((fn: () => void, ms: number) => {
        const id = nextId++;
        queue.set(id, { at: now + ms, fn });
        return id;
      }) as unknown as typeof setTimeout,
      clearTimeout: ((id: number) => { queue.delete(id); }) as unknown as typeof clearTimeout,
    },
    tick(ms: number) {
      now += ms;
      for (const [id, t] of [...queue].sort((a, b) => a[1].at - b[1].at)) {
        if (t.at <= now) { queue.delete(id); t.fn(); }
      }
    },
    pending: () => queue.size,
  };
}

function setup() {
  const clock = fakeTimers();
  let refetches = 0;
  const s = createPingScheduler(() => { refetches++; }, 1000, clock.timers);
  return { s, clock, refetches: () => refetches };
}

test('one ping refetches once, after the window', () => {
  const { s, clock, refetches } = setup();
  s.ping();
  clock.tick(999);
  assert.equal(refetches(), 0);
  clock.tick(1);
  assert.equal(refetches(), 1);
});

test('a burst of pings refetches once', () => {
  const { s, clock, refetches } = setup();
  for (let i = 0; i < 50; i++) { s.ping(); clock.tick(10); }
  clock.tick(1000);
  assert.equal(refetches(), 1);
});

test('a steady stream still refetches once per window rather than never', () => {
  const { s, clock, refetches } = setup();
  for (let i = 0; i < 100; i++) { s.ping(); clock.tick(100); } // 10 s of pings
  assert.equal(refetches(), 10);
});

test('pings while busy are held, then replayed once busy ends', () => {
  const { s, clock, refetches } = setup();
  s.setBusy(true);
  s.ping(); s.ping(); s.ping();
  clock.tick(5000);
  assert.equal(refetches(), 0, 'refetched mid-drag');
  s.setBusy(false);
  clock.tick(1000);
  assert.equal(refetches(), 1);
});

test('a timer that expires while busy is held, not fired', () => {
  const { s, clock, refetches } = setup();
  s.ping();
  clock.tick(500);
  s.setBusy(true);          // drag starts with a refetch already scheduled
  clock.tick(1000);
  assert.equal(refetches(), 0, 'refetched under the user mid-drag');
  s.setBusy(false);
  clock.tick(1000);
  assert.equal(refetches(), 1);
});

test('discardPending drops a held ping: the mutation refetches on its own', () => {
  const { s, clock, refetches } = setup();
  s.setBusy(true);
  s.ping();                 // the server's ping for this user's own mutation
  s.discardPending();       // onSettled is about to invalidate anyway
  s.setBusy(false);
  clock.tick(5000);
  assert.equal(refetches(), 0);
});

test('a ping after discardPending, still busy, is held again', () => {
  const { s, clock, refetches } = setup();
  s.setBusy(true);
  s.ping();
  s.discardPending();
  s.ping();                 // someone else moved a case meanwhile
  s.setBusy(false);
  clock.tick(1000);
  assert.equal(refetches(), 1);
});

test('busy ending with nothing held does not refetch', () => {
  const { s, clock, refetches } = setup();
  s.setBusy(true);
  s.setBusy(false);
  clock.tick(5000);
  assert.equal(refetches(), 0);
});

test('dispose cancels a scheduled refetch', () => {
  const { s, clock, refetches } = setup();
  s.ping();
  s.dispose();
  clock.tick(5000);
  assert.equal(refetches(), 0);
  assert.equal(clock.pending(), 0);
});

if (failures) {
  console.error(`\n${failures} failed`);
  process.exit(1);
}
