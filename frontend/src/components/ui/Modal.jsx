import { useEffect, useRef } from "react";

import { IconAlert } from "../../icons.jsx";
import Button from "./Button.jsx";

/**
 * A confirmation the user cannot lose track of.
 *
 * Three accessibility obligations that a plain <div> overlay does not meet on
 * its own, all of them handled here so no caller has to remember them:
 *
 *   - Escape closes it. A dialog you can only leave with the mouse is a trap.
 *   - Focus moves into the dialog on open, so a keyboard user is actually
 *     where the dialog is, and returns to the trigger on close.
 *   - The backdrop click closes, but a click inside must not bubble out to it.
 *
 * `tone="danger"` is for actions that destroy data, and the confirm button
 * says what will happen rather than "OK" - "Delete 205 transactions" is a
 * decision, "OK" is a reflex.
 */
export default function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "primary",
  busy = false,
  onConfirm,
  onCancel,
}) {
  const confirmRef = useRef(null);
  const previouslyFocused = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    previouslyFocused.current = document.activeElement;
    confirmRef.current?.focus();

    function onKeyDown(event) {
      if (event.key === "Escape") onCancel();
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      // Put focus back where it was, or it lands on <body> and the next Tab
      // starts from the top of the page.
      previouslyFocused.current?.focus?.();
    };
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="backdrop" onClick={onCancel}>
      <div
        className="modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          {tone === "danger" && (
            <span className="state-icon danger" style={{ width: 34, height: 34 }}>
              <IconAlert size={17} />
            </span>
          )}
          <h2 id="dialog-title" style={{ fontSize: 15, paddingTop: 6 }}>
            {title}
          </h2>
        </div>

        <div className="modal-body">{children}</div>

        <div className="modal-foot">
          <Button variant="secondary" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            ref={confirmRef}
            variant={tone === "danger" ? "danger" : "primary"}
            onClick={onConfirm}
            loading={busy}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
