import { useEffect, useState } from "react";

/**
 * Load one thing when a page opens, and keep its three states together.
 *
 * App.jsx fetches everything the dashboard needs in one parallel batch, which
 * is right for data several pages share. It is wrong for these: scanning two
 * years of rows for near-duplicates takes seconds, and paying that on every
 * dashboard load — for a page most visits never open — would slow down the app
 * for a panel nobody asked for.
 *
 * So the heavy panels load their own data, once, when you actually go to them.
 *
 * `cancelled` matters because a source filter can change while a request is in
 * flight. Without it the slower, older response lands last and the page shows
 * results for a file the user already navigated away from.
 */
export default function useResource(load, deps = []) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  // Bumping this re-runs the effect without changing what is being asked for,
  // which is exactly what a "Try again" button needs.
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    // Keep the old data on screen while refreshing, so changing a filter dims
    // the panel rather than collapsing the page to a skeleton and back.
    setState((current) => ({ ...current, loading: true }));

    load()
      .then((data) => {
        if (!cancelled) setState({ loading: false, data, error: null });
      })
      .catch((error) => {
        if (!cancelled) setState({ loading: false, data: null, error });
      });

    return () => {
      cancelled = true;
    };
    // The caller states its own dependencies; `load` is a fresh closure every
    // render and would re-fetch forever if it were listed here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  return {
    ...state,
    reload: () => setAttempt((count) => count + 1),
    // Lets a page apply a change it already knows the outcome of — dismissing
    // a duplicate pair, say — without re-running a multi-second scan.
    setData: (data) => setState({ loading: false, data, error: null }),
  };
}
