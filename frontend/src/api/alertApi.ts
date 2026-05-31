import { API_BASE_URL } from "./config";

export type AlertBannerAction =
  | "CONFIRM_LOCATION"
  | "OPEN_LOCATION_ADJUSTMENT"
  | string;

export type AlertBannerButton = {
  label: string;
  action: AlertBannerAction;
};

export type AlertBannerResponse = {
  user_id: number;
  show_banner: boolean;
  level: string;
  banner_title: string;
  banner_message: string;
  detected_location: string;
  buttons: AlertBannerButton[];
  next_api?: {
    confirm_location?: string;
  };
};

export async function getAlertBanner(
  userId = 1,
): Promise<AlertBannerResponse> {
  const path = "/alerts/banner";
  const query = new URLSearchParams({
    user_id: String(userId),
  });
  const url = `${API_BASE_URL}${path}?${query}`;
  const method = "GET";

  const response = await fetch(url, {
    method,
  });

  if (!response.ok) {
    const responseText = await response.text();

    console.error("Alert banner API request failed", {
      url,
      method,
      status: response.status,
      responseText,
    });

    throw new Error(`재난 알림 배너 API 요청 실패 (${response.status})`);
  }

  return await response.json();
}
