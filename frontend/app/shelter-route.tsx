import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  AppState,
  type AppStateStatus,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import * as Location from "expo-location";
import { useLocalSearchParams, useRouter } from "expo-router";

import {
  getNearbyShelters,
  type NearbySheltersResponse,
  type Shelter,
} from "../src/api/shelterApi";
import { colors, radius, typography } from "../src/constants/theme";

const DEFAULT_POSITION = {
  latitude: 37.5446,
  longitude: 126.9647,
};
const ROUTE_RETURN_POPUP_DELAY_MS = 700;

export default function ShelterRouteScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{
    latitude?: string;
    longitude?: string;
    arrival?: string;
  }>();
  const appStateRef = useRef<AppStateStatus>(AppState.currentState);
  const routeOpenedAtRef = useRef<number | null>(null);
  const routeReturnPendingRef = useRef(false);
  const [shelterData, setShelterData] =
    useState<NearbySheltersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openingShelterId, setOpeningShelterId] = useState<number | null>(null);
  const [showArrivalConfirm, setShowArrivalConfirm] = useState(false);

  const resolvePosition = useCallback(
    async (preferRouteParams: boolean) => {
      const routeLatitude = Number(params.latitude);
      const routeLongitude = Number(params.longitude);

      if (
        preferRouteParams &&
        Number.isFinite(routeLatitude) &&
        Number.isFinite(routeLongitude)
      ) {
        return {
          latitude: routeLatitude,
          longitude: routeLongitude,
        };
      }

      const { status } = await Location.requestForegroundPermissionsAsync();

      if (status !== Location.PermissionStatus.GRANTED) {
        return DEFAULT_POSITION;
      }

      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });

      return {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      };
    },
    [params.latitude, params.longitude],
  );

  const loadShelters = useCallback(
    async (preferRouteParams = true) => {
      try {
        setLoading(true);
        setError("");

        const position = await resolvePosition(preferRouteParams);
        const data = await getNearbyShelters(position);

        setShelterData(data);
      } catch (loadError) {
        console.error("Failed to load nearby shelters", loadError);
        setError(
          "현재 위치 기준 대피소 정보를 불러오지 못했습니다. 위치 권한과 네트워크를 확인해 주세요.",
        );
      } finally {
        setLoading(false);
      }
    },
    [resolvePosition],
  );

  useEffect(() => {
    void loadShelters(true);
  }, [loadShelters]);

  useEffect(() => {
    if (params.arrival === "1") {
      setShowArrivalConfirm(true);
    }
  }, [params.arrival]);

  const showPopupAfterRouteReturn = useCallback(() => {
    if (!routeReturnPendingRef.current) {
      return;
    }

    const routeOpenedAt = routeOpenedAtRef.current;
    if (
      routeOpenedAt !== null &&
      Date.now() - routeOpenedAt < ROUTE_RETURN_POPUP_DELAY_MS
    ) {
      return;
    }

    routeReturnPendingRef.current = false;
    routeOpenedAtRef.current = null;
    setShowArrivalConfirm(true);
  }, []);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (nextState) => {
      const previousState = appStateRef.current;
      appStateRef.current = nextState;

      if (
        previousState.match(/inactive|background/) &&
        nextState === "active"
      ) {
        showPopupAfterRouteReturn();
      }
    });

    return () => {
      subscription.remove();
    };
  }, [showPopupAfterRouteReturn]);

  useEffect(() => {
    if (Platform.OS !== "web" || typeof window === "undefined") {
      return;
    }

    window.addEventListener("focus", showPopupAfterRouteReturn);

    return () => {
      window.removeEventListener("focus", showPopupAfterRouteReturn);
    };
  }, [showPopupAfterRouteReturn]);

  const openRoute = async (shelter: Shelter) => {
    const routeUrl = shelter.route_url ?? shelter.map_url;

    try {
      setOpeningShelterId(shelter.id);
      routeReturnPendingRef.current = true;
      routeOpenedAtRef.current = Date.now();

      if (Platform.OS === "web" && typeof window !== "undefined") {
        window.open(routeUrl, "_blank", "noopener,noreferrer");
        return;
      }

      await Linking.openURL(routeUrl);
    } catch (openError) {
      routeReturnPendingRef.current = false;
      routeOpenedAtRef.current = null;
      console.error("Failed to open Kakao route URL", openError);
      setError("카카오맵 길찾기를 열지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setOpeningShelterId(null);
    }
  };

  const nearestShelter = shelterData?.nearest_shelter ?? null;
  const shelters = shelterData?.shelters ?? [];
  const currentLocation = shelterData?.current_location;

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="뒤로 가기"
          style={({ pressed }) => [
            styles.circleButton,
            pressed && styles.pressed,
          ]}
          onPress={() => router.back()}
        >
          <Ionicons name="arrow-back" size={29} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>대피소 안내</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="현재 위치 기준 새로고침"
          style={({ pressed }) => [
            styles.circleButton,
            pressed && styles.pressed,
          ]}
          onPress={() => void loadShelters(false)}
        >
          <Ionicons name="locate-outline" size={31} color={colors.text} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.locationBanner}>
          <View style={styles.locationIcon}>
            <Ionicons name="location" size={20} color={colors.rode} />
          </View>
          <View style={styles.locationTextWrap}>
            <Text style={styles.locationTitle}>현재 위치 기준</Text>
            <Text style={styles.locationMeta}>
              {currentLocation
                ? `${currentLocation.latitude.toFixed(4)}, ${currentLocation.longitude.toFixed(4)}`
                : "가까운 대피소를 확인하고 있습니다."}
            </Text>
          </View>
        </View>

        {loading ? (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.primary} />
            <Text style={styles.stateText}>가까운 대피소를 찾고 있습니다.</Text>
          </View>
        ) : null}

        {error ? (
          <View style={styles.errorBox}>
            <Ionicons name="warning-outline" size={22} color={colors.primary} />
            <Text style={styles.errorText}>{error}</Text>
            <Pressable
              accessibilityRole="button"
              style={({ pressed }) => [
                styles.retryButton,
                pressed && styles.pressed,
              ]}
              onPress={() => void loadShelters(false)}
            >
              <Text style={styles.retryButtonText}>다시 시도</Text>
            </Pressable>
          </View>
        ) : null}

        {nearestShelter ? (
          <View style={styles.recommendCard}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>가장 가까운 대피소</Text>
              <View style={styles.statusPill}>
                <Text style={styles.statusText}>
                  {nearestShelter.status_text}
                </Text>
              </View>
            </View>
            <View style={styles.recommendBody}>
              <View style={styles.markerCircle}>
                <MaterialCommunityIcons
                  name="map-marker-check-outline"
                  size={32}
                  color={colors.primary}
                />
              </View>
              <View style={styles.recommendCopy}>
                <Text style={styles.shelterName}>{nearestShelter.name}</Text>
                <Text style={styles.addressText}>{nearestShelter.address}</Text>
                <Text style={styles.distanceText}>
                  직선거리 {formatShelterDistance(nearestShelter)}
                </Text>
                <Text style={styles.routeHintText}>
                  실제 이동 거리와 시간은 길찾기에서 확인해 주세요.
                </Text>
              </View>
            </View>
            <RouteButton
              loading={openingShelterId === nearestShelter.id}
              onPress={() => void openRoute(nearestShelter)}
              wide
            />
          </View>
        ) : null}

        <View style={styles.listSection}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>주변 대피소 목록</Text>
            <Text style={styles.countText}>{shelters.length}곳</Text>
          </View>

          {shelters.length > 0 ? (
            shelters.map((shelter, index) => (
              <ShelterRow
                index={index}
                key={shelter.id}
                loading={openingShelterId === shelter.id}
                onRoutePress={() => void openRoute(shelter)}
                shelter={shelter}
              />
            ))
          ) : !loading ? (
            <View style={styles.emptyBox}>
              <Text style={styles.emptyText}>
                표시할 대피소 목록이 없습니다.
              </Text>
            </View>
          ) : null}
        </View>
      </ScrollView>

      {showArrivalConfirm ? (
        <ArrivalConfirmDialog
          onCancel={() => setShowArrivalConfirm(false)}
          onComplete={() => {
            setShowArrivalConfirm(false);
            router.push("/missing" as never);
          }}
        />
      ) : null}
    </View>
  );
}

function ArrivalConfirmDialog({
  onCancel,
  onComplete,
}: {
  onCancel: () => void;
  onComplete: () => void;
}) {
  return (
    <View style={styles.arrivalOverlay}>
      <View style={styles.arrivalDialog}>
        <View style={styles.arrivalTitleRow}>
          <View style={styles.arrivalIconWrap}>
            <Ionicons
              name="shield-checkmark-outline"
              size={34}
              color={colors.primary}
            />
          </View>
          <Text style={styles.arrivalTitle}>대피 확인</Text>
        </View>
        <Text style={styles.arrivalQuestion}>
          안전하게 대피를 완료하셨나요?
        </Text>
        <Text style={styles.arrivalBody}>
          현재 대피소에 도착했다면{"\n"}아래 버튼을 눌러 알려주세요
        </Text>
        <View style={styles.arrivalButtons}>
          <Pressable
            accessibilityRole="button"
            onPress={onCancel}
            style={({ pressed }) => [
              styles.arrivalSecondaryButton,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.arrivalSecondaryText}>아직 도착 전</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={onComplete}
            style={({ pressed }) => [
              styles.arrivalPrimaryButton,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.arrivalPrimaryText}>대피 완료</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

function ShelterRow({
  index,
  loading,
  onRoutePress,
  shelter,
}: {
  index: number;
  loading: boolean;
  onRoutePress: () => void;
  shelter: Shelter;
}) {
  return (
    <View style={styles.shelterRow}>
      <View style={styles.rankBox}>
        <Text style={styles.rankText}>{index + 1}</Text>
      </View>
      <View style={styles.rowCopy}>
        <Text style={styles.rowName} numberOfLines={1}>
          {shelter.name}
        </Text>
        <Text style={styles.rowAddress} numberOfLines={2}>
          {shelter.address}
        </Text>
        <Text style={styles.rowMeta}>
          직선거리 {formatShelterDistance(shelter)}
        </Text>
      </View>
      <RouteButton loading={loading} onPress={onRoutePress} />
    </View>
  );
}

function RouteButton({
  loading,
  onPress,
  wide = false,
}: {
  loading: boolean;
  onPress: () => void;
  wide?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={loading}
      style={({ pressed }) => [
        styles.routeButton,
        wide && styles.routeButtonWide,
        pressed && styles.pressed,
        loading && styles.disabledButton,
      ]}
      onPress={onPress}
    >
      {loading ? (
        <ActivityIndicator color={colors.background} size="small" />
      ) : (
        <>
          <Ionicons name="navigate" size={17} color={colors.background} />
          <Text style={styles.routeButtonText}>길찾기</Text>
        </>
      )}
    </Pressable>
  );
}

function formatShelterDistance(shelter: Shelter) {
  return formatDistance(shelter.straight_distance_m ?? shelter.distance_m);
}

function formatDistance(distanceM: number) {
  if (distanceM >= 1000) {
    return `${(distanceM / 1000).toFixed(1)}km`;
  }

  return `${Math.round(distanceM)}m`;
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F7F7F7",
  },
  header: {
    paddingTop: 54,
    paddingHorizontal: 24,
    paddingBottom: 18,
    backgroundColor: colors.background,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  circleButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.card,
    alignItems: "center",
    justifyContent: "center",
  },
  headerTitle: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  content: {
    paddingHorizontal: 18,
    paddingTop: 18,
    paddingBottom: 28,
    gap: 16,
  },
  locationBanner: {
    minHeight: 72,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.cardLine,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  locationIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.location,
    alignItems: "center",
    justifyContent: "center",
  },
  locationTextWrap: {
    flex: 1,
  },
  locationTitle: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  locationMeta: {
    ...typography.helperTiny,
    color: colors.subText,
    marginTop: 4,
  },
  stateBox: {
    minHeight: 96,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.cardLine,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },
  stateText: {
    ...typography.helperTiny,
    color: colors.subText,
  },
  errorBox: {
    borderRadius: radius.borderRadiusSm,
    borderWidth: 1,
    borderColor: "rgba(229, 57, 53, 0.35)",
    backgroundColor: colors.emergencyBox,
    padding: 16,
    gap: 10,
  },
  errorText: {
    ...typography.helperTiny,
    color: colors.text,
  },
  retryButton: {
    height: 38,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  retryButtonText: {
    ...typography.shelterButton,
    color: colors.background,
    fontWeight: "700",
  },
  recommendCard: {
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.cardLine,
    padding: 18,
    gap: 16,
  },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  sectionTitle: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  statusPill: {
    minHeight: 26,
    borderRadius: 13,
    paddingHorizontal: 10,
    backgroundColor: colors.checkCard,
    alignItems: "center",
    justifyContent: "center",
  },
  statusText: {
    ...typography.bodySmall,
    color: colors.primary,
    fontWeight: "700",
  },
  recommendBody: {
    flexDirection: "row",
    gap: 12,
  },
  markerCircle: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: colors.shelterIcon,
    alignItems: "center",
    justifyContent: "center",
  },
  recommendCopy: {
    flex: 1,
    gap: 5,
  },
  shelterName: {
    fontSize: 20,
    lineHeight: 25,
    fontWeight: "700",
    color: colors.text,
  },
  addressText: {
    ...typography.helperTiny,
    color: colors.subText,
  },
  distanceText: {
    ...typography.titleMedium,
    color: colors.primary,
    fontWeight: "700",
  },
  routeHintText: {
    ...typography.helperTiny,
    color: colors.subText,
  },
  listSection: {
    gap: 10,
  },
  countText: {
    ...typography.helperTiny,
    color: colors.subText,
  },
  shelterRow: {
    minHeight: 112,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.cardLine,
    padding: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  rankBox: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.card,
    alignItems: "center",
    justifyContent: "center",
  },
  rankText: {
    ...typography.bodySmall,
    color: colors.text,
    fontWeight: "700",
  },
  rowCopy: {
    flex: 1,
    minWidth: 0,
    gap: 4,
  },
  rowName: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  rowAddress: {
    ...typography.helperTiny,
    color: colors.subText,
  },
  rowMeta: {
    ...typography.shelterButton,
    color: colors.primary,
    fontWeight: "700",
  },
  routeButton: {
    width: 82,
    minHeight: 38,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.primary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 5,
  },
  routeButtonWide: {
    width: "100%",
    minHeight: 48,
  },
  routeButtonText: {
    ...typography.shelterButton,
    color: colors.background,
    fontWeight: "700",
  },
  disabledButton: {
    opacity: 0.72,
  },
  emptyBox: {
    minHeight: 90,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.cardLine,
    alignItems: "center",
    justifyContent: "center",
  },
  emptyText: {
    ...typography.helperTiny,
    color: colors.subText,
  },
  pressed: {
    opacity: 0.78,
  },
  arrivalOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.24)",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 28,
    zIndex: 20,
  },
  arrivalDialog: {
    width: "100%",
    maxWidth: 320,
    borderRadius: 27,
    backgroundColor: colors.background,
    paddingHorizontal: 18,
    paddingVertical: 30,
    alignItems: "center",
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },
  arrivalTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    marginBottom: 18,
  },
  arrivalIconWrap: {
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: colors.checkCard,
    alignItems: "center",
    justifyContent: "center",
  },
  arrivalTitle: {
    ...typography.completeCheck,
    color: colors.text,
  },
  arrivalQuestion: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
    marginBottom: 17,
    textAlign: "center",
  },
  arrivalBody: {
    ...typography.bodyMediumRegular,
    color: colors.subText,
    textAlign: "center",
    marginBottom: 27,
  },
  arrivalButtons: {
    width: "100%",
    flexDirection: "row",
    gap: 14,
  },
  arrivalSecondaryButton: {
    flex: 1,
    minHeight: 52,
    borderRadius: radius.borderRadiusSm,
    borderWidth: 1,
    borderColor: colors.cardLine,
    backgroundColor: colors.background,
    alignItems: "center",
    justifyContent: "center",
  },
  arrivalPrimaryButton: {
    flex: 1,
    minHeight: 52,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  arrivalSecondaryText: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  arrivalPrimaryText: {
    ...typography.titleMedium,
    color: colors.background,
    fontWeight: "700",
  },
});
