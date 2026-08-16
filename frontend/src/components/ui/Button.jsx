import { forwardRef } from "react";

/**
 * One button, four intents.
 *
 * Every button in the app comes from here, which is what keeps a "Delete" on
 * one screen looking and behaving like a "Delete" on another.
 *
 * `loading` disables the button as well as showing the spinner. A button that
 * still fires while it says "Saving…" is how you get two of everything.
 *
 * forwardRef because the confirmation dialog focuses its confirm button on
 * open — without the ref that focus lands on <body> and the keyboard user is
 * nowhere.
 */
const Button = forwardRef(function Button(
  {
    variant = "secondary",
    size,
    icon: Icon,
    loading = false,
    disabled = false,
    children,
    className = "",
    ...rest
  },
  ref
) {
  const classes = [
    "btn",
    `btn-${variant}`,
    size ? `btn-${size}` : "",
    children ? "" : "btn-icon",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button ref={ref} className={classes} disabled={disabled || loading} {...rest}>
      {loading ? <span className="btn-spinner" /> : Icon ? <Icon size={15} /> : null}
      {children}
    </button>
  );
});

export default Button;
