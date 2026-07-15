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

function ModelMesh({ geo, targetMm, axis }: { geo: THREE.BufferGeometry; targetMm?: number; axis: "x" | "y" | "z" }) {
  const { scale, dims, offset } = useMemo(() => {
    const bb = geo.boundingBox!;
    const size = new THREE.Vector3();
    bb.getSize(size);
    const axisSize = { x: size.x, y: size.y, z: size.z }[axis] || 1;
    const s = targetMm ? targetMm / axisSize : 1;
    const center = new THREE.Vector3();
    bb.getCenter(center);
    return {
      scale: s,
      dims: { x: size.x * s, y: size.y * s, z: size.z * s },
      offset: new THREE.Vector3(-center.x * s, -center.y * s, -bb.min.z * s),
    };
  }, [geo, targetMm, axis]);

  return (
    <group>
      {/* המרה: Z-up (עולם הדפסה) בתוך סצנת three (Y-up) נעשית בהיפוך המצלמה */}
      <mesh geometry={geo} scale={[scale, scale, scale]} position={offset.toArray()}>
        <meshStandardMaterial color="#2dd4bf" metalness={0.1} roughness={0.55} />
      </mesh>
      <DimsLabel dims={dims} />
    </group>
  );
}

function DimsLabel({ dims }: { dims: { x: number; y: number; z: number } }) {
  return (
    <group position={[0, 0, dims.z + 12]} />
  );
}

export default function Viewer3D({ stlUrl, bed, targetHeightMm, scaleAxis = "z" }: Props) {
  const geo = useStl(stlUrl);
  const bedX = bed?.x ?? 220;
  const bedY = bed?.y ?? 220;

  const dimsText = useMemo(() => {
    if (!geo?.boundingBox) return "";
    const size = new THREE.Vector3();
    geo.boundingBox.getSize(size);
    const axisSize = { x: size.x, y: size.y, z: size.z }[scaleAxis] || 1;
    const s = targetHeightMm ? targetHeightMm / axisSize : 1;
    return `${(size.x * s).toFixed(1)} × ${(size.y * s).toFixed(1)} × ${(size.z * s).toFixed(1)} מ"מ`;
  }, [geo, targetHeightMm, scaleAxis]);

  return (
    <div className="viewer-canvas" style={{ position: "relative" }}>
      <Canvas camera={{ position: [bedX * 0.9, -bedY * 1.1, bedX * 0.8], fov: 45, up: [0, 0, 1], near: 1, far: 5000 }}>
        <color attach="background" args={["#0d1117"]} />
        <ambientLight intensity={0.55} />
        <directionalLight position={[100, -120, 220]} intensity={1.15} />
        <directionalLight position={[-150, 100, 80]} intensity={0.35} color="#88aaff" />
        {/* משטח הדפסה וירטואלי */}
        <mesh position={[0, 0, -0.5]}>
          <boxGeometry args={[bedX, bedY, 1]} />
          <meshStandardMaterial color="#161b22" />
        </mesh>
        <Grid
          position={[0, 0, 0.05]} args={[bedX, bedY]} rotation={[Math.PI / 2, 0, 0]}
          cellSize={10} cellColor="#30363d" sectionSize={50} sectionColor="#2dd4bf44"
          fadeDistance={1200} infiniteGrid={false}
        />
        <Suspense fallback={null}>
          {geo && <ModelMesh geo={geo} targetMm={targetHeightMm} axis={scaleAxis} />}
        </Suspense>
        <OrbitControls makeDefault target={[0, 0, 30]} />
      </Canvas>
      {dimsText && (
        <div className="mono" style={{
          position: "absolute", bottom: 10, left: 12, background: "#161b22cc",
          padding: "4px 10px", borderRadius: 8, fontSize: "0.85rem", direction: "rtl",
        }}>
          📐 {dimsText}
        </div>
      )}
      {!geo && <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "#8b949e" }}>טוען מודל…</div>}
    </div>
  );
}
