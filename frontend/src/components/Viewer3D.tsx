// Viewer תלת-ממד — Three.js + React Three Fiber (S-4)
// מציג את המודל על משטח הדפסה וירטואלי בגודל אמיתי + bounding box חי
import { Suspense, useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Grid, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

interface Props {
  stlUrl: string;
  bed?: { x: number; y: number; z: number };
  targetHeightMm?: number;      // סקייל חי לפי קלט המשתמש
  scaleAxis?: "x" | "y" | "z";
  rotationDeg?: [number, number, number];  // סיבוב ידני (F-5.5)
}

function useStl(url: string) {
  const [geo, setGeo] = useState<THREE.BufferGeometry | null>(null);
  useEffect(() => {
    let alive = true;
    new STLLoader().load(url, (g) => {
      if (!alive) return;
      g.computeVertexNormals();
      g.computeBoundingBox();
      setGeo(g);
    });
    return () => { alive = false; };
  }, [url]);
  return geo;
}

function ModelMesh({ geo, targetMm, axis, rotationDeg }: {
  geo: THREE.BufferGeometry; targetMm?: number; axis: "x" | "y" | "z";
  rotationDeg?: [number, number, number];
}) {
  const { scale, offset } = useMemo(() => {
    // הסיבוב מוחל על הגיאומטריה לפני חישוב הסקייל וההנחה על המשטח,
    // כדי שהתצוגה תתאים למה שהשרת יבצע (סיבוב → סקייל → הנחה)
    const rotated = geo.clone();
    const [rx, ry, rz] = (rotationDeg ?? [0, 0, 0]).map((d) => (d * Math.PI) / 180);
    if (rx || ry || rz) {
      const m = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(rx, ry, rz, "XYZ"));
      rotated.applyMatrix4(m);
    }
    rotated.computeBoundingBox();
    const bb = rotated.boundingBox!;
    const size = new THREE.Vector3();
    bb.getSize(size);
    const axisSize = { x: size.x, y: size.y, z: size.z }[axis] || 1;
    const s = targetMm ? targetMm / axisSize : 1;
    const center = new THREE.Vector3();
    bb.getCenter(center);
    return {
      scale: s,
      offset: new THREE.Vector3(-center.x * s, -center.y * s, -bb.min.z * s),
    };
  }, [geo, targetMm, axis, rotationDeg]);

  const [rx, ry, rz] = (rotationDeg ?? [0, 0, 0]).map((d) => (d * Math.PI) / 180);
  return (
    <group position={offset.toArray()} scale={[scale, scale, scale]}>
      <mesh geometry={geo} rotation={[rx, ry, rz]}>
        <meshStandardMaterial color="#818cf8" metalness={0.15} roughness={0.45} />
      </mesh>
    </group>
  );
}

export default function Viewer3D({ stlUrl, bed, targetHeightMm, scaleAxis = "z", rotationDeg }: Props) {
  const geo = useStl(stlUrl);
  const bedX = bed?.x ?? 220;
  const bedY = bed?.y ?? 220;

  const dimsText = useMemo(() => {
    if (!geo?.boundingBox) return "";
    const rotated = geo.clone();
    const [rx, ry, rz] = (rotationDeg ?? [0, 0, 0]).map((d) => (d * Math.PI) / 180);
    if (rx || ry || rz) {
      rotated.applyMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(rx, ry, rz, "XYZ")));
      rotated.computeBoundingBox();
    }
    const size = new THREE.Vector3();
    rotated.boundingBox!.getSize(size);
    const axisSize = { x: size.x, y: size.y, z: size.z }[scaleAxis] || 1;
    const s = targetHeightMm ? targetHeightMm / axisSize : 1;
    return `${(size.x * s).toFixed(1)} × ${(size.y * s).toFixed(1)} × ${(size.z * s).toFixed(1)} מ"מ`;
  }, [geo, targetHeightMm, scaleAxis, rotationDeg]);

  return (
    <div className="viewer-canvas" style={{ position: "relative" }}>
      <Canvas camera={{ position: [bedX * 0.9, -bedY * 1.1, bedX * 0.8], fov: 45, up: [0, 0, 1], near: 1, far: 5000 }}>
        <color attach="background" args={["#141827"]} />
        <fog attach="fog" args={["#141827", 900, 2400]} />
        <ambientLight intensity={0.55} />
        <directionalLight position={[100, -120, 220]} intensity={1.15} />
        <directionalLight position={[-150, 100, 80]} intensity={0.4} color="#a5b4fc" />
        {/* משטח הדפסה וירטואלי */}
        <mesh position={[0, 0, -0.5]}>
          <boxGeometry args={[bedX, bedY, 1]} />
          <meshStandardMaterial color="#1b1f2e" />
        </mesh>
        <Grid
          position={[0, 0, 0.05]} args={[bedX, bedY]} rotation={[Math.PI / 2, 0, 0]}
          cellSize={10} cellColor="#2a3046" sectionSize={50} sectionColor="#818cf844"
          fadeDistance={1200} infiniteGrid={false}
        />
        <Suspense fallback={null}>
          {geo && <ModelMesh geo={geo} targetMm={targetHeightMm} axis={scaleAxis} rotationDeg={rotationDeg} />}
        </Suspense>
        <OrbitControls makeDefault target={[0, 0, 30]} />
      </Canvas>
      {dimsText && (
        <div className="mono" style={{
          position: "absolute", bottom: 10, left: 12, background: "#1b1f2ecc",
          padding: "4px 10px", borderRadius: 8, fontSize: "0.85rem", direction: "rtl",
          border: "1px solid rgba(148,163,184,0.14)",
        }}>
          📐 {dimsText}
        </div>
      )}
      {!geo && <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "#96a0b8" }}>טוען מודל…</div>}
    </div>
  );
}
