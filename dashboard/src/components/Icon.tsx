import React from 'react';

const ICON_PATHS: Record<string, React.ReactNode> = {
  search:      <><circle cx="7" cy="7" r="5" /><path d="M11 11l3 3" /></>,
  dashboard:   <><rect x="2" y="2" width="5" height="6" rx="1"/><rect x="9" y="2" width="5" height="4" rx="1"/><rect x="2" y="10" width="5" height="4" rx="1"/><rect x="9" y="8" width="5" height="6" rx="1"/></>,
  pipeline:    <><circle cx="3.5" cy="8" r="1.5"/><circle cx="12.5" cy="8" r="1.5"/><path d="M5 8h6"/><path d="M8 5v6"/></>,
  shield:      <><path d="M8 1.5l5.5 2v4c0 3.5-2.5 6-5.5 7-3-1-5.5-3.5-5.5-7v-4l5.5-2z"/></>,
  alert:       <><path d="M8 1.5l6.5 12h-13L8 1.5z"/><path d="M8 6v3.5"/><circle cx="8" cy="11.6" r=".5" fill="currentColor" stroke="none"/></>,
  repo:        <><path d="M3 2h8a1 1 0 011 1v10a1 1 0 01-1 1H4a1 1 0 01-1-1V2z"/><path d="M3 11h9"/></>,
  chat:        <><path d="M2 4a2 2 0 012-2h8a2 2 0 012 2v6a2 2 0 01-2 2H7l-3 2v-2H4a2 2 0 01-2-2V4z"/></>,
  settings:    <><circle cx="8" cy="8" r="2"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M3.5 12.5l1.4-1.4M11.1 4.9l1.4-1.4"/></>,
  report:      <><path d="M3 2h7l3 3v9a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z"/><path d="M10 2v3h3"/><path d="M5 8h6M5 11h4"/></>,
  filter:      <><path d="M2 3h12l-4.5 5v5l-3 1V8L2 3z"/></>,
  plus:        <><path d="M8 3v10M3 8h10"/></>,
  arrow_right: <><path d="M3 8h10M9 4l4 4-4 4"/></>,
  chevron_right:<><path d="M6 3l4 5-4 5"/></>,
  chevron_down:<><path d="M3 6l5 4 5-4"/></>,
  external:    <><path d="M9 2h5v5"/><path d="M14 2L7 9"/><path d="M12 9v4a1 1 0 01-1 1H3a1 1 0 01-1-1V5a1 1 0 011-1h4"/></>,
  check:       <><path d="M3 8.5l3 3 7-7"/></>,
  x:           <><path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/></>,
  copy:        <><rect x="5" y="2" width="9" height="9" rx="1"/><path d="M11 11v2a1 1 0 01-1 1H3a1 1 0 01-1-1V6a1 1 0 011-1h2"/></>,
  refresh:     <><path d="M14 8a6 6 0 11-1.7-4.2"/><path d="M14 2v4h-4"/></>,
  send:        <><path d="M2 8l12-6-5 14-2-6-5-2z"/></>,
  attach:      <><path d="M11 7l-5 5a2 2 0 11-3-3l6-6a3 3 0 014 4l-6 6"/></>,
  branch:      <><circle cx="4" cy="3.5" r="1.5"/><circle cx="4" cy="12.5" r="1.5"/><circle cx="12" cy="6.5" r="1.5"/><path d="M4 5v6"/><path d="M4 8c0-2 1-3 4-3 1.5 0 3 .5 3-1"/></>,
  commit:      <><circle cx="8" cy="8" r="2.5"/><path d="M2 8h3.5M10.5 8H14"/></>,
  clock:       <><circle cx="8" cy="8" r="6"/><path d="M8 5v3l2 1.5"/></>,
  user:        <><circle cx="8" cy="6" r="2.5"/><path d="M3 14c0-2.5 2-4.5 5-4.5s5 2 5 4.5"/></>,
  bot:         <><rect x="3" y="5" width="10" height="8" rx="2"/><circle cx="6.5" cy="9" r=".7" fill="currentColor"/><circle cx="9.5" cy="9" r=".7" fill="currentColor"/><path d="M8 3v2"/></>,
  sparkle:     <><path d="M8 2l1.2 4 4 1.2-4 1.2L8 12.4 6.8 8.4l-4-1.2 4-1.2L8 2z"/></>,
  play:        <><path d="M4 3l9 5-9 5z" fill="currentColor"/></>,
  bell:        <><path d="M4 11V7a4 4 0 118 0v4l1 2H3l1-2z"/><path d="M7 14a1 1 0 002 0"/></>,
  github:      <path d="M8 1.5C4.4 1.5 1.5 4.4 1.5 8c0 2.9 1.9 5.3 4.4 6.2.3.1.4-.1.4-.3v-1.1c-1.8.4-2.2-.9-2.2-.9-.3-.7-.7-.9-.7-.9-.6-.4 0-.4 0-.4.6 0 1 .7 1 .7.6 1 1.5.7 1.9.6 0-.4.2-.7.4-.9-1.4-.2-2.9-.7-2.9-3.2 0-.7.3-1.3.7-1.7 0-.2-.3-.9.1-1.8 0 0 .6-.2 1.8.7.5-.1 1-.2 1.6-.2s1 .1 1.6.2c1.2-.8 1.8-.7 1.8-.7.4.9.1 1.6.1 1.8.4.4.7 1 .7 1.7 0 2.5-1.5 3-2.9 3.2.2.2.4.6.4 1.2v1.7c0 .2.1.4.5.3 2.5-.9 4.4-3.3 4.4-6.2 0-3.6-2.9-6.5-6.5-6.5z" fill="currentColor" stroke="none"/>,
  fix:         <><path d="M11.5 2.5l2 2-7 7-2.5.5.5-2.5 7-7z"/><path d="M9.5 4.5l2 2"/></>,
  more:        <><circle cx="3" cy="8" r="1" fill="currentColor"/><circle cx="8" cy="8" r="1" fill="currentColor"/><circle cx="13" cy="8" r="1" fill="currentColor"/></>,
  download:    <><path d="M8 2v8M5 7l3 3 3-3"/><path d="M2 13h12"/></>,
  link:        <><path d="M7 9a2.5 2.5 0 003.5 0L13 6.5a2.5 2.5 0 00-3.5-3.5L8 4.5"/><path d="M9 7a2.5 2.5 0 00-3.5 0L3 9.5a2.5 2.5 0 003.5 3.5L8 11.5"/></>,
  flag:        <><path d="M3 14V2"/><path d="M3 2h9l-2 3 2 3H3"/></>,
  rerun:       <><path d="M2 8a6 6 0 1010-4.5"/><path d="M14 2v4h-4"/><path d="M7 6l3 2-3 2z" fill="currentColor"/></>,
  mute:        <><path d="M2 6h3l4-3v10l-4-3H2z"/><path d="M11 6l3 4M14 6l-3 4"/></>,
  diff:        <><path d="M5 2v9"/><path d="M3 4h4"/><path d="M3 9h4"/><path d="M11 5v9"/><path d="M9 12h4"/></>,
  // DAST-specific
  globe:       <><circle cx="8" cy="8" r="6"/><path d="M2 8h12"/><path d="M8 2c2 2 3 4 3 6s-1 4-3 6"/><path d="M8 2c-2 2-3 4-3 6s1 4 3 6"/></>,
  target:      <><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="3"/><circle cx="8" cy="8" r=".8" fill="currentColor"/></>,
  zap:         <><path d="M9 1L3 9h4l-1 6 6-8H8l1-6z" fill="currentColor" stroke="none"/></>,
  key:         <><circle cx="5" cy="11" r="2.5"/><path d="M7 9l6-6"/><path d="M11 5l1.5 1.5"/><path d="M9 7l1.5 1.5"/></>,
  cookie:      <><path d="M8 1.5a6.5 6.5 0 106.5 6.5c-1.5 0-2.5-1-2.5-2.5 0-1-1-2-2-2 0-1.5-1-2-2-2z"/><circle cx="6" cy="7" r=".5" fill="currentColor"/><circle cx="9.5" cy="10" r=".5" fill="currentColor"/><circle cx="11" cy="6" r=".5" fill="currentColor"/></>,
  http:        <><path d="M2 6h12M2 10h12"/><path d="M5 4v8M11 4v8"/></>,
  schedule:    <><rect x="2" y="3" width="12" height="11" rx="1.5"/><path d="M2 6h12"/><path d="M5 1.5v3M11 1.5v3"/></>,
  api:         <><rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M5 7l1 1-1 1M9 7h2M9 9h2"/></>,
  pause:       <><rect x="4" y="3" width="3" height="10" rx="1" fill="currentColor"/><rect x="9" y="3" width="3" height="10" rx="1" fill="currentColor"/></>,
  stop:        <><rect x="3" y="3" width="10" height="10" rx="1.5" fill="currentColor"/></>,
  spider:      <><circle cx="8" cy="8" r="2.5"/><path d="M8 5.5V2M8 10.5V14M5.5 8H2M10.5 8H14M6 6L3 3M10 10l3 3M6 10l-3 3M10 6l3-3"/></>,
  link_off:    <><path d="M7 9a2.5 2.5 0 003.5 0L11 8.5"/><path d="M9 7a2.5 2.5 0 00-3.5 0L5 7.5"/><path d="M2 2l12 12"/></>,
  graph:       <><path d="M2 14l4-5 3 2 5-7"/><circle cx="2" cy="14" r="1" fill="currentColor"/><circle cx="6" cy="9" r="1" fill="currentColor"/><circle cx="9" cy="11" r="1" fill="currentColor"/><circle cx="14" cy="4" r="1" fill="currentColor"/></>,
  layers:      <><path d="M8 2L2 5l6 3 6-3-6-3z"/><path d="M2 8l6 3 6-3"/><path d="M2 11l6 3 6-3"/></>,
  // SCA / Secrets / Governance / AI advanced
  package:     <><path d="M8 2L2 5v6l6 3 6-3V5L8 2z"/><path d="M2 5l6 3 6-3"/><path d="M8 8v6"/></>,
  license:     <><path d="M3 2h7l3 3v9a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z"/><path d="M10 2v3h3"/><circle cx="6" cy="9" r="1.5"/><path d="M5 11.5l1 1.5 2-3"/></>,
  upgrade:     <><path d="M8 2v9M5 5l3-3 3 3"/><rect x="2" y="12" width="12" height="2" rx="1"/></>,
  secret:      <><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5 7V5a3 3 0 016 0v2"/><circle cx="8" cy="10.5" r=".8" fill="currentColor"/></>,
  history:     <><circle cx="8" cy="8" r="6"/><path d="M8 4v4l2.5 1.5"/><path d="M2.5 5.5l-1.5-1"/></>,
  vault:       <><rect x="2" y="3" width="12" height="10" rx="1.5"/><circle cx="8" cy="8" r="2.5"/><path d="M8 5.5V8M8 11v-1"/></>,
  bot_pr:      <><circle cx="4" cy="4" r="1.5"/><circle cx="4" cy="12" r="1.5"/><circle cx="12" cy="8" r="1.5"/><path d="M4 5.5v5"/><path d="M5.5 4h2a3 3 0 013 3v0"/></>,
  ide:         <><rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M2 6h12"/><path d="M5 9l1.5 1.5L5 12M8 12h3"/></>,
  shield_user: <><path d="M8 1.5l5.5 2v4c0 3.5-2.5 6-5.5 7-3-1-5.5-3.5-5.5-7v-4l5.5-2z"/><circle cx="8" cy="7" r="1.5"/><path d="M5.5 11c.5-1.5 1.5-2 2.5-2s2 .5 2.5 2"/></>,
  audit:       <><rect x="3" y="2" width="10" height="12" rx="1"/><path d="M5 5h6M5 8h6M5 11h4"/></>,
  brain:       <><path d="M5.5 3.5a2.5 2.5 0 00-2 4 2.5 2.5 0 001 4 2 2 0 003 .5V4a2 2 0 00-2-.5z"/><path d="M10.5 3.5a2.5 2.5 0 012 4 2.5 2.5 0 01-1 4 2 2 0 01-3 .5V4a2 2 0 012-.5z"/></>,
  triage:      <><path d="M2 4h12"/><path d="M4 8h8"/><path d="M6 12h4"/><circle cx="13" cy="12" r="1.5"/></>,
  threat:      <><path d="M3 5l5-3 5 3v4c0 3-2 5-5 6-3-1-5-3-5-6V5z"/><path d="M6 8l1.5 1.5L10 7"/></>,
  graphql:     <><circle cx="8" cy="8" r=".8" fill="currentColor"/><circle cx="8" cy="2.5" r="1" fill="currentColor"/><circle cx="13" cy="5.5" r="1" fill="currentColor"/><circle cx="13" cy="10.5" r="1" fill="currentColor"/><circle cx="8" cy="13.5" r="1" fill="currentColor"/><circle cx="3" cy="10.5" r="1" fill="currentColor"/><circle cx="3" cy="5.5" r="1" fill="currentColor"/><path d="M8 3.3l4.3 2.5v4.4L8 12.7l-4.3-2.5V5.8z"/></>,
};

interface IconProps {
  name: string;
  size?: number;
  stroke?: number;
  style?: React.CSSProperties;
  className?: string;
  title?: string;
}

export function Icon({ name, size = 16, stroke = 1.5, style, className, title }: IconProps) {
  const path = ICON_PATHS[name];
  if (!path) return <svg width={size} height={size} style={style} className={className} />;
  return (
    <svg
      width={size} height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={style}
      className={className}
    >
      {title && <title>{title}</title>}
      {path}
    </svg>
  );
}
