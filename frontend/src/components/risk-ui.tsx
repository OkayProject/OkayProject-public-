import {
  type ComponentProps,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ActivityIndicator,
  AppState,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import * as Location from "expo-location";
import { useLocalSearchParams, useRouter } from "expo-router";

import {
  getAlertBanner,
  type AlertBannerResponse,
  type AlertBannerButton,
} from "../api/alertApi";
import { confirmLocation } from "../api/locationApi";
import {
  getRiskFactors,
  type RiskFactorsRequest,
  type RiskFactorsResponse,
} from "../api/riskApi";
import { colors, radius, spacing, typography } from "../constants/theme";
import {
  useRiskAlertFeedback,
  type RiskAlertLevel,
} from "../hooks/useRiskAlertFeedback";
import { showInAppNotificationFromContent } from "../notifications/inAppNotification";
import { loadSavedUserId } from "../storage/userProfile";
import {
  AppHeader,
  AppScreen,
  BottomTabs,
  Card,
  Divider,
  HeaderActions,
  TabSceneTransition,
} from "./okay-ui";

type RiskLevel = "safe" | "caution" | "danger" | "emergency";

type GuideIcon = ComponentProps<typeof MaterialCommunityIcons>["name"];
type NoticeIcon = ComponentProps<typeof Ionicons>["name"];

const RISK_REFRESH_INTERVAL_MS = 8000;
const RISK_REFRESH_AFTER_RESUME_DELAY_MS = 1000;
const LAST_KNOWN_LOCATION_MAX_AGE_MS = 5 * 60 * 1000;
const locationBannerShownKeys = new Set<string>();

const riskConfig: Record<
  RiskLevel,
  {
    label: string;
    color: string;
    guideTitle: string;
    guideBg: string;
    line: string;
    reasons: [string, string];
    actions?: [GuideIcon, string][];
  }
> = {
  safe: {
    label: "안전",
    color: "#61B95A",
    guideTitle: "사전 대비 행동 안내",
    guideBg: "rgba(97, 185, 90, 0.18)",
    line: "rgba(97, 185, 90, 0.28)",
    reasons: [
      "현재 위치 주변에 감지된 재난 위험이 없습니다.",
      "현재는 안전 단계이지만, 기상 변화에 따라 위험 단계가 달라질 수 있습니다.",
    ],
  },
  caution: {
    label: "주의",
    color: colors.caution,
    guideTitle: "사전 대비 행동 안내",
    guideBg: colors.cautionBox,
    line: colors.cautionBoxLine,
    reasons: [
      "현재 입력 기준으로 침수 가능성 신호가 일부 확인되었습니다.",
      "기상 변화에 따라 위험 단계가 달라질 수 있습니다.",
    ],
    actions: [
      ["weather-sunny", "기상 상황을 자주 확인하세요."],
      ["map-marker-path", "가까운 대피소를 미리 알아두세요."],
      ["waves", "하천과 침수 취약 장소 접근을 피하세요."],
    ],
  },
  danger: {
    label: "위험",
    color: colors.danger,
    guideTitle: "행동 요령 안내",
    guideBg: colors.dangerBox,
    line: colors.dangerBoxLine,
    reasons: [
      "현재 입력 기준으로 침수 위험 조건이 확인되었습니다.",
      "공식 안내와 주변 상황을 함께 확인하세요.",
    ],
    actions: [
      ["road-variant", "가까운 대피소와 이동 경로를 바로 확인하세요"],
      ["briefcase-outline", "필수품을 챙기고 즉시 이동할 수 있도록 준비하세요"],
      [
        "water-off",
        "하천과 침수 취약 장소 접근을 피하고, 필요 시 바로 대피하세요.",
      ],
    ],
  },
  emergency: {
    label: "긴급",
    color: colors.emergency,
    guideTitle: "행동 강령 안내",
    guideBg: colors.emergencyBox,
    line: colors.emergencyBoxLine,
    reasons: [
      "현재 강수량이 급증해 침수 위험이 매우 높아요.",
      "앞으로 무릎 높이까지 물이 찰 수 있는 강한 비가 예상돼요.",
    ],
    actions: [
      [
        "run-fast",
        "공식 재난 안내를 확인하고 안전한 장소로 이동을 준비하세요.",
      ],
      [
        "account-group-outline",
        "이동이 어렵다면 주변 또는 119에 도움을 요청하세요.",
      ],
    ],
  },
};

export function DisasterRiskScreen({ level }: { level: RiskLevel }) {
  const router = useRouter();
  const lastObservedLevelRef = useRef<RiskLevel | null>(null);
  const lastBackendLevelRef = useRef<RiskLevel | null>(null);
  const riskRefreshInFlightRef = useRef(false);
  const { playRiskAlertFeedback, flashPreview } = useRiskAlertFeedback();
  const params = useLocalSearchParams<{
    latitude?: string;
    longitude?: string;
  }>();
  const { height } = useWindowDimensions();
  const [riskData, setRiskData] = useState<RiskFactorsResponse | null>(null);
  const [bannerData, setBannerData] = useState<AlertBannerResponse | null>(
    null,
  );
  const [riskRequest, setRiskRequest] = useState<RiskFactorsRequest | null>(
    null,
  );
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [currentUserIdLoaded, setCurrentUserIdLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmingLocation, setConfirmingLocation] = useState(false);
  const compact = height < 760;
  const displayLevel = useMemo(
    () => toRiskLevel(riskData?.level) ?? level,
    [level, riskData?.level],
  );
  const isEmergency = displayLevel === "emergency";
  const shouldCheckLocationBanner =
    !loading && !error && isLocationConfirmationLevel(displayLevel);

  const buildCurrentLocationRiskRequest = useCallback(
    async (
      accuracy: Location.Accuracy = Location.Accuracy.Balanced,
    ): Promise<RiskFactorsRequest> => {
      let { status } = await Location.getForegroundPermissionsAsync();

      if (status !== Location.PermissionStatus.GRANTED) {
        const requestedPermission =
          await Location.requestForegroundPermissionsAsync();
        status = requestedPermission.status;
      }

      if (status !== Location.PermissionStatus.GRANTED) {
        throw new Error("Location permission is not granted");
      }
      const lastKnownPosition =
        accuracy === Location.Accuracy.High
          ? null
          : await Location.getLastKnownPositionAsync({
              maxAge: LAST_KNOWN_LOCATION_MAX_AGE_MS,
              requiredAccuracy: 200,
            });
      const position =
        lastKnownPosition ??
        (await Location.getCurrentPositionAsync({
          accuracy,
        }));

      return {
        ...(currentUserId ? { user_id: currentUserId } : {}),
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        risk_location_type: "current",
      };
    },
    [currentUserId],
  );

  useEffect(() => {
    let mounted = true;

    async function loadCurrentUserId() {
      const savedUserId = await loadSavedUserId();
      if (mounted) {
        setCurrentUserId(savedUserId);
        setCurrentUserIdLoaded(true);
      }
    }

    loadCurrentUserId();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (loading || error) {
      return;
    }

    const previousLevel = lastObservedLevelRef.current;

    if (previousLevel === displayLevel) {
      return;
    }

    lastObservedLevelRef.current = displayLevel;

    if (displayLevel === "safe") {
      return;
    }

    void playRiskAlertFeedback(displayLevel as RiskAlertLevel);
  }, [displayLevel, error, loading, playRiskAlertFeedback]);

  useEffect(() => {
    if (!currentUserIdLoaded) {
      return;
    }

    let mounted = true;

    async function buildRiskRequest(): Promise<RiskFactorsRequest> {
      const routeLatitude = Number(params.latitude);
      const routeLongitude = Number(params.longitude);

      if (Number.isFinite(routeLatitude) && Number.isFinite(routeLongitude)) {
        return {
          ...(currentUserId ? { user_id: currentUserId } : {}),
          latitude: routeLatitude,
          longitude: routeLongitude,
          risk_location_type: "current",
        };
      }

      return await buildCurrentLocationRiskRequest();
    }

    async function fetchRiskFactors() {
      try {
        setLoading(true);
        setError("");

        const request = await buildRiskRequest();

        if (mounted) {
          setRiskRequest(request);
        }

        const data = await getRiskFactors(request);

        if (mounted) {
          setRiskData(data);
        }
      } catch (fetchError) {
        console.error("POST /api/flood-risk/predict failed", fetchError);

        if (mounted) {
          setError("현재 위치를 기준으로 위험 정보를 불러오지 못했습니다.");
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    fetchRiskFactors();

    return () => {
      mounted = false;
    };
  }, [
    buildCurrentLocationRiskRequest,
    currentUserId,
    params.latitude,
    params.longitude,
  ]);

  useEffect(() => {
    if (!riskRequest) {
      return;
    }

    let mounted = true;
    const request = riskRequest;
    let resumeTimeoutId: ReturnType<typeof setTimeout> | null = null;

    async function refreshRiskFactors() {
      if (
        !mounted ||
        AppState.currentState !== "active" ||
        riskRefreshInFlightRef.current
      ) {
        return;
      }

      riskRefreshInFlightRef.current = true;

      try {
        const data = await getRiskFactors(request);

        if (mounted) {
          setRiskData(data);
          setError("");
          setLoading(false);
        }
      } catch {
        // Keep the previous risk data during transient app resume failures.
      } finally {
        riskRefreshInFlightRef.current = false;
      }
    }

    function refreshAfterResume() {
      if (resumeTimeoutId) {
        clearTimeout(resumeTimeoutId);
      }

      resumeTimeoutId = setTimeout(
        refreshRiskFactors,
        RISK_REFRESH_AFTER_RESUME_DELAY_MS,
      );
    }

    void refreshRiskFactors();

    const intervalId = setInterval(
      refreshRiskFactors,
      RISK_REFRESH_INTERVAL_MS,
    );
    const appStateSubscription = AppState.addEventListener(
      "change",
      (nextState) => {
        if (nextState === "active") {
          refreshAfterResume();
        }
      },
    );

    return () => {
      mounted = false;
      clearInterval(intervalId);
      if (resumeTimeoutId) {
        clearTimeout(resumeTimeoutId);
      }
      appStateSubscription.remove();
    };
  }, [riskRequest]);

  useEffect(() => {
    const currentLevel = toRiskLevel(riskData?.level);
    if (!currentLevel) {
      return;
    }

    if (lastBackendLevelRef.current === null) {
      lastBackendLevelRef.current = currentLevel;
      return;
    }

    if (lastBackendLevelRef.current === currentLevel) {
      return;
    }

    lastBackendLevelRef.current = currentLevel;

    if (currentLevel === "safe") {
      return;
    }

    void showInAppNotificationFromContent({
      title: getInAppBannerTitle(currentLevel),
      body:
        riskData?.ai_message ||
        "백엔드 위험 단계가 변경되어 현재 상태를 다시 확인해 주세요.",
      data: {
        id: `flood-${currentUserId ?? "anonymous"}-${Date.now()}`,
        type: "flood",
        risk_level: toNotificationRiskLevel(currentLevel),
        meta: riskData?.current_location ?? "",
        created_at: new Date().toISOString(),
      },
    });
  }, [currentUserId, riskData]);

  useEffect(() => {
    let mounted = true;

    async function fetchAlertBanner() {
      if (!currentUserId) {
        if (mounted) {
          setBannerData(null);
        }
        return;
      }

      try {
        const data = await getAlertBanner(currentUserId);
        const bannerLevel = toRiskLevel(data.level) ?? displayLevel;
        const bannerKey = getLocationBannerKey(data, bannerLevel);

        if (
          mounted &&
          data.show_banner &&
          isLocationConfirmationLevel(bannerLevel) &&
          !locationBannerShownKeys.has(bannerKey)
        ) {
          locationBannerShownKeys.add(bannerKey);
          setBannerData(data);
        } else if (mounted) {
          setBannerData(null);
        }
      } catch (fetchError) {
        console.error("GET /alerts/banner failed", fetchError);
      }
    }

    if (shouldCheckLocationBanner && currentUserId) {
      fetchAlertBanner();
    } else {
      setBannerData(null);
    }

    return () => {
      mounted = false;
    };
  }, [currentUserId, displayLevel, shouldCheckLocationBanner]);

  async function handleBannerAction(button: AlertBannerButton) {
    if (button.action === "CONFIRM_LOCATION") {
      if (!riskRequest || !currentUserId) {
        return;
      }

      try {
        setConfirmingLocation(true);
        await confirmLocation({
          ...riskRequest,
          user_id: currentUserId,
          is_current_location_correct: true,
        });
        setBannerData((current) =>
          current ? { ...current, show_banner: false } : current,
        );
      } catch (confirmError) {
        console.error("POST /location/confirm failed", confirmError);
      } finally {
        setConfirmingLocation(false);
      }

      return;
    }

    if (button.action === "OPEN_LOCATION_ADJUSTMENT") {
      try {
        setConfirmingLocation(true);
        setBannerData(null);
        setLoading(true);
        setError("");

        const request = await buildCurrentLocationRiskRequest(
          Location.Accuracy.High,
        );
        setRiskRequest(request);

        const data = await getRiskFactors(request);
        setRiskData(data);
      } catch (locationError) {
        console.error("Failed to refresh current location", locationError);
        setError(
          "현재 위치를 다시 확인하지 못했습니다. 위치 권한과 GPS 설정을 확인해 주세요.",
        );
      } finally {
        setLoading(false);
        setConfirmingLocation(false);
      }
    }
  }

  function handleEmergencyCall() {
    Linking.openURL("tel:119").catch((callError) => {
      console.error("Failed to open phone app", callError);
    });
  }

  function openShelterRoute() {
    if (riskRequest) {
      router.push(
        `/shelter-route?latitude=${riskRequest.latitude}&longitude=${riskRequest.longitude}` as never,
      );
      return;
    }

    router.push("/shelter-route" as never);
  }

  return (
    <AppScreen contentStyle={styles.screen}>
      {flashPreview}
      <TabSceneTransition active="disaster">
        <AppHeader
          title="재난 정보"
          left={
            displayLevel !== "safe" ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="119 전화 앱 열기"
                onPress={handleEmergencyCall}
                style={({ pressed }) => [
                  styles.emergencyCallButton,
                  pressed && styles.pressed,
                ]}
              >
                <Ionicons name="call-outline" size={31} color={colors.text} />
              </Pressable>
            ) : null
          }
          right={<HeaderActions />}
        />
        <View style={styles.contentFrame}>
          {bannerData?.show_banner ? (
            <View style={styles.bannerOverlay}>
              <AlertBanner
                data={bannerData}
                disabled={confirmingLocation}
                onActionPress={handleBannerAction}
              />
            </View>
          ) : null}

          <ScrollView
            bounces={false}
            showsVerticalScrollIndicator={false}
            contentContainerStyle={styles.body}
          >
            {loading ? (
              <StatusCard compact={compact} type="loading" />
            ) : error ? (
              <StatusCard compact={compact} type="error" message={error} />
            ) : (
              <RiskSummary
                level={displayLevel}
                compact={compact}
                data={riskData}
              />
            )}

            {!loading && !error && isEmergency ? (
              <Pressable
                accessibilityRole="button"
                onPress={openShelterRoute}
                style={({ pressed }) => [
                  styles.emergencyCta,
                  compact && styles.emergencyCtaCompact,
                  pressed && styles.pressed,
                ]}
              >
                <View style={styles.emergencyCtaTop}>
                  <MaterialCommunityIcons
                    name="map-marker-check-outline"
                    size={26}
                    color="#fff"
                  />
                  <Text style={styles.emergencyCtaText}>
                    공식 안내를 확인하세요
                  </Text>
                </View>
                <Text
                  style={[
                    styles.emergencyCtaTitle,
                    compact && styles.emergencyCtaTitleCompact,
                  ]}
                >
                  대피소로 이동하기
                </Text>
              </Pressable>
            ) : null}

            {!loading && !error ? (
              <GuideCard
                level={displayLevel}
                compact={compact}
                data={riskData}
              />
            ) : null}

            {!loading && !error && !isEmergency ? (
              <Pressable
                accessibilityRole="button"
                onPress={openShelterRoute}
                style={({ pressed }) => [
                  styles.shelterButton,
                  pressed && styles.pressed,
                ]}
              >
                <MaterialCommunityIcons
                  name="map-marker-check-outline"
                  size={25}
                  color="#fff"
                />
                <Text style={styles.shelterButtonText}>대피소 위치 확인</Text>
              </Pressable>
            ) : null}
          </ScrollView>
        </View>
      </TabSceneTransition>
      <BottomTabs active="disaster" />
    </AppScreen>
  );
}

function getBannerColor(level: string) {
  const normalizedLevel = toRiskLevel(level);

  return normalizedLevel ? riskConfig[normalizedLevel].color : colors.primary;
}

function getInAppBannerTitle(level: RiskLevel) {
  if (level === "emergency") {
    return "침수 긴급 알림";
  }
  if (level === "danger") {
    return "침수 위험 알림";
  }
  return "침수 주의 알림";
}

function toNotificationRiskLevel(level: RiskLevel) {
  if (level === "emergency") {
    return "emergency";
  }
  if (level === "danger") {
    return "danger";
  }
  return "caution";
}

function isLocationConfirmationLevel(level: RiskLevel) {
  return level === "caution" || level === "danger" || level === "emergency";
}

function getLocationBannerKey(data: AlertBannerResponse, level: RiskLevel) {
  return [data.user_id, level, data.detected_location].join(":");
}

function AlertBanner({
  data,
  disabled,
  onActionPress,
}: {
  data: AlertBannerResponse;
  disabled: boolean;
  onActionPress: (button: AlertBannerButton) => void;
}) {
  const accentColor = getBannerColor(data.level);

  return (
    <View style={styles.banner}>
      <View style={styles.bannerHeader}>
        <View style={[styles.bannerIcon, { backgroundColor: accentColor }]}>
          <Ionicons
            name="warning-outline"
            size={18}
            color={colors.background}
          />
        </View>
        <View style={styles.bannerCopy}>
          <Text style={styles.bannerTitle}>{data.banner_title}</Text>
          <Text style={styles.bannerMessage}>{data.banner_message}</Text>
          <Text style={styles.bannerLocation}>{data.detected_location}</Text>
        </View>
      </View>

      <View style={styles.bannerButtons}>
        {data.buttons.map((button) => (
          <Pressable
            key={button.action}
            accessibilityRole="button"
            disabled={disabled}
            onPress={() => onActionPress(button)}
            style={({ pressed }) => [
              styles.bannerButton,
              pressed && styles.pressed,
              disabled && styles.disabled,
            ]}
          >
            <Text style={styles.bannerButtonText}>{button.label}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function toRiskLevel(level?: string): RiskLevel | null {
  const normalizedLevel = level?.trim().toLowerCase();

  if (!normalizedLevel) {
    return null;
  }

  if (["safe", "normal", "안전", "일반"].includes(normalizedLevel)) {
    return "safe";
  }

  if (["caution", "주의"].includes(normalizedLevel)) {
    return "caution";
  }

  if (["danger", "위험"].includes(normalizedLevel)) {
    return "danger";
  }

  if (["emergency", "긴급"].includes(normalizedLevel)) {
    return "emergency";
  }

  return null;
}

function getRiskLevelLabel(level: RiskLevel) {
  if (level === "emergency") return "긴급";
  if (level === "danger") return "위험";
  if (level === "caution") return "주의";
  return "일반";
}

function RiskSummary({
  level,
  compact,
  data,
}: {
  level: RiskLevel;
  compact: boolean;
  data: RiskFactorsResponse | null;
}) {
  const config = riskConfig[level];
  const dataLevel = toRiskLevel(data?.level);
  const isSafe = level === "safe";
  const levelLabel = isSafe
    ? "안전"
    : dataLevel
      ? getRiskLevelLabel(dataLevel)
      : (data?.level ?? getRiskLevelLabel(level));
  const reasons =
    !isSafe && data?.risk_factors?.length
      ? data.risk_factors.map((item) => item.description).slice(0, 2)
      : config.reasons;
  const primaryMessage = isSafe
    ? config.reasons[0]
    : (data?.ai_message ?? reasons[0]);

  if (isSafe) {
    return (
      <Card style={[styles.summaryCard, compact && styles.summaryCardCompact]}>
        <View style={styles.summaryTop}>
          <View style={styles.summaryText}>
            <Text style={styles.summaryLabel}>현재 나의 위험 단계</Text>
            <Text
              style={[
                styles.riskLabel,
                compact && styles.riskLabelCompact,
                { color: config.color },
              ]}
            >
              안전
            </Text>
          </View>
          <View
            style={[
              styles.ring,
              compact && styles.ringCompact,
              { borderColor: config.color },
            ]}
          >
            <Ionicons
              name="warning-outline"
              size={compact ? 30 : 35}
              color={config.color}
            />
          </View>
        </View>
        <Reason
          icon="information-circle-outline"
          color={config.color}
          compact={compact}
        >
          {primaryMessage}
        </Reason>
        <Reason icon="rainy-outline" compact={compact}>
          {reasons[1]}
        </Reason>
      </Card>
    );
  }

  return (
    <Card style={[styles.summaryCard, compact && styles.summaryCardCompact]}>
      <View style={styles.summaryTop}>
        <View style={styles.summaryText}>
          <Text style={styles.summaryLabel}>
            {data?.title ?? "현재 나의 위험 단계"}
          </Text>
          <Text
            style={[
              styles.riskLabel,
              compact && styles.riskLabelCompact,
              { color: config.color },
            ]}
          >
            {levelLabel}
          </Text>
        </View>
        <View
          style={[
            styles.ring,
            compact && styles.ringCompact,
            { borderColor: config.color },
          ]}
        >
          <Ionicons
            name="warning-outline"
            size={compact ? 30 : 35}
            color={config.color}
          />
        </View>
      </View>
      <Reason
        icon="information-circle-outline"
        color={config.color}
        compact={compact}
      >
        {data?.ai_message ?? reasons[0]}
      </Reason>
      {reasons[1] ? (
        <Reason icon="rainy-outline" compact={compact}>
          {reasons[1]}
        </Reason>
      ) : null}
    </Card>
  );
}

function Reason({
  children,
  icon,
  compact,
  color = colors.text,
}: {
  children: string;
  icon: NoticeIcon;
  compact: boolean;
  color?: string;
}) {
  return (
    <View style={[styles.reasonRow, compact && styles.reasonRowCompact]}>
      <Ionicons name={icon} size={compact ? 17 : 19} color={color} />
      <Text style={[styles.reasonText, compact && styles.reasonTextCompact]}>
        {children}
      </Text>
    </View>
  );
}

function GuideCard({
  level,
  compact,
  data,
}: {
  level: RiskLevel;
  compact: boolean;
  data: RiskFactorsResponse | null;
}) {
  const config = riskConfig[level];

  if (level === "safe") {
    return (
      <View
        style={[
          styles.guideCard,
          styles.safeGuideCard,
          compact && styles.guideCardCompact,
          compact && styles.safeGuideCardCompact,
          { backgroundColor: config.guideBg },
        ]}
      >
        <MaterialCommunityIcons
          name="shield-check-outline"
          size={compact ? 30 : 34}
          color={config.color}
        />
        <Text
          style={[
            styles.safeGuideTitle,
            compact && styles.safeGuideTitleCompact,
          ]}
        >
          안전합니다
        </Text>
      </View>
    );
  }

  const actions = data?.actions?.length
    ? data.actions.map(
        (text, index) =>
          [config.actions?.[index]?.[0] ?? "alert-circle-outline", text] as [
            GuideIcon,
            string,
          ],
      )
    : (config.actions ?? []);

  return (
    <View
      style={[
        styles.guideCard,
        level === "emergency" && styles.guideCardEmergency,
        compact && styles.guideCardCompact,
        compact && level === "emergency" && styles.guideCardEmergencyCompact,
        { backgroundColor: config.guideBg },
      ]}
    >
      <Text style={[styles.guideTitle, compact && styles.guideTitleCompact]}>
        {config.guideTitle}
      </Text>
      {actions.map(([icon, text], index) => (
        <View key={text}>
          <View style={[styles.actionRow, compact && styles.actionRowCompact]}>
            <View
              style={[styles.actionIcon, compact && styles.actionIconCompact]}
            >
              <MaterialCommunityIcons
                name={icon}
                size={compact ? 20 : 23}
                color={config.color}
              />
            </View>
            <Text
              style={[
                styles.actionText,
                compact && styles.actionTextCompact,
                level === "emergency" && index === 0 && { color: config.color },
              ]}
            >
              {text}
            </Text>
          </View>
          {index < actions.length - 1 ? <Divider color={config.line} /> : null}
        </View>
      ))}
    </View>
  );
}

function StatusCard({
  compact,
  type,
  message,
}: {
  compact: boolean;
  type: "loading" | "error";
  message?: string;
}) {
  const isLoading = type === "loading";

  return (
    <Card style={[styles.statusCard, compact && styles.statusCardCompact]}>
      {isLoading ? (
        <ActivityIndicator size="large" color={colors.primary} />
      ) : (
        <Ionicons
          name="alert-circle-outline"
          size={42}
          color={colors.primary}
        />
      )}
      <Text style={styles.statusTitle}>
        {isLoading
          ? "위험 정보를 불러오는 중입니다"
          : "위험 정보를 불러오지 못했습니다"}
      </Text>
      <Text style={styles.statusMessage}>
        {isLoading
          ? "현재 위치와 사용자 정보를 기준으로 재난 위험을 확인하고 있어요."
          : (message ?? "잠시 후 다시 시도해주세요.")}
      </Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  screen: {
    paddingTop: 4,
    paddingBottom: 10,
  },
  contentFrame: {
    flex: 1,
  },
  body: {
    flexGrow: 1,
    gap: 10,
    paddingBottom: 18,
  },
  emergencyCallButton: {
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
  },
  bannerOverlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 10,
  },
  banner: {
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.bannerBox,
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 12,
  },
  bannerHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
  },
  bannerIcon: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 1,
  },
  bannerCopy: {
    flex: 1,
  },
  bannerTitle: {
    ...typography.bannerTitle,
    color: colors.background,
    fontWeight: "700",
  },
  bannerMessage: {
    fontSize: 13,
    lineHeight: 18,
    color: colors.background,
    fontWeight: "500",
    marginTop: 5,
  },
  bannerLocation: {
    ...typography.bannerTime,
    color: colors.x,
    marginTop: 5,
  },
  bannerButtons: {
    flexDirection: "row",
    gap: 10,
  },
  bannerButton: {
    flex: 1,
    minHeight: 36,
    borderRadius: 6,
    backgroundColor: colors.yesOrNo,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 10,
  },
  bannerButtonText: {
    ...typography.bannerButton,
    color: colors.background,
    fontWeight: "700",
  },
  disabled: {
    opacity: 0.55,
  },
  statusCard: {
    minHeight: 230,
    paddingHorizontal: 22,
    paddingVertical: 24,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
  },
  statusCardCompact: {
    minHeight: 210,
    paddingVertical: 18,
  },
  statusTitle: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
    textAlign: "center",
  },
  statusMessage: {
    fontSize: 15,
    lineHeight: 21,
    fontWeight: "600",
    color: colors.subText,
    textAlign: "center",
  },
  summaryCard: {
    minHeight: 230,
    paddingHorizontal: 22,
    paddingVertical: 18,
  },
  summaryCardCompact: {
    minHeight: 210,
    paddingHorizontal: 18,
    paddingVertical: 13,
  },
  summaryTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
  },
  summaryText: {
    flex: 1,
  },
  summaryLabel: {
    ...typography.titleMedium,
    color: colors.subText,
    marginBottom: 2,
  },
  riskLabel: {
    fontSize: 50,
    lineHeight: 57,
    fontWeight: "700",
  },
  riskLabelCompact: {
    fontSize: 43,
    lineHeight: 49,
  },
  ring: {
    width: 90,
    height: 90,
    borderRadius: 45,
    borderWidth: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  ringCompact: {
    width: 76,
    height: 76,
    borderRadius: 38,
    borderWidth: 7,
  },
  reasonRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 7,
    marginTop: 8,
  },
  reasonRowCompact: {
    gap: 6,
    marginTop: 6,
  },
  reasonText: {
    flex: 1,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: "600",
    color: colors.subText,
  },
  reasonTextCompact: {
    fontSize: 13,
    lineHeight: 18,
  },
  guideCard: {
    minHeight: 300,
    borderWidth: 1,
    borderColor: colors.cardLine,
    borderRadius: radius.borderRadiusSm,
    paddingHorizontal: 24,
    paddingVertical: 18,
  },
  guideCardCompact: {
    minHeight: 270,
    paddingHorizontal: 20,
    paddingVertical: 13,
  },
  safeGuideCard: {
    alignItems: "center",
    paddingTop: 18,
  },
  safeGuideCardCompact: {
    paddingTop: 14,
  },
  guideCardEmergency: {
    minHeight: 225,
  },
  guideCardEmergencyCompact: {
    minHeight: 205,
  },
  guideTitle: {
    fontSize: 22,
    lineHeight: 27,
    fontWeight: "700",
    color: colors.text,
    marginBottom: 12,
  },
  guideTitleCompact: {
    fontSize: 20,
    lineHeight: 24,
    marginBottom: 8,
  },
  safeGuideTitle: {
    fontSize: 18,
    lineHeight: 24,
    fontWeight: "700",
    color: colors.text,
    marginTop: 7,
  },
  safeGuideTitleCompact: {
    fontSize: 16,
    lineHeight: 21,
    marginTop: 5,
  },
  actionRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 12,
  },
  actionRowCompact: {
    gap: 10,
    paddingVertical: 8,
  },
  actionIcon: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.82)",
  },
  actionIconCompact: {
    width: 32,
    height: 32,
    borderRadius: 16,
  },
  actionText: {
    flex: 1,
    fontSize: 17,
    lineHeight: 23,
    fontWeight: "600",
    color: colors.actionText,
  },
  actionTextCompact: {
    fontSize: 14,
    lineHeight: 19,
  },
  shelterButton: {
    height: 52,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.actionText,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.md,
  },
  shelterButtonText: {
    ...typography.shelterButton,
    color: colors.background,
    fontSize: 20,
    lineHeight: 26,
  },
  emergencyCta: {
    height: 126,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.emergency,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 18,
  },
  emergencyCtaCompact: {
    height: 110,
    paddingVertical: 12,
  },
  emergencyCtaTop: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginBottom: 4,
  },
  emergencyCtaText: {
    fontSize: 18,
    lineHeight: 23,
    fontWeight: "700",
    color: colors.background,
  },
  emergencyCtaTitle: {
    fontSize: 26,
    lineHeight: 32,
    fontWeight: "700",
    color: colors.background,
  },
  emergencyCtaTitleCompact: {
    fontSize: 23,
    lineHeight: 28,
  },
  pressed: {
    opacity: 0.8,
  },
});
