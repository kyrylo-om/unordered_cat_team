import { Dashboard } from "../pages/Dashboard";

export function MainContent({ onEventLog, onTick, onElementSelect, onElementPatch }) {
  return (
    <div className="main-content">
      <Dashboard
        onEventLog={onEventLog}
        onTick={onTick}
        onElementSelect={onElementSelect}
        onElementPatch={onElementPatch}
      />
    </div>
  );
}
