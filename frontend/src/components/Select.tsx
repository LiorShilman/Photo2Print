// Select מעוצב — מחליף את ה-<select> הנייטיבי שלא ניתן לעיצוב בפתיחה
import { useEffect, useRef, useState } from "react";

export interface SelectOption {
  value: string;
  label: string;
  hint?: string;   // טקסט משני קטן (למשל מידות משטח)
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  style?: React.CSSProperties;
}

export default function Select({ value, onChange, options, placeholder = "בחר…", style }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="select" style={style}>
      <button type="button" className="select-trigger" onClick={() => setOpen(!open)}>
        <span dir="auto" className={selected ? "" : "muted"}>
          {selected?.label ?? placeholder}
        </span>
        <span className="select-chevron">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="select-menu" role="listbox">
          {options.map((o) => (
            <div
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              className={`select-option ${o.value === value ? "selected" : ""}`}
              onClick={() => { onChange(o.value); setOpen(false); }}
            >
              <span dir="auto">{o.label}</span>
              {o.hint && <span className="select-hint mono">{o.hint}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
