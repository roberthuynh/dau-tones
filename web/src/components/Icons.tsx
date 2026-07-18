import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { title?: string };

function IconShell({ title, children, ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden={title ? undefined : true} role={title ? "img" : undefined} {...props}>
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}
export function MicIcon(props: IconProps) {
  return (
    <IconShell {...props}>
      <rect x="8" y="3" width="8" height="12" rx="4" stroke="currentColor" strokeWidth="1.8" />
      <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3M8.5 21h7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </IconShell>
  );
}

export function PlayIcon(props: IconProps) {
  return (
    <IconShell {...props}>
      <path d="m9 6 9 6-9 6V6Z" fill="currentColor" />
    </IconShell>
  );
}

export function PauseIcon(props: IconProps) {
  return (
    <IconShell {...props}>
      <path d="M8 6v12M16 6v12" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
    </IconShell>
  );
}

export function SparkIcon(props: IconProps) {
  return (
    <IconShell {...props}>
      <path d="M12 2.5c.6 5.7 3.1 8.3 8.4 9.3-5.3 1-7.8 3.6-8.4 9.3-.6-5.7-3.1-8.3-8.4-9.3 5.3-1 7.8-3.6 8.4-9.3Z" fill="currentColor" />
    </IconShell>
  );
}

export function ArrowIcon(props: IconProps) {
  return (
    <IconShell {...props}>
      <path d="M5 12h13M14 7l5 5-5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </IconShell>
  );
}

export function VolumeIcon(props: IconProps) {
  return (
    <IconShell {...props}>
      <path d="M4 10v4h4l5 4V6l-5 4H4Z" fill="currentColor" />
      <path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </IconShell>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <IconShell {...props}>
      <path d="m7 7 10 10M17 7 7 17" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </IconShell>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <IconShell {...props}>
      <path d="M12 3v12m0 0 4-4m-4 4-4-4M5 19h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </IconShell>
  );
}
