/** Flat layered-hills illustration used when no photo is available (design.md, section 7). */
export function Hills({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 800 260" preserveAspectRatio="xMidYMid slice" aria-hidden>
      <rect width="800" height="260" fill="#E6EAC9" />
      <circle cx="640" cy="70" r="34" fill="#F5F1B0" />
      <path d="M0 170 Q120 90 240 150 T480 130 T800 120 V260 H0Z" fill="#D8E5D6" />
      <path d="M0 200 Q160 130 320 190 T640 170 T800 180 V260 H0Z" fill="#A9BE8F" />
      <path d="M0 230 Q200 180 400 225 T800 215 V260 H0Z" fill="#5C7A43" />
    </svg>
  );
}
