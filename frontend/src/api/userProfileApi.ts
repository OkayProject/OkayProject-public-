import { API_BASE_URL } from "./config";

export type UserProfileFrequentPlaceRequest = {
  name: string;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
};

export type SaveUserProfileRequest = {
  user_id?: number | null;
  name: string;
  phone: string;
  address?: string | null;
  home_latitude?: number | null;
  home_longitude?: number | null;
  home_address?: string | null;
  frequent_places: UserProfileFrequentPlaceRequest[];
  has_disability: boolean;
  disability_type?: string | null;
  is_mobility_vulnerable: boolean;
  is_semi_basement_resident: boolean;
  notification_enabled: boolean;
  notification_methods: ("voice" | "vibration" | "flash")[];
};

export type SaveUserProfileResponse = {
  message: string;
  mode: "created" | "updated";
  user_id: number;
  user: Record<string, unknown>;
};

export async function saveUserProfile(
  request: SaveUserProfileRequest,
): Promise<SaveUserProfileResponse> {
  const path = "/users/profile";
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

    console.error("User profile API request failed", {
      url,
      method,
      body: request,
      status: response.status,
      responseText,
    });

    throw new Error(`User profile API request failed (${response.status})`);
  }

  return await response.json();
}
