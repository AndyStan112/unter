export interface Point {
  label?: string;
  lat: number;
  lon: number;
}
export interface Zone extends Point {
  name: string;
}
export type Role = 'passenger' | 'driver';
export interface Profile {
  id: string;
  name: string;
}
export interface Driver extends Profile {
  status: 'OFFLINE' | 'AVAILABLE' | 'OFFERED' | 'ON_TRIP';
  current_trip_id: string | null;
  position: Point | null;
  position_updated_at: string | null;
  zone: string | null;
}
export type TripStatus =
  'REQUESTED' | 'OFFERED' | 'ASSIGNED' | 'PICKED_UP' | 'COMPLETED' | 'CANCELLED' | 'UNMATCHED';
export interface Trip {
  id: string;
  rider_id: string;
  driver_id: string | null;
  zone: string;
  pickup: Point;
  dropoff: Point;
  status: TripStatus;
  price: number | null;
  surge_multiplier: number | null;
  driver_bonus?: number;
  incentive_id?: string | null;
  distance_meters?: number | null;
  duration_seconds?: number | null;
  distance_source?: string;
  pickup_label?: string | null;
  dropoff_label?: string | null;
  requested_at?: string;
}
export interface DriverOffer {
  offer: { id: string; expires_at: string; status: string };
  trip: Trip;
  estimated_price: number;
}
export interface RideSession {
  profiles: Partial<Record<Role, Profile>>;
  tripIds: Partial<Record<Role, string>>;
  role?: Role;
}

export interface RoadRoute {
  distance_meters: number;
  duration_seconds: number | null;
  source: 'road' | 'straight_line';
  geometry: Point[];
  steps: {
    instruction: string;
    distance_meters: number;
    duration_seconds: number;
    position: Point;
  }[];
  warning: string | null;
}
export interface RidePlan {
  route: RoadRoute;
  fare: number;
  surge_multiplier: number;
  currency: 'RON';
  payment_mode: 'mock';
}
export interface DriverEarnings {
  completed_trips: number;
  fares: number;
  bonuses: number;
  balance: number;
  today: number;
  currency: 'RON';
  mode: 'mock';
  entries: { trip_id: string; fare: number; bonus: number; total: number; settled_at: string }[];
}
