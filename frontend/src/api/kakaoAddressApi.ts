import { API_BASE_URL } from "./config";

export type KakaoAddressResult = {
  name: string;
  addressName: string;
  roadAddressName: string;
  zoneNo: string;
  x: string;
  y: string;
  source: string;
};

type MapSearchResult = {
  name?: string | null;
  address?: string | null;
  road_address?: string | null;
  lat: number | string;
  lon: number | string;
  source?: string | null;
};

type MapSearchResponse = {
  results: MapSearchResult[];
};

export const searchKakaoAddresses = async (query: string) => {
  const trimmedQuery = query.trim();

  if (!trimmedQuery) {
    return [];
  }

  const response = await fetch(
    `${API_BASE_URL}/map/search?query=${encodeURIComponent(trimmedQuery)}`,
  );

  if (!response.ok) {
    throw new Error(`Map search failed: ${response.status}`);
  }

  const data = (await response.json()) as MapSearchResponse;
  const results = Array.isArray(data.results) ? data.results : [];

  return results.map((result) => ({
    name: result.name?.trim() ?? "",
    addressName: result.address?.trim() ?? "",
    roadAddressName: result.road_address?.trim() ?? "",
    zoneNo: "",
    x: String(result.lon),
    y: String(result.lat),
    source: result.source?.trim() ?? "",
  }));
};
