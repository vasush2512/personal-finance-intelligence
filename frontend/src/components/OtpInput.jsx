import { useEffect, useRef } from "react";

/**
 * Six boxes that behave like one field.
 *
 * The fiddly parts, all of which are what makes the difference between this
 * feeling native and feeling like a toy:
 *
 *  - typing advances, Backspace on an empty box retreats
 *  - pasting the whole code fills every box, however it was pasted
 *  - arrow keys move without editing
 *  - inputMode="numeric" brings up the digit keypad on a phone
 *  - autoComplete="one-time-code" lets iOS and Android offer the code from
 *    the SMS itself
 */
export default function OtpInput({ length = 6, value, onChange, onComplete, disabled }) {
  const inputs = useRef([]);

  useEffect(() => {
    inputs.current[0]?.focus();
  }, []);

  const digits = value.padEnd(length, " ").slice(0, length).split("");

  function setDigit(index, digit) {
    const next = digits.map((d, i) => (i === index ? digit : d)).join("");
    const cleaned = next.replace(/\s/g, " ").trimEnd();
    onChange(cleaned);

    const complete = cleaned.replace(/\s/g, "");
    if (complete.length === length) onComplete?.(complete);
  }

  function handleChange(index, raw) {
    const typed = raw.replace(/\D/g, "");
    if (!typed) return;

    // A whole code arriving in one box means it was pasted or autofilled.
    if (typed.length > 1) {
      const filled = typed.slice(0, length);
      onChange(filled);
      inputs.current[Math.min(filled.length, length - 1)]?.focus();
      if (filled.length === length) onComplete?.(filled);
      return;
    }

    setDigit(index, typed);
    if (index < length - 1) inputs.current[index + 1]?.focus();
  }

  function handleKeyDown(index, event) {
    if (event.key === "Backspace") {
      event.preventDefault();
      if (digits[index].trim()) {
        setDigit(index, " ");
      } else if (index > 0) {
        setDigit(index - 1, " ");
        inputs.current[index - 1]?.focus();
      }
      return;
    }

    if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      inputs.current[index - 1]?.focus();
    }
    if (event.key === "ArrowRight" && index < length - 1) {
      event.preventDefault();
      inputs.current[index + 1]?.focus();
    }
  }

  function handlePaste(event) {
    const pasted = event.clipboardData.getData("text").replace(/\D/g, "");
    if (!pasted) return;
    event.preventDefault();
    const filled = pasted.slice(0, length);
    onChange(filled);
    inputs.current[Math.min(filled.length, length - 1)]?.focus();
    if (filled.length === length) onComplete?.(filled);
  }

  return (
    <div className="otp-row" role="group" aria-label="One-time code">
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(element) => {
            inputs.current[index] = element;
          }}
          className={`otp-box ${digit.trim() ? "filled" : ""}`}
          type="text"
          inputMode="numeric"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          maxLength={length}
          value={digit.trim()}
          disabled={disabled}
          aria-label={`Digit ${index + 1}`}
          onChange={(event) => handleChange(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onPaste={handlePaste}
          onFocus={(event) => event.target.select()}
        />
      ))}
    </div>
  );
}
