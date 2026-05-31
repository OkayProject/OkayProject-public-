import { useCallback, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";

import { colors, spacing, typography } from "../src/constants/theme";
import { AppHeader, AppScreen, Card } from "../src/components/okay-ui";
import {
  AlertHistoryItem,
  AlertHistoryRiskLevel,
  loadAlertHistory,
} from "../src/storage/alertHistory";

const riskLabels: Record<AlertHistoryRiskLevel, string> = {
  caution: "주의",
  danger: "위험",
  emergency: "긴급",
};

const riskColors: Record<AlertHistoryRiskLevel, string> = {
  caution: colors.caution,
  danger: colors.danger,
  emergency: colors.emergency,
};

export default function AlertHistoryScreen() {
  const [alerts, setAlerts] = useState<AlertHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useFocusEffect(
    useCallback(() => {
      let isActive = true;

      setIsLoading(true);
      loadAlertHistory()
        .then((items) => {
          if (isActive) {
            setAlerts(items);
          }
        })
        .catch((error) => {
          console.error("Failed to refresh alert history", error);
        })
        .finally(() => {
          if (isActive) {
            setIsLoading(false);
          }
        });

      return () => {
        isActive = false;
      };
    }, []),
  );

  const recentAlerts = alerts.filter((alert) =>
    isWithinDays(alert.receivedAt, 7),
  );
  const olderAlerts = alerts.filter(
    (alert) => !isWithinDays(alert.receivedAt, 7),
  );

  return (
    <AppScreen>
      <AppHeader title="지난 알람" showBack />
      <ScrollView showsVerticalScrollIndicator={false} bounces={false}>
        {isLoading ? (
          <EmptyState message="알림 내역을 불러오는 중입니다." />
        ) : alerts.length === 0 ? (
          <EmptyState message="저장된 알림 내역이 없습니다." />
        ) : (
          <>
            {recentAlerts.length > 0 && (
              <AlertSection title="최근 7일" alerts={recentAlerts} />
            )}
            {olderAlerts.length > 0 && (
              <AlertSection title="이전 알림" alerts={olderAlerts} />
            )}
          </>
        )}
      </ScrollView>
    </AppScreen>
  );
}

function AlertSection({
  title,
  alerts,
}: {
  title: string;
  alerts: AlertHistoryItem[];
}) {
  return (
    <>
      <Text style={styles.sectionTitle}>{title}</Text>
      {alerts.map((alert) => (
        <AlertCard key={alert.id} alert={alert} />
      ))}
    </>
  );
}

function AlertCard({ alert }: { alert: AlertHistoryItem }) {
  const isMissing = alert.type === "missing";
  const tint = isMissing
    ? colors.missingAlarm
    : alert.riskLevel
      ? riskColors[alert.riskLevel]
      : colors.primary;
  const riskLevel =
    alert.type === "flood" && alert.riskLevel ? alert.riskLevel : null;
  const metaText = normalizeMetaText(alert.meta);

  return (
    <Card style={styles.card}>
      <View style={[styles.iconCircle, { backgroundColor: tint }]}>
        {isMissing ? (
          <MaterialCommunityIcons
            name="account-search-outline"
            size={40}
            color="#fff"
          />
        ) : (
          <MaterialCommunityIcons name="home-flood" size={38} color="#fff" />
        )}
      </View>
      <View style={styles.cardContent}>
        <View style={styles.cardTop}>
          <Text style={styles.cardTitle}>{alert.title}</Text>
          <Text style={styles.time}>{formatReceivedAt(alert.receivedAt)}</Text>
        </View>
        <Text style={styles.body}>{alert.message}</Text>
        <View style={styles.metaRow}>
          <Ionicons
            name={isMissing ? "location" : "shield-half-outline"}
            size={15}
            color={isMissing ? colors.cardLine : tint}
          />
          <Text style={styles.meta}>
            {metaText || (isMissing ? "실종 알림" : "침수 위험 알림")}
          </Text>
          {riskLevel ? (
            <View style={[styles.riskBadge, { borderColor: tint }]}>
              <Text style={[styles.riskBadgeText, { color: tint }]}>
                {riskLabels[riskLevel]}
              </Text>
            </View>
          ) : null}
        </View>
      </View>
    </Card>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <Card style={styles.emptyCard}>
      <Ionicons name="notifications-outline" size={34} color={colors.subText} />
      <Text style={styles.emptyText}>{message}</Text>
    </Card>
  );
}

function isWithinDays(value: string, days: number) {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return false;
  }

  return Date.now() - timestamp <= days * 24 * 60 * 60 * 1000;
}

function formatReceivedAt(value: string) {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return "";
  }

  const diffMs = Date.now() - timestamp;
  const diffMinutes = Math.max(0, Math.floor(diffMs / (60 * 1000)));
  if (diffMinutes < 1) {
    return "방금 전";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}분 전`;
  }

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}시간 전`;
  }

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) {
    return `${diffDays}일 전`;
  }

  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
  }).format(new Date(timestamp));
}

function normalizeMetaText(meta?: string) {
  const trimmed = meta?.trim();
  if (!trimmed || trimmed === "{}") {
    return "";
  }

  return trimmed;
}

const styles = StyleSheet.create({
  sectionTitle: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
    marginTop: 5,
    marginBottom: 12,
  },
  card: {
    minHeight: 83,
    marginBottom: 12,
    padding: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
  iconCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: "center",
    justifyContent: "center",
  },
  cardContent: {
    flex: 1,
    gap: 6,
  },
  cardTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md,
  },
  cardTitle: {
    ...typography.titleMedium,
    flex: 1,
    color: colors.text,
    fontWeight: "700",
  },
  time: {
    ...typography.bodySmall,
    color: colors.subText,
  },
  body: {
    ...typography.bodySmallMedium,
    color: colors.text,
    fontSize: 11,
  },
  metaRow: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 4,
  },
  meta: {
    ...typography.bodySmall,
    color: colors.subText,
  },
  riskBadge: {
    borderWidth: 1,
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  riskBadgeText: {
    ...typography.bodySmall,
    fontWeight: "700",
  },
  emptyCard: {
    minHeight: 150,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
  },
  emptyText: {
    ...typography.bodyMediumRegular,
    color: colors.subText,
  },
});
