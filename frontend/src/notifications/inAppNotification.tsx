import { ReactNode, useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, radius, spacing, typography } from "../constants/theme";
import {
  AlertHistoryItem,
  createAlertHistoryItemFromNotificationContent,
  saveAlertHistoryItem,
} from "../storage/alertHistory";

type InAppNotificationListener = (item: AlertHistoryItem) => void;
type NotificationContent = Parameters<
  typeof createAlertHistoryItemFromNotificationContent
>[0];

const listeners = new Set<InAppNotificationListener>();

const riskLabels = {
  caution: "주의",
  danger: "위험",
  emergency: "긴급",
} as const;

const riskColors = {
  caution: colors.caution,
  danger: colors.danger,
  emergency: colors.emergency,
} as const;

function subscribeInAppNotification(listener: InAppNotificationListener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function publishInAppNotification(item: AlertHistoryItem) {
  listeners.forEach((listener) => listener(item));
}

export async function showInAppNotificationFromContent(
  content: NotificationContent,
) {
  const item = createAlertHistoryItemFromNotificationContent(content);
  if (!item) {
    return null;
  }

  await saveAlertHistoryItem(item);
  publishInAppNotification(item);
  return item;
}

export function InAppNotificationProvider({
  children,
}: {
  children: ReactNode;
}) {
  const router = useRouter();
  const [currentAlert, setCurrentAlert] = useState<AlertHistoryItem | null>(
    null,
  );
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const unsubscribe = subscribeInAppNotification((item) => {
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current);
      }

      setCurrentAlert(item);
      hideTimerRef.current = setTimeout(() => {
        setCurrentAlert(null);
        hideTimerRef.current = null;
      }, 6000);
    });

    return () => {
      unsubscribe();
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current);
      }
    };
  }, []);

  const closeBanner = () => {
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    setCurrentAlert(null);
  };

  const openAlertHistory = () => {
    closeBanner();
    router.push("/alert-history" as never);
  };

  return (
    <View style={styles.root}>
      {children}
      {currentAlert ? (
        <SafeAreaView
          pointerEvents="box-none"
          style={styles.overlay}
          edges={["top"]}
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="지난 알람에서 알림 보기"
            onPress={openAlertHistory}
            style={styles.banner}
          >
            <View
              style={[
                styles.iconCircle,
                { backgroundColor: getAccentColor(currentAlert) },
              ]}
            >
              {currentAlert.type === "missing" ? (
                <MaterialCommunityIcons
                  name="account-search-outline"
                  size={22}
                  color="#fff"
                />
              ) : (
                <MaterialCommunityIcons
                  name="home-flood"
                  size={21}
                  color="#fff"
                />
              )}
            </View>
            <View style={styles.copy}>
              <View style={styles.titleRow}>
                <Text style={styles.title} numberOfLines={1}>
                  {currentAlert.title}
                </Text>
                {currentAlert.type === "flood" && currentAlert.riskLevel ? (
                  <Text style={styles.level}>
                    {riskLabels[currentAlert.riskLevel]}
                  </Text>
                ) : null}
              </View>
              <Text style={styles.message} numberOfLines={2}>
                {currentAlert.message}
              </Text>
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="알림 배너 닫기"
              onPress={closeBanner}
              hitSlop={8}
              style={styles.closeButton}
            >
              <Ionicons name="close" size={18} color={colors.background} />
            </Pressable>
          </Pressable>
        </SafeAreaView>
      ) : null}
    </View>
  );
}

function getAccentColor(alert: AlertHistoryItem) {
  if (alert.type === "missing") {
    return colors.missingAlarm;
  }

  return alert.riskLevel ? riskColors[alert.riskLevel] : colors.primary;
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  overlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 100,
    paddingHorizontal: spacing.md,
  },
  banner: {
    minHeight: 72,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.bannerBox,
    paddingHorizontal: 14,
    paddingVertical: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  iconCircle: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
  },
  copy: {
    flex: 1,
    gap: 4,
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  title: {
    ...typography.bannerContentBold,
    flex: 1,
    color: colors.background,
    fontSize: 13,
    lineHeight: 16,
  },
  level: {
    ...typography.bannerButton,
    color: colors.background,
    fontWeight: "700",
  },
  message: {
    ...typography.bannerContent,
    color: colors.background,
    lineHeight: 15,
  },
  closeButton: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.xCircle,
  },
});
