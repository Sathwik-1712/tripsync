import { useEffect } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { PlanView } from "../api";

export const DAY_COLORS = ["#1F2A1C", "#5C7A2E", "#8A5A00", "#2D4F6B", "#9B2C1F", "#6B5B95", "#3E7C74", "#7A4E2D"];

const pin = (label: string, bg: string, fg: string, faded = false, size = 28) =>
  L.divIcon({
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${bg};color:${fg};
      opacity:${faded ? 0.35 : 1};display:grid;place-items:center;font:600 12px Outfit,sans-serif;
      border:2px solid #fff;box-shadow:0 1px 3px rgba(31,42,28,.3)">${label}</div>`,
  });

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 1) map.fitBounds(points, { padding: [36, 36] });
  }, [map, points]);
  return null;
}

export function TripMap({ plan, selectedDay }: { plan: PlanView; selectedDay: number }) {
  const home: [number, number] = [plan.home.lat, plan.home.lon];
  const day = plan.days.find((d) => d.day === selectedDay);
  const focus: [number, number][] = [home, ...(day?.stops ?? []).map((s) => [s.lat, s.lon] as [number, number])];
  return (
    <MapContainer center={home} zoom={12} scrollWheelZoom={false} className="h-[480px] w-full" aria-label="Trip map">
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
      <FitBounds points={focus} />
      <Marker position={home} icon={pin("H", "#C2CB52", "#1F2A1C", false, 32)}>
        <Tooltip>{plan.home.name}</Tooltip>
      </Marker>
      {plan.days.map((d) => {
        const color = DAY_COLORS[(d.day - 1) % DAY_COLORS.length];
        const faded = d.day !== selectedDay;
        const line: [number, number][] = [home, ...d.stops.map((s) => [s.lat, s.lon] as [number, number])];
        return (
          <div key={d.day}>
            {line.length > 1 && <Polyline positions={line} pathOptions={{ color, weight: faded ? 2 : 4, opacity: faded ? 0.3 : 0.85 }} />}
            {d.stops.map((s, i) => (
              <Marker key={s.id} position={[s.lat, s.lon]} icon={pin(`${d.day}.${i + 1}`, color, "#F8F7F0", faded)}>
                <Tooltip>Day {d.day} · {s.name}</Tooltip>
              </Marker>
            ))}
          </div>
        );
      })}
    </MapContainer>
  );
}
