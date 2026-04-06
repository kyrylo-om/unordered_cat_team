import { useCallback, useState } from "react";
import { DetailsPanel } from "../components/DetailsPanel";
import { LogoutButton } from "../components/LogoutButton";
import { MainContent } from "../components/MainContent";
import { StoreView } from "./StoreView";
import { useAuth } from "../context/useAuth";
import "../styles/MainPage.css";

function resolveRole(user) {
  const value =
    user?.role ||
    user?.user_type ||
    user?.userType ||
    user?.accountType ||
    user?.type ||
    "";
  const role = String(value).toLowerCase();

  if (role.includes("warehouse")) {
    return "warehouse";
  }

  if (role.includes("shop")) {
    return "shop";
  }

  return "warehouse";
}

function normalizeEventEntry(payload) {
  const timestampValue = payload?.at || payload?.timestamp || null;
  const date = timestampValue ? new Date(timestampValue) : new Date();
  const safeDate = Number.isNaN(date.getTime()) ? new Date() : date;

  const shipment = payload?.shipment || {};
  const defaultMessage = shipment?.fromLabel && shipment?.toLabel
    ? `Truck departed: ${shipment.fromLabel} -> ${shipment.toLabel}`
    : "Truck departed";

  return {
    id: `${Date.now()}-${Math.random()}`,
    message: payload?.message || defaultMessage,
    tick: Number.isFinite(Number(payload?.tick)) ? Number(payload.tick) : null,
    amount: Number.isFinite(Number(shipment?.amount)) ? Number(shipment.amount) : null,
    fromLabel: shipment?.fromLabel || "Unknown",
    toLabel: shipment?.toLabel || "Unknown",
    edgeId: shipment?.edgeId || "",
    at: safeDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
  };
}

export function MainPage() {
  const { user } = useAuth();
  const role = resolveRole(user);
  const [eventLogs, setEventLogs] = useState([]);
  const [currentTick, setCurrentTick] = useState(null);
  const [selectedElement, setSelectedElement] = useState(null);

  const handleEventLog = useCallback((payload) => {
    const payloadTick = Number(payload?.tick);
    if (Number.isFinite(payloadTick)) {
      setCurrentTick(payloadTick);
    }

    if (!payload || payload.event !== "truck_departure") {
      return;
    }

    const entry = normalizeEventEntry(payload);
    setEventLogs((previous) => [entry, ...previous].slice(0, 120));
  }, []);

  const handleTick = useCallback((payload) => {
    const tickValue = Number(payload?.tick);
    if (!Number.isFinite(tickValue)) {
      return;
    }

    setCurrentTick(tickValue);
  }, []);

  const handleElementSelect = useCallback((element) => {
    if (!element) {
      setSelectedElement(null);
      return;
    }

    setSelectedElement(element);
  }, []);

  const handleElementPatch = useCallback((patch) => {
    if (!patch) {
      return;
    }

    setSelectedElement((current) => {
      if (!current) {
        return current;
      }

      if (current.kind !== patch.kind || current.id !== patch.id) {
        return current;
      }

      return {
        ...current,
        data: {
          ...(current.data || {}),
          ...(patch.data || {}),
        },
      };
    });
  }, []);

  if (role === "shop") {
    return (
      <div className="main-page store-layout">
        <header className="app-header">
          <h1>Transportation Management System</h1>
          <LogoutButton />
        </header>

        <main className="store-main-area">
          <StoreView />
        </main>
      </div>
    );
  }

  return (
    <div className="main-page">
      <header className="app-header">
        <h1>Transportation Management System</h1>
        <LogoutButton />
      </header>

      <div className="app-layout">
        <aside className="left-sidebar">
          <div className="sidebar-placeholder">
            <div className="tick-counter" aria-live="polite">
              <span className="tick-counter-label">Current Tick</span>
              <strong className="tick-counter-value">
                {currentTick !== null ? currentTick : "--"}
              </strong>
            </div>
            <h3>Event Panel</h3>
            {eventLogs.length === 0 ? (
              <p>No redistribution events yet</p>
            ) : (
              <ul className="event-log-list">
                {eventLogs.map((event) => (
                  <li key={event.id} className="event-log-item">
                    <div className="event-log-meta">
                      <span>{event.at}</span>
                      {event.tick !== null ? <span>tick {event.tick}</span> : null}
                    </div>
                    <p>{event.message}</p>
                    {event.amount !== null ? (
                      <small>
                        {event.fromLabel}
                        {" -> "}
                        {event.toLabel}
                        {" | qty: "}
                        {event.amount}
                      </small>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        <main className="main-area">
          <MainContent
            onEventLog={handleEventLog}
            onTick={handleTick}
            onElementSelect={handleElementSelect}
            onElementPatch={handleElementPatch}
          />
        </main>

        <aside className="right-sidebar">
          <DetailsPanel
            selectedElement={selectedElement}
            onSelectionChange={setSelectedElement}
          />
        </aside>
      </div>
    </div>
  );
}
