// אייקוני SVG קוויים — זהות ויזואלית נקייה במקום אימוג'ים
import type { SVGProps } from "react";

function Base({ children, size = 20, ...rest }: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"
         aria-hidden="true" {...rest}>
      {children}
    </svg>
  );
}

export function IconPrinter(props: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <Base {...props}>
      <path d="M6 9V3h12v6" />
      <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
      <rect x="6" y="14" width="12" height="8" rx="1" />
    </Base>
  );
}

export function IconCube(props: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <Base {...props}>
      <path d="M21 8v8a2 2 0 0 1-1 1.73l-7 4a2 2 0 0 1-2 0l-7-4A2 2 0 0 1 3 16V8a2 2 0 0 1 1-1.73l7-4a2 2 0 0 1 2 0l7 4A2 2 0 0 1 21 8Z" />
      <path d="M3.3 7 12 12l8.7-5" />
      <path d="M12 22V12" />
    </Base>
  );
}

export function IconImage(props: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <Base {...props}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="9" cy="9" r="2" />
      <path d="m21 15-3.5-3.5a2 2 0 0 0-2.83 0L6 20" />
    </Base>
  );
}

export function IconUpload(props: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <Base {...props}>
      <path d="M12 3v12" />
      <path d="m7 8 5-5 5 5" />
      <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </Base>
  );
}

export function IconLayers(props: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <Base {...props}>
      <path d="m12 2 9 4.5-9 4.5-9-4.5L12 2Z" />
      <path d="m3 12 9 4.5 9-4.5" />
      <path d="m3 17 9 4.5 9-4.5" />
    </Base>
  );
}
