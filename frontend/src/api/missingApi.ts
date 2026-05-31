import { API_BASE_URL } from "./config";

export type MissingAlertClassifyRequest = {
  user_id?: number;
  latitude?: number;
  longitude?: number;
  limit?: number;
  max_distance_m?: number;
  frequent_places?: {
    name: string;
    address?: string;
    latitude: number;
    longitude: number;
  }[];
};

export type MissingReferenceLocation = {
  name?: string;
  source?: string;
  latitude?: number;
  longitude?: number;
  distance_m?: number;
};

export type MissingAlert = {
  id: number | string;
  stable_id?: string;
  data_source?: string;
  name?: string;
  age?: number | string;
  gender?: string;
  missing_person_category?: string;
  last_seen_location?: string;
  last_seen_latitude?: number;
  last_seen_longitude?: number;
  missing_time_hours?: number;
  appearance_description?: string;
  description?: string;
  report_summary?: string;
  relevance_score?: number;
  distance_m?: number | null;
  nearest_reference_location?: MissingReferenceLocation | null;
  should_notify?: boolean;
  alert_level?: string;
  alert_priority?: number;
  alert_message?: string;
  score_reason?: string;
};

export type MissingAlertClassifyResponse = {
  source: string;
  is_fallback: boolean;
  fallback_reason?: string | null;
  user_id?: number;
  current_location: {
    latitude: number;
    longitude: number;
  };
  reference_locations: MissingReferenceLocation[];
  count: number;
  notify_count: number;
  max_distance_m?: number | null;
  alerts: MissingAlert[];
  classification_method: string;
};

export async function classifyMissingAlerts(
  request: MissingAlertClassifyRequest,
): Promise<MissingAlertClassifyResponse> {
  const path = "/missing-alert/classify";
  const url = `${API_BASE_URL}${path}`;
  const method = "POST";
  const body = {
    limit: 3,
    ...request,
  };

  console.log("Missing alert request", body);

  const response = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const responseText = await response.text();

    console.error("Missing alert API request failed", {
      url,
      method,
      body,
      status: response.status,
      responseText,
    });

    throw new Error(`Missing alert API request failed (${response.status})`);
  }

  const json = await response.json();

  console.log("Missing alert response max_distance_m", json.max_distance_m);
  console.log(
    "Missing alert distances",
    json.alerts?.map((alert: MissingAlert) => ({
      name: alert.name,
      distance_m: alert.distance_m,
    })),
  );

  return json;
}
