/** @file Ishiban browser entrypoint and explicit live/demo selection. */
import {useEffect, useState, useSyncExternalStore} from 'react';
import {createRoot} from 'react-dom/client';
import {createBoardStore, startLive} from './client';
import {startLazyActivity} from './lazy-activity';
import {createDemoSnapshot} from './demo';
import {Board} from './ui/board';

const store = createBoardStore((notify) => requestAnimationFrame(() => notify()));
const demo = createDemoSnapshot();

/** Render the observatory; for example, demo mode never opens a live stream. */
function Application() {
  const [isDemo, setIsDemo] = useState(false);
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  useEffect(() => {
    if (isDemo) return;
    const stopLive = startLive(store);
    const stopActivity = startLazyActivity(store);
    return () => {
      stopActivity();
      stopLive();
    };
  }, [isDemo]);
  const snapshot = isDemo ? demo : state.snapshot;
  const connection = isDemo ? 'Demo data — no live connections' : state.connection;
  return (
    <>
      <nav className="data-mode" aria-label="Data source" data-cursor={snapshot?.cursor}>
        <span>ISHIBAN / OBSERVATION SPIKE</span>
        <div className="data-mode-actions">
          <button className="btn btn-xs" type="button" aria-pressed={!isDemo} onClick={() => setIsDemo(false)}>
            Live · leynos
          </button>
          <button className="btn btn-xs" type="button" aria-pressed={isDemo} onClick={() => setIsDemo(true)}>
            Demo data · 120 repositories
          </button>
        </div>
      </nav>
      {snapshot ? (
        <Board snapshot={snapshot} connection={connection} />
      ) : (
        <main className="connection-placeholder">
          <h1>Ishiban</h1>
          <p role="status">{state.connection}</p>
          <p>Start the collector to observe leynos, or explore the labelled demo.</p>
        </main>
      )}
    </>
  );
}

const root = document.querySelector('#root');
if (root) createRoot(root).render(<Application />);
