import { API_BASE_URL } from "./config";

export type LocationConfirmRequest = {
  user_id: number;
  is_current_location_correct: boolean;
  latitude: number;
  longitude: number;
};

export type LocationPosition = {
  latitude: number;
  longitude: number;
};

export type LocationConfirmResponse = {
  user_id: number;
  location_confirmed: boolean;
  message: string;
  next_action: string;
  confirmed_position: LocationPosition;
  detected_position?: LocationPosition;
};

const testRequest: LocationConfirmRequest = {
  user_id: 1,
  is_current_location_correct: true,
  latitude: 37.5446,
  longitude: 126.9647,
};

export async function confirmLocation(
  request: LocationConfirmRequest = testRequest,
): Promise<LocationConfirmResponse> {
  const path = "/location/confirm";
  const url = `${API_BASE_URL}${path}`;
  const method = "POST";

  const response = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const responseText = await response.text();

    console.error("Location confirm API request failed", {
      url,
      method,
      body: request,
      status: response.status,
      responseText,
    });

    throw new Error(`Location confirm API request failed (${response.status})`);
  }

  return await response.json();
}
