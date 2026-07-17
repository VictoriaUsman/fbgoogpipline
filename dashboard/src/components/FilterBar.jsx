import { PLATFORM_LABELS } from "../lib/format.js";

export function FilterBar({ platform, onChangePlatform, platforms }) {
  return (
    <div className="filter-bar">
      <button className={platform === "all" ? "active" : ""} onClick={() => onChangePlatform("all")}>
        All platforms
      </button>
      {platforms.map((p) => (
        <button key={p} className={platform === p ? "active" : ""} onClick={() => onChangePlatform(p)}>
          {PLATFORM_LABELS[p] ?? p}
        </button>
      ))}
    </div>
  );
}
