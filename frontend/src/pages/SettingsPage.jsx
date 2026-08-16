import { useEffect, useState } from "react";

import * as api from "../api.js";
import PreferencesCard from "../components/PreferencesCard.jsx";
import Card, { CardHead, CardFoot } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import Badge from "../components/ui/Badge.jsx";
import {
  IconDatabase,
  IconLogOut,
  IconMonitor,
  IconMoon,
  IconSun,
} from "../icons.jsx";
import { useThemeMode } from "../theme-mode.js";

/**
 * Account, connection, and an honest account of what this app does not do.
 *
 * There is no settings endpoint and no preferences table, so nothing here
 * pretends to save. Every value is either something the backend already
 * reports or something the browser already knows. A row of toggles that reset
 * on reload would look more like a product and be worth less than nothing.
 */
export default function SettingsPage({
  session,
  summary,
  sources,
  categories,
  onSignOut,
  dataVersion,
  onError,
  onSuccess,
  onChanged,
}) {
  const [online, setOnline] = useState(null);
  const [checking, setChecking] = useState(false);

  async function check() {
    setChecking(true);
    setOnline(await api.getHealth());
    setChecking(false);
  }

  useEffect(() => {
    check();
  }, []);

  return (
    <div className="stack">
      <AppearanceCard />

      {/* Preferences before Appearance: what the app does matters more than
          how it looks, and sensitivity is the one setting here that changes
          an analysis rather than a colour. */}
      {onChanged && (
        <PreferencesCard
          dataVersion={dataVersion}
          onError={onError}
          onSuccess={onSuccess}
          onChanged={onChanged}
        />
      )}

      <Card>
        <CardHead title="Account" bordered />
        <div className="card-body">
          <div className="grid-2">
            <Field label="Name" value={session?.display_name || "—"} />
            <Field label="Email" value={session?.email || "—"} />
          </div>

          <div style={{ marginTop: "var(--sp-5)" }}>
            <Button variant="secondary" icon={IconLogOut} onClick={onSignOut}>
              Sign out
            </Button>
          </div>
        </div>
        <CardFoot>
          Signing in unlocks this interface and nothing else — no endpoint asks
          who is calling. Anyone who can reach the API can read this data
          whether they have an account or not.
        </CardFoot>
      </Card>

      <Card>
        <CardHead
          title="Backend connection"
          description="Where this interface sends every request"
          actions={
            <Badge tone={online === null ? "neutral" : online ? "success" : "danger"} dot>
              {online === null ? "Checking" : online ? "Connected" : "Unreachable"}
            </Badge>
          }
          bordered
        />
        <div className="card-body">
          <div className="grid-2">
            <Field label="API base URL" value={api.API_BASE_URL} mono />
            <Field
              label="Status"
              value={
                online === null
                  ? "Checking…"
                  : online
                    ? "Responding normally"
                    : "No response — is the server running?"
              }
            />
          </div>

          <div style={{ marginTop: "var(--sp-5)" }}>
            <Button variant="secondary" loading={checking} onClick={check}>
              Check again
            </Button>
          </div>
        </div>
        <CardFoot>
          Change the address in <code>src/api.js</code> — it is defined once, so
          the whole app follows.
        </CardFoot>
      </Card>

      <Card>
        <CardHead
          title="Your data"
          description="Everything currently stored in the local database"
          bordered
        />
        <div className="card-body">
          <div className="grid-4">
            <Field
              label="Transactions"
              value={summary.transaction_count.toLocaleString("en-IN")}
            />
            <Field label="Imported files" value={sources.length} />
            <Field
              label="Categories in use"
              value={categories.filter((entry) => entry.count > 0).length}
            />
            <Field
              label="Corrections made"
              value={(
                summary.by_category_source.find((entry) => entry.source === "user")
                  ?.count || 0
              ).toLocaleString("en-IN")}
            />
          </div>
        </div>
        <CardFoot>
          <span
            style={{ display: "inline-flex", alignItems: "center", gap: "var(--sp-2)" }}
          >
            <IconDatabase size={13} />
            Stored unencrypted in <code>backend/data/expenses.db</code>. Deleting
            a file from the Upload page is the only way to remove its rows.
          </span>
        </CardFoot>
      </Card>
    </div>
  );
}

/**
 * Light, dark, or follow the system.
 *
 * A radiogroup rather than three buttons: the options are mutually exclusive,
 * so arrow keys should move between them and a screen reader should announce
 * "2 of 3". Three <button>s would need all of that written by hand and would
 * still announce wrongly.
 *
 * The preference is the one thing on this page that does persist — in
 * localStorage, which is where a display preference belongs. It is not account
 * state, and sending it to a server that has no settings endpoint would be
 * inventing an API to store something the browser already holds.
 */
function AppearanceCard() {
  const { mode, resolved, setMode } = useThemeMode();

  const options = [
    { value: "light", label: "Light", icon: IconSun },
    { value: "dark", label: "Dark", icon: IconMoon },
    { value: "system", label: "System", icon: IconMonitor },
  ];

  return (
    <Card>
      <CardHead
        title="Appearance"
        description="Choose a theme, or follow your operating system."
        bordered
      />
      <div className="card-body">
        <div
          className="segmented"
          role="radiogroup"
          aria-label="Colour theme"
        >
          {options.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={mode === value}
              onClick={() => setMode(value)}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </div>

        <p className="note" style={{ marginTop: "var(--sp-3)" }}>
          {mode === "system"
            ? `Following your system, which is currently ${resolved}.`
            : `Always ${mode}, on this browser.`}
        </p>
      </div>
      <CardFoot>
        Saved in this browser only — it is a display preference, not account
        state, so it does not follow you to another device.
      </CardFoot>
    </Card>
  );
}

function Field({ label, value, mono = false }) {
  return (
    <div className="field">
      <span className="stat-label">{label}</span>
      <span
        style={{
          fontSize: 14,
          fontWeight: 550,
          fontFamily: mono ? "var(--font-mono)" : undefined,
          wordBreak: "break-all",
        }}
      >
        {value}
      </span>
    </div>
  );
}
