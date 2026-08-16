import { useEffect, useState } from "react";

import {
  IconAlert,
  IconCalendar,
  IconChart,
  IconCopy,
  IconDashboard,
  IconFile,
  IconReceipt,
  IconSearch,
  IconRepeat,
  IconSettings,
  IconShield,
  IconSparkles,
  IconTags,
  IconUpload,
  IconWallet,
} from "./icons.jsx";

/**
 * A router in twenty lines, built on the URL hash.
 *
 * No routing library, because everything this app needs from one is here: a
 * back button that works, a reloadable URL, and links that are real anchors.
 * The hash also means no dev-server rewrite rules — "#/analytics" is still a
 * request for "/".
 *
 * Each route carries its own title and description so the topbar does not keep
 * a second copy of the navigation, drifting out of step with this one.
 */

export const ROUTES = [
  {
    path: "/",
    label: "Dashboard",
    icon: IconDashboard,
    title: "Financial Overview",
    description: "Track your income, expenses and spending patterns.",
    group: "Overview",
  },
  {
    path: "/add",
    label: "Add transaction",
    icon: IconWallet,
    title: "Add Transaction",
    description: "Record an expense or income by hand.",
    group: "Overview",
    // A destination, not a section. It is reached from a button and from the
    // Personal Expenses page, so listing it in the nav beside them would be a
    // third way to the same place.
    hidden: true,
  },
  {
    path: "/personal",
    label: "Personal Expenses",
    icon: IconWallet,
    title: "Personal Expenses",
    description: "Track spending by hand — cash, shared bills, anything a statement misses.",
    group: "Overview",
  },
  {
    path: "/transactions",
    label: "Transactions",
    icon: IconReceipt,
    title: "Transactions",
    description: "Search, filter and correct every imported row.",
    group: "Overview",
  },
  {
    path: "/budgets",
    label: "Budgets",
    icon: IconWallet,
    title: "Budgets",
    description: "Monthly limits you set, and how much of each has gone.",
    group: "Overview",
  },
  {
    path: "/analytics",
    label: "Analytics",
    icon: IconChart,
    title: "Analytics",
    description: "Where the money goes, month by month.",
    group: "Overview",
  },
  {
    path: "/unusual",
    label: "Unusual",
    icon: IconAlert,
    title: "Unusual Spending",
    description: "Transactions far above the usual for their category.",
    group: "Overview",
  },
  {
    path: "/ask",
    label: "Ask",
    icon: IconSearch,
    title: "Ask Your Data",
    description: "Type a question. It is matched to a real query, not answered by a model.",
    group: "Overview",
  },
  {
    path: "/forecast",
    label: "Forecast",
    icon: IconCalendar,
    title: "Cash Flow Forecast",
    description: "What a month like your recent months would cost.",
    group: "Overview",
  },
  {
    path: "/recurring",
    label: "Recurring",
    icon: IconRepeat,
    title: "Recurring Payments",
    description: "Merchants you pay on a regular rhythm, and what they cost each month.",
    group: "Overview",
  },
  {
    path: "/duplicates",
    label: "Possible Duplicates",
    icon: IconCopy,
    title: "Possible Duplicates",
    description: "Pairs that may be one payment recorded twice. Nothing is deleted here.",
    group: "Manage",
  },
  {
    path: "/upload",
    label: "Upload Statement",
    icon: IconUpload,
    title: "Upload Statement",
    description: "Import a CSV, JSON or Excel statement from your bank.",
    group: "Manage",
  },
  {
    path: "/rules",
    label: "Rules",
    icon: IconTags,
    title: "Categorisation Rules",
    description: "Your own keyword rules. They run before the built-in ones and win.",
    group: "Manage",
  },
  {
    path: "/accounts",
    label: "Accounts",
    icon: IconWallet,
    title: "Bank Accounts",
    description: "Which statement came from which account.",
    group: "Manage",
  },
  {
    path: "/categories",
    label: "Categories",
    icon: IconTags,
    title: "Categories",
    description: "The vocabulary every transaction is sorted into.",
    group: "Manage",
  },
  {
    path: "/model",
    label: "AI / Model",
    icon: IconSparkles,
    title: "AI Categorization",
    description: "The classifier that labels merchants no rule covers.",
    group: "Manage",
  },
  {
    path: "/report",
    label: "Report",
    icon: IconFile,
    title: "Financial Report",
    description: "A printable summary of everything, from your own transactions.",
    group: "Manage",
  },
  {
    path: "/quality",
    label: "Data Quality",
    icon: IconShield,
    title: "Data Quality",
    description: "What is wrong, missing or odd about your imported rows.",
    group: "Manage",
  },
  {
    path: "/settings",
    label: "Settings",
    icon: IconSettings,
    title: "Settings",
    description: "Account, connection and data.",
    group: "Manage",
  },
];

const DEFAULT_ROUTE = "/";

/** Old bookmarks should not land on a blank page. */
const ALIASES = { "/files": "/upload", "/overview": "/" };

function currentRoute() {
  const raw = window.location.hash.replace(/^#/, "");
  const path = ALIASES[raw] || raw;
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

export function routeMeta(path) {
  return ROUTES.find((route) => route.path === path) || ROUTES[0];
}

/** Send the user to a route from code, e.g. after an upload. */
export function navigate(path) {
  window.location.hash = path;
}
