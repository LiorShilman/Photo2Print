// Preview שכבות G-code עם slider (F-7.7) + אזורי צבע והחלפות M600
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

interface Layer { z: number; segments: number[][] }
export interface ColorChange { layer: number; color: string }

interface Props {
  jobId: string;
  bed?: { x: number; y: number };
  colorChanges?: ColorChange[];                       // אזורי צבע קיימים (מה-slice האחרון)
  onApplyColorChanges?: (changes: ColorChange[]) => void;  // slice מחדש עם ההחלפות
}

const BASE_COLOR = "#8b93ff";

function zoneColor(layerIdx: number, changes: ColorChange[]): string {
  // הצבע של שכבה = ההחלפה האחרונה שה-layer שלה ≤ אינדקס (1-based)
  let color = BASE_COLOR;
  for (const c of [...changes].sort((a, b) => a.layer - b.layer)) {
    if (c.layer <= layerIdx + 1) color = c.color;
  }
  return color;
}

export default function GcodePreview({ jobId, bed, colorChanges = [], onApplyColorChanges }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [layerIdx, setLayerIdx] = useState(0);
  const [pending, setPending] = useState<ColorChange[]>(colorChanges);
  const [pickColor, setPickColor] = useState("#f472b6");

  const { data, isLoading } = useQuery({
    queryKey: ["gcode_layers", jobId],
    queryFn: async () => {
      const res = await fetch(`/api/v1/jobs/${jobId}/gcode_layers`);
      if (!res.ok) throw new Error("אין G-code");
      return res.json() as Promise<{ layers: Layer[]; count: number }>;
    },
    staleTime: Infinity,
  });

  const layers = data?.layers ?? [];

  useEffect(() => {
    if (layers.length) setLayerIdx((i) => Math.min(i, layers.length - 1));
  }, [layers.length]);

  const bounds = useMemo(() => {
    if (bed) return { minX: 0, minY: 0, maxX: bed.x, maxY: bed.y };
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const l of layers) for (const s of l.segments) {
      minX = Math.min(minX, s[0], s[2]); maxX = Math.max(maxX, s[0], s[2]);
      minY = Math.min(minY, s[1], s[3]); maxY = Math.max(maxY, s[1], s[3]);
    }
    const pad = 10;
    return { minX: minX - pad, minY: minY - pad, maxX: maxX + pad, maxY: maxY + pad };
  }, [layers, bed]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !layers.length) return;
    const ctx = canvas.getContext("2d")!;
    const W = canvas.width, H = canvas.height;
    const spanX = bounds.maxX - bounds.minX, spanY = bounds.maxY - bounds.minY;
    const scale = Math.min(W / spanX, H / spanY);
    const toX = (x: number) => (x - bounds.minX) * scale + (W - spanX * scale) / 2;
    const toY = (y: number) => H - ((y - bounds.minY) * scale + (H - spanY * scale) / 2);

    ctx.fillStyle = "#141827";
    ctx.fillRect(0, 0, W, H);

    if (bed) {
      ctx.strokeStyle = "#2a3046";
      ctx.lineWidth = 1;
      ctx.strokeRect(toX(0), toY(bed.y), bed.x * scale, bed.y * scale);
    }

    const draw = (layer: Layer, color: string, width: number) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      for (const [x1, y1, x2, y2] of layer.segments) {
        ctx.moveTo(toX(x1), toY(y1));
        ctx.lineTo(toX(x2), toY(y2));
      }
      ctx.stroke();
    };

    if (layerIdx > 0) draw(layers[layerIdx - 1], zoneColor(layerIdx - 1, pending) + "33", 1);
    draw(layers[layerIdx], zoneColor(layerIdx, pending), 1.6);
  }, [layers, layerIdx, bounds, bed, pending]);

  if (isLoading) return <p className="muted">טוען שכבות…</p>;
  if (!layers.length) return null;

  const dirty = JSON.stringify(pending) !== JSON.stringify(colorChanges);

  return (
    <div className="card" style={{ direction: "ltr" }}>
      <canvas ref={canvasRef} width={560} height={560} style={{ width: "100%", borderRadius: 10 }} />
      <div style={{ direction: "rtl", marginTop: "0.6rem" }}>
        <label>
          שכבה {layerIdx + 1} מתוך {layers.length} · גובה{" "}
          <span className="mono">{layers[layerIdx].z.toFixed(2)} מ"מ</span>
        </label>
        {/* פס אזורי צבע מתחת ל-slider */}
        <div style={{ display: "flex", height: 6, borderRadius: 99, overflow: "hidden", direction: "ltr", margin: "0.2rem 0" }}>
          {layers.map((_, i) => (
            <div key={i} style={{ flex: 1, background: zoneColor(i, pending), opacity: i <= layerIdx ? 1 : 0.35 }} />
          ))}
        </div>
        <input type="range" min={0} max={layers.length - 1} value={layerIdx}
               onChange={(e) => setLayerIdx(Number(e.target.value))}
               style={{ width: "100%", direction: "ltr" }} />

        {onApplyColorChanges && (
          <div style={{ marginTop: "0.7rem", borderTop: "1px solid var(--border)", paddingTop: "0.7rem" }}>
            <div className="row" style={{ gap: "0.6rem" }}>
              <input type="color" value={pickColor} onChange={(e) => setPickColor(e.target.value)}
                     style={{ width: 42, height: 34, padding: 2, cursor: "pointer" }} />
              <button className="secondary" style={{ padding: "0.35rem 0.9rem" }}
                      onClick={() => setPending([...pending.filter((c) => c.layer !== layerIdx + 1),
                                                 { layer: layerIdx + 1, color: pickColor }])}>
                🎨 החלף צבע משכבה {layerIdx + 1}
              </button>
              {pending.length > 0 && (
                <button className="secondary" style={{ padding: "0.35rem 0.9rem" }}
                        onClick={() => setPending([])}>נקה הכל</button>
              )}
            </div>
            {pending.length > 0 && (
              <div className="row" style={{ marginTop: "0.5rem", gap: "0.4rem" }}>
                {[...pending].sort((a, b) => a.layer - b.layer).map((c) => (
                  <span key={c.layer} className="badge" style={{ background: c.color + "22", color: c.color, border: `1px solid ${c.color}55` }}>
                    שכבה {c.layer}
                    <span style={{ cursor: "pointer", marginInlineStart: 6 }}
                          onClick={() => setPending(pending.filter((p) => p.layer !== c.layer))}>✕</span>
                  </span>
                ))}
              </div>
            )}
            {dirty && (
              <button style={{ marginTop: "0.7rem", width: "100%" }}
                      onClick={() => onApplyColorChanges(pending)}>
                ▶ החל החלפות צבע (Slicing מחדש עם M600)
              </button>
            )}
            <p className="muted" style={{ fontSize: "0.78rem", marginTop: "0.5rem", marginBottom: 0 }}>
              M600 עוצר את המדפסת בתחילת השכבה להחלפת חוט ידנית — נתמך ב-Prusa, Bambu, Marlin.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
