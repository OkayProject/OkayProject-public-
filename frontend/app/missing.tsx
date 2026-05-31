import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import * as Location from "expo-location";
import { useRouter } from "expo-router";

import {
  classifyMissingAlerts,
  type MissingAlert,
} from "../src/api/missingApi";
import { colors, spacing, typography } from "../src/constants/theme";
import {
  loadFrequentPlaces,
  loadSavedUserId,
} from "../src/storage/userProfile";
import {
  AppHeader,
  AppScreen,
  BottomTabs,
  Card,
  HeaderActions,
  PrimaryButton,
  SecondaryButton,
  StatusBadge,
  TabSceneTransition,
} from "../src/components/okay-ui";
import { MissingReferenceImage } from "../src/components/missing-reference-image";

const DEFAULT_POSITION = {
  latitude: 37.5446,
  longitude: 126.9647,
};

const MISSING_ALERT_CACHE_TTL_MS = 5 * 60 * 1000;
const LAST_KNOWN_LOCATION_MAX_AGE_MS = 5 * 60 * 1000;

let missingAlertCache:
  | {
      alerts: MissingAlert[];
      savedAt: number;
    }
  | null = null;

function getFreshMissingAlertCache() {
  if (!missingAlertCache) {
    return null;
  }

  if (Date.now() - missingAlertCache.savedAt > MISSING_ALERT_CACHE_TTL_MS) {
    missingAlertCache = null;
    return null;
  }

  return missingAlertCache.alerts;
}

export default function MissingScreen() {
  const router = useRouter();
  const cachedAlerts = getFreshMissingAlertCache();
  const [alerts, setAlerts] = useState<MissingAlert[]>(cachedAlerts ?? []);
  const [loading, setLoading] = useState(!cachedAlerts);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    const cachedAlertsOnMount = getFreshMissingAlertCache();

    async function resolvePosition() {
      const { status } = await Location.getForegroundPermissionsAsync();

      if (status !== Location.PermissionStatus.GRANTED) {
        return DEFAULT_POSITION;
      }

      const position =
        (await Location.getLastKnownPositionAsync({
          maxAge: LAST_KNOWN_LOCATION_MAX_AGE_MS,
          requiredAccuracy: 200,
        })) ??
        (await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        }));

      return {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      };
    }

    async function fetchMissingAlerts() {
      try {
        if (!cachedAlertsOnMount) {
          setLoading(true);
        }
        setError("");

        const position = await resolvePosition();
        const [savedUserId, frequentPlaces] = await Promise.all([
          loadSavedUserId(),
          loadFrequentPlaces(),
        ]);
        const requestFrequentPlaces = frequentPlaces.map((place, index) => ({
          name:
            place.name ||
            place.roadAddressName ||
            place.addressName ||
            `frequent_place_${index + 1}`,
          address: place.roadAddressName || place.addressName,
          latitude: Number(place.y),
          longitude: Number(place.x),
        }));
        console.log("Resolved position", position);

        const response = await classifyMissingAlerts({
          ...(savedUserId ? { user_id: savedUserId } : {}),
          latitude: position.latitude,
          longitude: position.longitude,
          limit: 10,
          max_distance_m: 15000,
          frequent_places: requestFrequentPlaces,
        });

        console.log("Missing alert full response", response);
        console.log("source", response.source);
        console.log("fallback_reason", response.fallback_reason);
        console.log("count", response.count);
        console.log("alerts", response.alerts);

        if (mounted) {
          missingAlertCache = {
            alerts: response.alerts,
            savedAt: Date.now(),
          };
          setAlerts(response.alerts);
        }
      } catch (fetchError) {
        console.error("POST /missing-alert/classify failed", fetchError);

        if (mounted) {
          setError("실종자 알림 정보를 불러오지 못했습니다.");
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    if (cachedAlertsOnMount) {
      setAlerts(cachedAlertsOnMount);
      setLoading(false);
      return () => {
        mounted = false;
      };
    }

    fetchMissingAlerts();

    return () => {
      mounted = false;
    };
  }, []);

  const primaryAlert = alerts[0] ?? null;
  const details = useMemo(() => buildDetails(primaryAlert), [primaryAlert]);
  const primaryMissingPersonId = primaryAlert
    ? String(primaryAlert.stable_id ?? primaryAlert.id)
    : "";

  function handleEmergencyCall() {
    Linking.openURL("tel:112").catch((callError) => {
      console.error("Failed to open phone app", callError);
    });
  }

  return (
    <AppScreen contentStyle={styles.screen}>
      <TabSceneTransition active="missing">
        <AppHeader title="실종자 알림" right={<HeaderActions />} />
        <View style={styles.body}>
          {loading ? (
            <StatusCard type="loading" />
          ) : error ? (
            <StatusCard type="error" message={error} />
          ) : primaryAlert ? (
            <>
              <View style={styles.statusLine}>
                <StatusBadge>현재 수색 중</StatusBadge>
                <Text style={styles.lastSeen}>
                  최종 목격{" "}
                  <Text style={styles.red}>
                    {formatMissingTime(primaryAlert.missing_time_hours)}
                  </Text>
                </Text>
              </View>

              <Card style={styles.locationCard}>
                <Ionicons
                  name="location-sharp"
                  size={21}
                  color={colors.primary}
                />
                <View style={styles.locationTextWrap}>
                  <Text style={styles.locationTitle}>
                    최종 목격 장소:{" "}
                    {primaryAlert.last_seen_location ?? "위치 정보 확인 중"}
                  </Text>
                  <Text style={styles.locationSub}>
                    가까운 기준 위치 기준{" "}
                    {formatDistance(primaryAlert.distance_m)}
                  </Text>
                </View>
              </Card>

              <Card style={styles.personCard}>
                <Pressable
                  accessibilityRole="button"
                  onPress={() =>
                    router.push({
                      pathname: "/missing-detail",
                      params: { missingPersonId: primaryMissingPersonId },
                    })
                  }
                  style={styles.avatarWrap}
                >
                  <MissingReferenceImage
                    missingPersonId={primaryMissingPersonId}
                  />
                </Pressable>
                <View style={styles.detailList}>
                  <View style={styles.detailBox}>
                    {details.map((item, index) => (
                      <View key={`${item}-${index}`} style={styles.detailRow}>
                        <MaterialCommunityIcons
                          name="chevron-down-circle-outline"
                          size={15}
                          color={colors.primary}
                        />
                        <Text style={styles.detailText}>{item}</Text>
                      </View>
                    ))}
                  </View>
                </View>
              </Card>

              <Text style={styles.alertMessage}>
                {primaryAlert.alert_message ??
                  "주변을 확인하고 관련 단서가 있으면 신고해 주세요."}
              </Text>
            </>
          ) : (
            <StatusCard type="error" message="표시할 실종자 알림이 없습니다." />
          )}

          <View style={styles.buttons}>
            <PrimaryButton
              onPress={handleEmergencyCall}
              style={styles.actionButton}
            >
              <MaterialCommunityIcons
                name="bullhorn-outline"
                size={21}
                color="#fff"
              />
              <Text style={styles.actionButtonText}>제보하기</Text>
            </PrimaryButton>
            <SecondaryButton
              onPress={() =>
                primaryMissingPersonId
                  ? router.push({
                      pathname: "/missing-detail",
                      params: { missingPersonId: primaryMissingPersonId },
                    })
                  : router.push("/missing-detail")
              }
              style={styles.actionButton}
            >
              <MaterialCommunityIcons
                name="image-search-outline"
                size={21}
                color={colors.text}
              />
              <Text style={styles.secondaryActionText}>이미지 크게 보기</Text>
            </SecondaryButton>
          </View>
        </View>
      </TabSceneTransition>

      <BottomTabs active="missing" />
    </AppScreen>
  );
}

function StatusCard({
  type,
  message,
}: {
  type: "loading" | "error";
  message?: string;
}) {
  const isLoading = type === "loading";

  return (
    <Card style={styles.statusCard}>
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
        {isLoading ? "실종자 알림을 확인하는 중입니다." : message}
      </Text>
    </Card>
  );
}

function buildDetails(alert: MissingAlert | null) {
  if (!alert) {
    return [];
  }

  return [
    [alert.name, alert.age ? `${alert.age}세` : null, alert.gender]
      .filter(Boolean)
      .join(" / "),
    alert.missing_person_category
      ? `분류: ${alert.missing_person_category}`
      : null,
    alert.appearance_description,
    alert.description,
  ].filter((item): item is string => Boolean(item));
}

function formatMissingTime(hours?: number) {
  if (hours === undefined || hours === null) {
    return "확인 중";
  }

  if (hours < 1) {
    return "1시간 이내";
  }

  return `${hours}시간 전`;
}

function formatDistance(distanceM?: number | null) {
  if (distanceM === undefined || distanceM === null) {
    return "거리 확인 중";
  }

  if (distanceM >= 1000) {
    return `${(distanceM / 1000).toFixed(1)}km`;
  }

  return `${Math.round(distanceM)}m`;
}

const styles = StyleSheet.create({
  screen: {
    paddingTop: 4,
    paddingBottom: 10,
  },
  body: {
    flex: 1,
    gap: 8,
    paddingBottom: 8,
  },
  statusLine: {
    flexDirection: "row",
    alignItems: "center",
    gap: 17,
  },
  lastSeen: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  red: {
    color: colors.primary,
  },
  locationCard: {
    minHeight: 66,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
  locationTextWrap: {
    flex: 1,
    gap: 7,
  },
  locationTitle: {
    fontSize: 15,
    lineHeight: 20,
    color: colors.text,
    fontWeight: "700",
  },
  locationSub: {
    fontSize: 15,
    lineHeight: 20,
    color: colors.subText,
    fontWeight: "600",
  },
  personCard: {
    flex: 1,
    minHeight: 320,
    flexDirection: "row",
    alignItems: "stretch",
    gap: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  avatarWrap: {
    width: 168,
    alignSelf: "stretch",
    alignItems: "center",
    justifyContent: "center",
  },
  detailList: {
    flex: 1,
    justifyContent: "center",
  },
  detailBox: {
    borderWidth: 1,
    borderColor: colors.cardLine,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 12,
    gap: 12,
  },
  detailRow: {
    minHeight: 24,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 6,
  },
  detailText: {
    flex: 1,
    fontSize: 14,
    lineHeight: 19,
    color: colors.text,
    fontWeight: "500",
  },
  alertMessage: {
    fontSize: 14,
    lineHeight: 20,
    color: colors.subText,
    fontWeight: "600",
  },
  buttons: {
    flexDirection: "row",
    gap: 10,
    marginTop: 0,
    marginBottom: 0,
  },
  actionButton: {
    flex: 1,
    minHeight: 47,
    flexDirection: "row",
    gap: 5,
  },
  actionButtonText: {
    ...typography.titleMedium,
    color: colors.background,
  },
  secondaryActionText: {
    ...typography.titleMedium,
    color: colors.text,
  },
  statusCard: {
    minHeight: 390,
    alignItems: "center",
    justifyContent: "center",
    gap: 14,
    paddingHorizontal: 20,
  },
  statusTitle: {
    ...typography.titleMedium,
    color: colors.text,
    textAlign: "center",
  },
});
