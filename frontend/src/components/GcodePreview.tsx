// Preview שכבות G-code עם slider (F-7.7) — קנבס דו-ממדי מבט-על
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

interface Layer { z: number; segments: number[][] }

export default function GcodePreview({ jobId, bed }: { jobId: string; bed?: { x: number; y: number } }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [layerIdx, setLayerIdx] = useState(0);

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
    if (layers.length) setLayerIdx(Math.min(layerIdx, layers.length - 1));
  }, [layers.length]);

  // גבולות ציור — לפי המשטח או לפי תחום המודל
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

    if (bed) { // מסגרת משטח
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

    if (layerIdx > 0) draw(layers[layerIdx - 1], "#818cf833", 1); // שכבה קודמת — עמומה
    draw(layers[layerIdx], "#8b93ff", 1.6);
  }, [layers, layerIdx, bounds, bed]);

  if (isLoading) return <p className="muted">טוען שכבות…</p>;
  if (!layers.length) return null;

  return (
    <div className="card" style={{ direction: "ltr" }}>
      <canvas ref={canvasRef} width={560} height={560} style={{ width: "100%", borderRadius: 10 }} />
      <div style={{ direction: "rtl", marginTop: "0.6rem" }}>
        <label>
          שכבה {layerIdx + 1} מתוך {layers.length} · גובה{" "}
          <span className="mono">{layers[layerIdx].z.toFixed(2)} מ"מ</span>
        </label>
        <input type="range" min={0} max={layers.length - 1} value={layerIdx}
               onChange={(e) => setLayerIdx(Number(e.target.value))}
               style={{ width: "100%" }} />
      </div>
    </div>
  );
}
