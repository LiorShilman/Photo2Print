// Lightbox — הגדלת תמונות preview בלחיצה, זום בגלגלת, סגירה ב-Esc/רקע
import { useEffect, useState } from "react";

interface Props {
  src: string;
  alt?: string;
  onClose: () => void;
}

export default function Lightbox({ src, alt, onClose }: Props) {
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      onWheel={(e) => setZoom((z) => Math.min(6, Math.max(0.5, z * (e.deltaY < 0 ? 1.15 : 0.87))))}
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(10, 12, 20, 0.88)",
        backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
        display: "grid", placeItems: "center", cursor: "zoom-out",
      }}
    >
      <img
        src={src} alt={alt ?? ""}
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: "88vw", maxHeight: "88vh",
          transform: `scale(${zoom})`, transition: "transform .12s ease-out",
          borderRadius: 14, boxShadow: "0 24px 80px rgba(0,0,0,.6)",
          cursor: "default",
        }}
      />
      <div style={{
        position: "fixed", bottom: 22, insetInlineStart: 0, insetInlineEnd: 0,
        textAlign: "center", color: "#96a0b8", fontSize: "0.85rem", pointerEvents: "none",
      }}>
        גלגלת = זום · Esc או לחיצה ברקע = סגירה
      </div>
    </div>
  );
}
