"use client";

import { useRef } from "react";
import { useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

import { useOrgStore } from "@/store/orgStore";

import { useOrgGraphLayout } from "./useOrgGraphLayout";

/**
 * Cinematic camera: orbit/zoom stay under user control via OrbitControls,
 * while `activeDepartment` (real, derived from the live event stream --
 * see orgStore.applyEvent) drives an automatic GSAP fly-to whenever the
 * department the pipeline is actively touching changes. Research begins
 * -> camera moves toward Research; research finishes and the Executive
 * reviews it -> activeDepartment flips back to "Executive" and the camera
 * returns; Product/Engineering follow the same real signal. No department
 * is ever focused because of a click or a timer -- only because a real
 * OrgEvent said that's where the organization is currently working.
 */

const HOME_TARGET = new THREE.Vector3(0, 0, 0);
const HOME_POSITION = new THREE.Vector3(0, 3.2, 11);

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function CinematicCamera() {
  const { camera } = useThree();
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const activeDepartment = useOrgStore((state) => state.activeDepartment);
  const { departmentCentroids } = useOrgGraphLayout();

  useGSAP(
    () => {
      const controls = controlsRef.current;
      if (!controls) return;

      const centroid = activeDepartment ? departmentCentroids.get(activeDepartment) : null;
      const target = centroid
        ? new THREE.Vector3(centroid[0], centroid[1], centroid[2])
        : HOME_TARGET.clone();
      // Pull back from the target along a fixed viewing angle rather than
      // teleporting the camera inside the node cluster.
      const position = centroid
        ? new THREE.Vector3(centroid[0] * 0.5, centroid[1] + 3.4, centroid[2] * 0.5 + 8.5)
        : HOME_POSITION.clone();

      if (prefersReducedMotion()) {
        camera.position.copy(position);
        controls.target.copy(target);
        controls.update();
        return;
      }

      const timeline = gsap.timeline({ defaults: { duration: 1.7, ease: "power3.inOut" } });
      timeline.to(
        camera.position,
        { x: position.x, y: position.y, z: position.z, onUpdate: () => camera.updateMatrixWorld() },
        0
      );
      timeline.to(
        controls.target,
        { x: target.x, y: target.y, z: target.z, onUpdate: () => controls.update() },
        0
      );
    },
    { dependencies: [activeDepartment, departmentCentroids], revertOnUpdate: true }
  );

  return (
    <OrbitControls
      ref={controlsRef}
      enableDamping
      dampingFactor={0.08}
      minDistance={4}
      maxDistance={30}
      maxPolarAngle={Math.PI * 0.85}
    />
  );
}
