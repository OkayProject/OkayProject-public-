import { API_BASE_URL } from "./config";

export type NearbySheltersRequest = {
  latitude: number;
  longitude: number;
};

export type Shelter = {
  id: number;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  distance_m: number;
  walk_time_min: number;
  distance_source?: "kakao_walking" | "straight_line_fallback";
  straight_distance_m?: number;
  is_open: boolean;
  status_text: string;
  map_url: string;
  route_url?: string;
};

export type NearbySheltersResponse = {
  current_location: {
    latitude: number;
    longitude: number;
  };
  nearest_shelter: Shelter | null;
  shelters: Shelter[];
};

const testRequest: NearbySheltersRequest = {
  latitude: 37.5446,
  longitude: 126.9647,
};

export async function getNearbyShelters(
  request: NearbySheltersRequest = testRequest,
): Promise<NearbySheltersResponse> {
  const query = new URLSearchParams({
    latitude: String(request.latitude),
    longitude: String(request.longitude),
  });

  const response = await fetch(`${API_BASE_URL}/shelters/nearby?${query}`, {
    method: "GET",
  });

  if (!response.ok) {
    throw new Error("Nearby shelters API request failed");
  }

  return await response.json();
}
