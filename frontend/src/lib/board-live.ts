// Turns a stream of "the case list changed" pings into board refetches.
//
// Kept out of the hook so the timing rules can be tested on plain node, without
// a React harness or a socket.
//
// Coalescing, not a resetting debounce: the first ping starts the timer and
// later ones ride along, so a steady stream refetches once per window instead
// of never. Pings carry no data — any number of them means the same thing.
//
// Busy covers the two moments a refetch would visibly fight the user:
//   * mid-drag     — the overlay card is looked up from the query data, so a
//                    refetch that moves or removes it empties the overlay
//   * mid-mutation — a refetch can return the row from before the write
//                    commits and snap the optimistically moved card back
// Pings that land while busy are held and replayed when it ends.

export const PING_COALESCE_MS = 1000;

export interface PingScheduler {
  ping(): void;
  setBusy(busy: boolean): void;
  /** Drop a held ping because the caller is about to refetch anyway. */
  discardPending(): void;
  dispose(): void;
}

export function createPingScheduler(
  refetch: () => void,
  delayMs = PING_COALESCE_MS,
  timers: Pick<typeof globalThis, 'setTimeout' | 'clearTimeout'> = globalThis,
): PingScheduler {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let busy = false;
  let pending = false;

  function fire() {
    timer = null;
    if (busy) {
      pending = true;
      return;
    }
    refetch();
  }

  function schedule() {
    if (timer === null) timer = timers.setTimeout(fire, delayMs);
  }

  return {
    ping() {
      if (busy) {
        pending = true;
        return;
      }
      schedule();
    },
    setBusy(next) {
      const ended = busy && !next;
      busy = next;
      if (ended && pending) {
        pending = false;
        schedule();
      }
    },
    discardPending() {
      pending = false;
    },
    dispose() {
      if (timer !== null) timers.clearTimeout(timer);
      timer = null;
      pending = false;
    },
  };
}
