import { useEffect, useState } from "react";

/**
 * A router in fifteen lines, built on the URL hash.
 *
 * No routing library, because everything this app needs from one is here:
 * a back button that works, a reloadable URL, and links that are real
 * anchors. The hash also means no dev-server rewrite rules — "#/model" is
 * still a request for "/".
 */

export const ROUTES = [
  { path: "/", label: "Overview" },
  { path: "/transactions", label: "Transactions" },
  { path: "/unusual", label: "Unusual" },
  { path: "/files", label: "Files" },
  { path: "/model", label: "Model" },
];

const DEFAULT_ROUTE = "/";

function currentRoute() {
  const path = window.location.hash.replace(/^#/, "");
  return ROUTES.some((route) => route.path === path) ? path : DEFAULT_ROUTE;
}

export function useRoute() {
  const [route, setRoute] = useState(currentRoute);

  useEffect(() => {
    const onHashChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return route;
}

/** Send the user to a route from code, e.g. after an upload. */
export function navigate(path) {
  window.location.hash = path;
}
