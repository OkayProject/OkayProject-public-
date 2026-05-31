import { API_BASE_URL } from "./config";

export type MissingReferenceImageStatus = "pending" | "completed" | "success" | "failed";

export type MissingReferenceImageResponse = {
  reference_image_url: string | null;
  status: MissingReferenceImageStatus;
  is_ai_generated: boolean;
  notice?: string;
  error_code?: string;
  message?: string;
};

const referenceImageCache = new Map<string, MissingReferenceImageResponse>();
const pendingReferenceImageRequests = new Map<string, Promise<MissingReferenceImageResponse>>();

export function getCachedMissingReferenceImage(
  missingPersonId: string,
): MissingReferenceImageResponse | null {
  return referenceImageCache.get(missingPersonId) ?? null;
}

export async function fetchMissingReferenceImage(
  missingPersonId: string,
): Promise<MissingReferenceImageResponse> {
  const cachedReferenceImage = referenceImageCache.get(missingPersonId);
  if (cachedReferenceImage) {
    return cachedReferenceImage;
  }

  const pendingRequest = pendingReferenceImageRequests.get(missingPersonId);
  if (pendingRequest) {
    return pendingRequest;
  }

  const url = `${API_BASE_URL}/missing-persons/${missingPersonId}/reference-image`;

  console.log("Missing reference image request", {
    missingPersonId,
    url,
  });

  const request = fetch(url, { method: "POST" })
    .then(async (response): Promise<MissingReferenceImageResponse> => {
      if (!response.ok) {
        return {
          reference_image_url: null,
          status: "failed",
          is_ai_generated: false,
          error_code: `HTTP_${response.status}`,
          message: "현재 참고 이미지를 불러올 수 없습니다.",
        };
      }

      // 백엔드 응답 필드명은 reference_image_url, status, is_ai_generated, notice를 기대합니다.
      const referenceImage: MissingReferenceImageResponse = await response.json();
      if (
        referenceImage.reference_image_url &&
        (referenceImage.status === "completed" || referenceImage.status === "success")
      ) {
        referenceImageCache.set(missingPersonId, referenceImage);
      }

      return referenceImage;
    })
    .finally(() => {
      pendingReferenceImageRequests.delete(missingPersonId);
    });

  pendingReferenceImageRequests.set(missingPersonId, request);
  return request;
}
