export interface Point {
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
