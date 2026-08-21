"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

const RUNGS = 34;
const RADIUS = 1.35;
const HEIGHT = 9;
const TWIST = 2.4 * Math.PI;

function Helix() {
  const group = useRef<THREE.Group>(null);

  useFrame((state, delta) => {
    if (group.current) {
      group.current.rotation.y += delta * 0.12;
      group.current.rotation.z = Math.sin(state.clock.elapsedTime * 0.15) * 0.06;
    }
  });

  const rungs = useMemo(() => {
    return Array.from({ length: RUNGS }, (_, i) => {
      const t = i / (RUNGS - 1);
      const angle = t * TWIST;
      const y = (t - 0.5) * HEIGHT;
      const a = new THREE.Vector3(Math.cos(angle) * RADIUS, y, Math.sin(angle) * RADIUS);
      const b = new THREE.Vector3(-Math.cos(angle) * RADIUS, y, -Math.sin(angle) * RADIUS);
      const mid = a.clone().add(b).multiplyScalar(0.5);
      const quat = new THREE.Quaternion().setFromUnitVectors(
        new THREE.Vector3(0, 1, 0),
        b.clone().sub(a).normalize(),
      );
      return { a, b, mid, quat, key: i };
    });
  }, []);

  return (
    <group ref={group} rotation={[0.28, 0, 0.12]}>
      {rungs.map(({ a, b, mid, quat, key }) => (
        <group key={key}>
          <mesh position={a}>
            <sphereGeometry args={[0.11, 12, 12]} />
            <meshStandardMaterial
              color="#00e5ff"
              emissive="#00e5ff"
              emissiveIntensity={0.55}
              roughness={0.3}
            />
          </mesh>
          <mesh position={b}>
            <sphereGeometry args={[0.11, 12, 12]} />
            <meshStandardMaterial
              color="#8b5cf6"
              emissive="#8b5cf6"
              emissiveIntensity={0.55}
              roughness={0.3}
            />
          </mesh>
          <mesh position={mid} quaternion={quat}>
            <cylinderGeometry args={[0.022, 0.022, RADIUS * 2, 6]} />
            <meshStandardMaterial
              color="#334155"
              emissive="#1e293b"
              emissiveIntensity={0.4}
              transparent
              opacity={0.85}
            />
          </mesh>
        </group>
      ))}
    </group>
  );
}

export default function DnaHelix({ className = "" }: { className?: string }) {
  return (
    <div className={`pointer-events-none ${className}`} aria-hidden>
      <Canvas
        dpr={[1, 1.5]}
        camera={{ position: [0, 0, 7.5], fov: 45 }}
        gl={{ antialias: true, alpha: true }}
      >
        <ambientLight intensity={0.5} />
        <pointLight position={[6, 4, 6]} intensity={40} color="#00e5ff" />
        <pointLight position={[-6, -4, 4]} intensity={30} color="#8b5cf6" />
        <Helix />
      </Canvas>
    </div>
  );
}
