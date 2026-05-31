import { API_BASE_URL } from "./config";

export type RiskFactorsRequest = {
  user_id?: number;
  latitude: number;
  longitude: number;
  risk_location_type?: "current" | "home" | "residence";
  rainfall_total?: number;
  rain_1h_max?: number;
  rain_3h_max?: number;
  rain_6h_max?: number;
  rain_24h_max?: number;
};

export type RiskFactorItem = {
  factor: string;
  description: string;
};

export type RiskFactorsResponse = {
  level: string;
  color: string;
  title: string;
  ai_message: string;
  risk_score: number;
  rainfall_level: string;
  current_location: string;
  risk_factors: RiskFactorItem[];
  actions: string[];
  user_context: {
    has_disability: boolean;
    disability_type: string | null;
    is_mobility_vulnerable: boolean;
    is_semi_basement_resident: boolean;
  };
  ai_risk_level?: string;
  base_risk_level?: string;
  final_risk_level?: string;
  model_version?: string;
  data_version?: string;
  reasons?: string[];
  model_reasons?: string[];
  recommended_channels?: string[];
  stage3_danger_filter_score?: number | null;
  model_notice?: string;
  rainfall?: FloodRiskRainfall;
};

export type FloodRiskRainfallFeatures = {
  rainfall_total: number;
  rain_1h_max: number;
  rain_10m_max?: number;
  rain_3h_max?: number;
  rain_6h_max?: number;
  rain_24h_max?: number;
};

export type FloodRiskRainfall = {
  source: string;
  observed_at: string | null;
  raw_provider?: string | null;
  features: FloodRiskRainfallFeatures;
};

export type FloodRiskPredictResponse = {
  risk_score: number;
  relative_risk_score?: number;
  ai_risk_level?: string;
  base_risk_level?: string;
  final_risk_level: string;
  level?: string;
  risk_level?: string;
  stage1_score?: number;
  stage2_score?: number;
  stage3_danger_filter_score?: number | null;
  base_probability?: number;
  personalized_probability?: number;
  thresholds: {
    caution: number;
    danger?: number;
    danger_candidate?: number;
    emergency?: number;
    stage1_candidate?: number;
    stage3_danger_filter?: number;
  };
  reasons: string[];
  model_reasons?: string[];
  recommended_channels: string[];
  model_version: string;
  data_version?: string;
  model_note?: string;
  model_notice?: string;
  personalization?: {
    applied: boolean;
    included_in_model: boolean;
    applied_factors?: {
      is_basement?: boolean;
      is_mobility_limited?: boolean;
      has_visual_impairment?: boolean;
      has_disability?: boolean;
    };
    vulnerability_score?: number;
    score_adjustment?: number;
    base_score?: number;
    personalized_score?: number;
    emergency_guard_applied?: boolean;
    reasons?: string[];
    message: string;
  };
  stage_scores?: {
    p_positive: number;
    predicted_overlap: number;
  };
  rainfall?: FloodRiskRainfall;
};

const testRequest: RiskFactorsRequest = {
  latitude: 37.5446,
  longitude: 126.9647,
  risk_location_type: "current",
};

const FLOOD_RISK_PREDICT_PATH = "/api/flood-risk/predict";

export async function getRiskFactors(
  request: RiskFactorsRequest = testRequest,
): Promise<RiskFactorsResponse> {
  const path = FLOOD_RISK_PREDICT_PATH;
  const url = `${API_BASE_URL}${path}`;
  const method = "POST";
  let effectiveRequest = request;

  let response = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(effectiveRequest),
  });

  if (!response.ok && !hasRainfallInput(request)) {
    const fallbackRequest = withZeroRainfall(request);
    console.warn(
      "Risk factors API failed without rainfall fields; retrying with explicit zero rainfall",
      {
        url,
        method,
        status: response.status,
      },
    );
    response = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(fallbackRequest),
    });
    effectiveRequest = fallbackRequest;
  }

  if (!response.ok) {
    const responseText = await response.text();

    console.error("Risk factors API request failed", {
      url,
      method,
      body: effectiveRequest,
      status: response.status,
      responseText,
    });

    throw new Error(`위험 정보 API 요청 실패 (${response.status})`);
  }

  const data: FloodRiskPredictResponse = await response.json();
  return toRiskFactorsResponse(data, effectiveRequest);
}

function hasRainfallInput(request: RiskFactorsRequest): boolean {
  return [
    request.rainfall_total,
    request.rain_1h_max,
    request.rain_3h_max,
    request.rain_6h_max,
    request.rain_24h_max,
  ].some((value) => value !== undefined && value !== null);
}

function withZeroRainfall(request: RiskFactorsRequest): RiskFactorsRequest {
  return {
    ...request,
    rainfall_total: 0,
    rain_1h_max: 0,
    rain_3h_max: 0,
    rain_6h_max: 0,
    rain_24h_max: 0,
  };
}

function toRiskFactorsResponse(
  data: FloodRiskPredictResponse,
  request: RiskFactorsRequest,
): RiskFactorsResponse {
  const level = normalizeRiskLevel(
    data.final_risk_level ||
      data.base_risk_level ||
      data.level ||
      data.risk_level ||
      data.ai_risk_level,
  );
  const sourceReasons =
    Array.isArray(data.model_reasons) && data.model_reasons.length > 0
      ? data.model_reasons
      : data.reasons;
  const reasons =
    Array.isArray(sourceReasons) && sourceReasons.length > 0
      ? sourceReasons
      : ["현재 입력 기준으로 침수 위험도를 산출했습니다."];

  return {
    level,
    color: getColorByLevel(level),
    title: getTitleByLevel(level),
    ai_message: getMessageByLevel(level, reasons),
    risk_score: Math.round(data.risk_score * 100),
    rainfall_level: getRainfallSummary(data.rainfall?.features),
    current_location: `현재 위치 (${request.latitude.toFixed(4)}, ${request.longitude.toFixed(4)})`,
    risk_factors: reasons.map((reason) => ({
      factor: reason,
      description: `${reason} 요소가 현재 침수 위험 판단에 반영되었습니다.`,
    })),
    actions: getActionsByLevel(level),
    user_context: {
      has_disability: Boolean(
        data.personalization?.applied_factors?.has_disability,
      ),
      disability_type: null,
      is_mobility_vulnerable: Boolean(
        data.personalization?.applied_factors?.is_mobility_limited,
      ),
      is_semi_basement_resident: Boolean(
        data.personalization?.applied_factors?.is_basement,
      ),
    },
    ai_risk_level: data.ai_risk_level,
    base_risk_level: data.base_risk_level,
    final_risk_level: data.final_risk_level,
    model_version: data.model_version,
    data_version: data.data_version,
    reasons,
    model_reasons: data.model_reasons,
    recommended_channels: data.recommended_channels,
    stage3_danger_filter_score: data.stage3_danger_filter_score,
    model_notice: data.model_notice,
    rainfall: data.rainfall,
  };
}

function normalizeRiskLevel(level?: string): "안전" | "주의" | "위험" | "긴급" {
  const normalizedLevel = level?.trim().toLowerCase();

  if (normalizedLevel === "긴급" || normalizedLevel === "emergency") {
    return "긴급";
  }

  if (normalizedLevel === "위험" || normalizedLevel === "danger") {
    return "위험";
  }

  if (normalizedLevel === "주의" || normalizedLevel === "caution") {
    return "주의";
  }

  return "안전";
}

function getColorByLevel(level: string): string {
  if (level === "긴급") return "#FFCDD2";
  if (level === "위험") return "#FFE0B2";
  if (level === "주의") return "#FFF9C4";
  return "#E8F5E9";
}

function getTitleByLevel(level: string): string {
  if (level === "긴급") return "긴급 단계 · 공식 안내 확인";
  if (level === "위험") return "위험 단계 · 침수 위험 알림";
  if (level === "주의") return "주의 단계 · 호우 대비 알림";
  return "안전 단계 · 위험 신호 제한적";
}

function getMessageByLevel(level: string, reasons: string[]): string {
  const reasonText = reasons.join(", ");
  if (level === "긴급") {
    return `현재 위치에서 침수 위험이 높은 조건이 확인되었습니다. ${reasonText}. 지하 공간과 하천 주변을 피하고 공식 대피 안내를 확인하세요.`;
  }
  if (level === "위험") {
    return `현재 위치에서 침수 위험 조건이 확인되었습니다. ${reasonText}. 침수 취약 장소와 지하 공간을 피하고 이동 경로를 확인하세요.`;
  }
  if (level === "주의") {
    return `현재 위치에서 침수 가능성 신호가 일부 확인되었습니다. ${reasonText}. 기상 상황과 이동 경로를 확인하세요.`;
  }
  return `현재 입력 기준 높은 침수 위험 신호는 제한적입니다. ${reasonText}. 기상 변화는 계속 확인하세요.`;
}

function getActionsByLevel(level: string): string[] {
  if (level === "긴급") {
    return [
      "지하 공간에서 즉시 벗어나세요.",
      "하천 주변과 침수 도로 접근을 피하세요.",
      "가까운 대피소 또는 안전한 실내로 이동하세요.",
    ];
  }
  if (level === "위험") {
    return [
      "침수 취약 장소와 지하 공간 출입을 피하세요.",
      "가까운 대피소와 이동 경로를 확인하세요.",
      "추가 강수와 공식 안내를 확인하세요.",
    ];
  }
  if (level === "주의") {
    return [
      "현재 위치와 이동 경로를 확인하세요.",
      "기상 정보를 수시로 확인하세요.",
      "침수 취약 장소 방문을 피하세요.",
    ];
  }
  return [
    "기상 정보를 주기적으로 확인하세요.",
    "위치 권한과 알림 설정을 유지하세요.",
  ];
}

function getRainfallSummary(features?: FloodRiskRainfallFeatures): string {
  if (!features) return "확인 중";
  const rain3hMax = features.rain_3h_max ?? 0;
  if (features.rain_1h_max >= 50 || rain3hMax >= 90) return "매우 강함";
  if (features.rain_1h_max >= 30 || rain3hMax >= 60) return "강함";
  if (features.rainfall_total > 0) return "비";
  return "없음";
}

export type BackendConnectionTestResult = {
  ok: boolean;
  baseUrl: string;
  status?: number;
  message: string;
};

export async function testBackendConnection(
  request: RiskFactorsRequest = testRequest,
): Promise<BackendConnectionTestResult> {
  try {
    const response = await fetch(`${API_BASE_URL}${FLOOD_RISK_PREDICT_PATH}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    return {
      ok: response.ok,
      baseUrl: API_BASE_URL,
      status: response.status,
      message: response.ok
        ? "Backend connection test succeeded"
        : "Backend connection test failed",
    };
  } catch (error) {
    return {
      ok: false,
      baseUrl: API_BASE_URL,
      message:
        error instanceof Error
          ? error.message
          : "Backend connection test failed",
    };
  }
}
